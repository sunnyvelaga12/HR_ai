"""
routes_hr.py — HR Admin API Routes (Production-Ready)

Endpoints:
  POST   /api/hr/companies                                   — Create/ensure company + optional logo
  GET    /api/hr/companies/{company_id}                      — Fallback company profile (fixes 404)
  GET    /api/hr/companies/{company_id}/profile              — Get company profile
  GET    /api/hr/companies/{company_id}/stats                — Overview stats (docs, employees, departments)
  GET    /api/hr/companies/{company_id}/employees            — List all employees with pagination
  POST   /api/hr/companies/{company_id}/documents            — Upload PDF/DOCX/TXT policy file
  GET    /api/hr/companies/{company_id}/documents            — List uploaded documents
  DELETE /api/hr/companies/{company_id}/documents/{doc_id}   — Delete a document
  POST   /api/hr/companies/{company_id}/employees/preview    — Parse CSV and return first 3 rows
  POST   /api/hr/companies/{company_id}/employees/import     — Import employees from CSV/XLSX
"""

import base64
import csv
import io
import logging
import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from app.db import get_db
from app.deps import require_role
from app.schemas_company import (
    CompanyCreateRequest,
    DocumentStatusResponse,
    PoliciesUpsertRequest,
)
from app.schemas_hr_import import (
    EmployeeImportPreview,
    EmployeeImportResult,
    EmployeePreviewRow,
)
from app.vector_db import (
    store_policy_document as vdb_store_policy,
    delete_policy as vdb_delete_policy,
    store_employee_data as vdb_store_employee,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hr", tags=["HR"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gen_temp_password(length: int = 12) -> str:
    """Generate a secure random temporary password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _normalize_column_name(column: str) -> str:
    """Normalize a single column name to its standard form."""
    return (column or "").strip().lower()


# ---------------------------------------------------------------------------
# Flexible CSV/XLSX column normalisation
# ---------------------------------------------------------------------------

COLUMN_MAP: Dict[str, str] = {
    # Full Name variants
    "full name": "fullName",
    "fullname": "fullName",
    "name": "fullName",
    "employee name": "fullName",
    "full_name": "fullName",
    "employee_name": "fullName",
    "contact name": "fullName",
    "contact": "fullName",
    # Split name variants (combined in _normalize_row)
    "first_name": "firstName",
    "first name": "firstName",
    "firstname": "firstName",
    "given name": "firstName",
    "last_name": "lastName",
    "last name": "lastName",
    "lastname": "lastName",
    "surname": "lastName",
    "family name": "lastName",
    # Employee ID
    "employee_id": "employeeId",
    "employee id": "employeeId",
    "emp id": "employeeId",
    "emp_id": "employeeId",
    "id": "employeeId",
    # Email variants
    "email": "email",
    "email address": "email",
    "emailaddress": "email",
    "work email": "email",
    "e-mail": "email",
    "e_mail": "email",
    # Phone variants
    "phone": "phone",
    "phone number": "phone",
    "mobile": "phone",
    "mobile number": "phone",
    "contact number": "phone",
    "phone_number": "phone",
    # Role / Job title variants
    "role": "role",
    "job title": "role",
    "jobtitle": "role",
    "title": "role",
    "position": "role",
    "designation": "role",
    "job role": "role",
    "job_title": "role",
    # Department variants
    "department": "department",
    "dept": "department",
    "team": "department",
    "division": "department",
    "business unit": "department",
    "group": "department",
    # Manager
    "manager_name": "managerName",
    "manager name": "managerName",
    "manager": "managerName",
    "reporting manager": "managerName",
    "reports to": "managerName",
    # Location
    "office_location": "officeLocation",
    "office location": "officeLocation",
    "location": "officeLocation",
    "city": "officeLocation",
    "office": "officeLocation",
    # Work mode
    "work_mode": "workMode",
    "work mode": "workMode",
    "working mode": "workMode",
    "mode": "workMode",
    # Employment status
    "employment_status": "status",
    "employment status": "status",
    "status": "status",
    "emp status": "status",
}



def _normalize_row(raw_row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map any CSV/XLSX column name variant to our standard field names.
    Handles split first_name + last_name columns by combining them into fullName.
    Returns a dict with keys: fullName, email, role, department (+ extras)
    """
    normalized: Dict[str, Any] = {}

    for raw_key, value in raw_row.items():
        clean_key = _normalize_column_name(raw_key)
        mapped_key = COLUMN_MAP.get(clean_key)

        # First match wins — don't overwrite existing normalized fields
        if mapped_key and mapped_key not in normalized:
            # Clean string values
            if isinstance(value, str):
                normalized[mapped_key] = value.strip()
            else:
                normalized[mapped_key] = value if value else ""

    # Combine firstName + lastName into fullName if fullName isn't already set
    if "fullName" not in normalized or not normalized["fullName"]:
        first = normalized.pop("firstName", "") or ""
        last = normalized.pop("lastName", "") or ""
        combined = f"{first} {last}".strip()
        if combined:
            normalized["fullName"] = combined
    else:
        # Clean up split fields if fullName already set
        normalized.pop("firstName", None)
        normalized.pop("lastName", None)

    return normalized



def _parse_raw_rows(filename: str, raw: bytes) -> List[Dict[str, Any]]:
    """
    Parse CSV or XLSX bytes into a list of normalized header→value dicts.
    
    Args:
        filename: Original filename (used to determine format)
        raw: Raw file bytes
    
    Returns:
        List of normalized row dictionaries
    
    Raises:
        HTTPException: If file format is unsupported or parsing fails
    """
    fname = _normalize_column_name(filename or "")
    
    try:
        # XLSX/XLS parsing
        if fname.endswith((".xlsx", ".xls")):
            try:
                import pandas as pd
            except ImportError:
                raise HTTPException(
                    status_code=400,
                    detail="XLSX import requires pandas. Please install it in the backend.",
                )
            
            df = pd.read_excel(io.BytesIO(raw))
            rows = []
            
            for _, row in df.iterrows():
                # Convert row to dict, handling NaN values
                raw_row = {}
                for col in df.columns:
                    value = row[col]
                    if pd.isna(value):
                        raw_row[str(col).strip()] = ""
                    else:
                        raw_row[str(col).strip()] = str(value).strip()
                
                normalized = _normalize_row(raw_row)
                if normalized.get("email"):  # Skip rows without email
                    rows.append(normalized)
            
            return rows
        
        # CSV parsing (default)
        else:
            text = raw.decode("utf-8-sig", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            rows = []
            
            for row in reader:
                # Filter out empty keys and normalize
                raw_row = {k.strip(): (v or "").strip() for k, v in row.items() if k and k.strip()}
                normalized = _normalize_row(raw_row)
                if normalized.get("email"):  # Skip rows without email
                    rows.append(normalized)
            
            return rows
    
    except UnicodeDecodeError as e:
        logger.error(f"Failed to decode file {filename}: {e}")
        raise HTTPException(
            status_code=400,
            detail="Unable to read file. Please ensure it's a valid CSV or XLSX file.",
        )
    except Exception as e:
        logger.error(f"Failed to parse file {filename}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse file: {str(e)}",
        )


def _extract_text_from_file(filename: str, raw: bytes) -> str:
    """
    Extract plain text from PDF, DOCX, or TXT file.
    
    Args:
        filename: Original filename
        raw: File bytes
    
    Returns:
        Extracted text string (empty if extraction fails)
    """
    fname = _normalize_column_name(filename)
    
    # Plain text files
    if fname.endswith(".txt"):
        return raw.decode("utf-8", errors="replace")
    
    # PDF extraction
    if fname.endswith(".pdf"):
        try:
            from pdfminer.high_level import extract_text as pdf_extract
            return pdf_extract(io.BytesIO(raw))
        except ImportError:
            logger.warning("pdfminer.six not installed, cannot extract PDF text")
            raise HTTPException(
                status_code=500,
                detail="PDF extraction requires pdfminer.six. Please install it in the backend.",
            )
        except Exception as e:
            logger.warning(f"PDF extraction failed for {filename}: {e}")
            return ""
    
    # DOCX extraction
    if fname.endswith(".docx"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(raw))
            return "\n".join(paragraph.text for paragraph in doc.paragraphs)
        except ImportError:
            logger.warning("python-docx not installed, cannot extract DOCX text")
            raise HTTPException(
                status_code=500,
                detail="DOCX extraction requires python-docx. Please install it in the backend.",
            )
        except Exception as e:
            logger.warning(f"DOCX extraction failed for {filename}: {e}")
            return ""
    
    return ""


def _row_to_employee(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map normalized CSV row keys to canonical employee fields.

    Args:
        row: Normalized row dictionary

    Returns:
        Employee dictionary with standard fields (including extras)
    """
    return {
        "email": row.get("email", ""),
        "fullName": row.get("fullName", ""),
        "role_title": row.get("role", "employee"),
        "department": row.get("department", ""),
        # Extra fields from expanded COLUMN_MAP
        "employeeId": row.get("employeeId", ""),
        "phone": row.get("phone", ""),
        "managerName": row.get("managerName", ""),
        "officeLocation": row.get("officeLocation", ""),
        "workMode": row.get("workMode", ""),
        "status": row.get("status", "Active"),
    }



# ---------------------------------------------------------------------------
# Company Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/companies",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(role="hr_admin"))],
)
async def create_company(
    companyName: str = Form(...),
    logo: Optional[UploadFile] = File(default=None),
    user: dict = Depends(require_role(role="hr_admin")),
):
    """
    Create or ensure company workspace. Accepts optional logo file.
    
    Returns:
        Company creation confirmation with logo status
    """
    company_name = companyName.strip()
    if not company_name:
        raise HTTPException(status_code=400, detail="companyName is required")
    
    # Use the JWT companyId (set at signup) so HR admin always maps to their company
    company_id = user.get("companyId") or company_name.lower().replace(" ", "-")
    
    # Process logo if provided
    logo_b64 = None
    if logo and logo.filename:
        raw_logo = await logo.read()
        if len(raw_logo) > 2 * 1024 * 1024:  # 2 MB limit
            raise HTTPException(status_code=400, detail="Logo must be under 2 MB")
        logo_b64 = base64.b64encode(raw_logo).decode()
    
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    
    # Prepare update fields
    update_fields: Dict[str, Any] = {
        "name": company_name,
        "updatedAt": now,
    }
    if logo_b64:
        update_fields["logo"] = logo_b64
    
    # Upsert company
    await db.companies.update_one(
        {"_id": company_id},
        {
            "$set": update_fields,
            "$setOnInsert": {
                "_id": company_id,
                "createdAt": now,
            },
        },
        upsert=True,
    )
    
    logger.info(f"Company created/updated: {company_id} ({company_name})")
    
    return {
        "companyId": company_id,
        "name": company_name,
        "hasLogo": logo_b64 is not None,
    }


@router.get(
    "/companies/{company_id}",
    dependencies=[Depends(require_role(role="hr_admin"))],
)
async def get_company_fallback(company_id: str):
    """
    Fallback router to catch standard company root GET requests.
    This fixes the 404 error when frontend calls /api/hr/companies/{company_id}
    """
    return await get_company_profile(company_id)


@router.get(
    "/companies/{company_id}/profile",
    dependencies=[Depends(require_role(role="hr_admin"))],
)
async def get_company_profile(company_id: str):
    """
    Return company name and logo (base64).
    
    Returns:
        Company profile with name and optional base64-encoded logo
    """
    db = get_db()
    company = await db.companies.find_one({"_id": company_id})
    
    if not company:
        # Provide a fallback and auto-create the document if missing
        company = {
            "_id": company_id,
            "name": "HR Admin",
            "createdAt": datetime.now(timezone.utc).isoformat()
        }
        try:
            await db.companies.insert_one(company)
        except Exception:
            pass
    
    return {
        "companyId": company_id,
        "name": company.get("name", "HR Admin"),
        "logo": company.get("logo"),  # base64 or None
    }


@router.get(
    "/companies/{company_id}/stats",
    dependencies=[Depends(require_role(role="hr_admin"))],
)
async def get_company_stats(company_id: str):
    """
    Return real-time overview stats derived from MongoDB collections.
    
    Returns:
        Statistics including employee count, document count, and department breakdown
    """
    db = get_db()
    
    # Run counts concurrently for better performance
    total_employees = await db.users.count_documents({
        "companyId": company_id,
        "role": "employee",
    })
    
    total_documents = await db.documents.count_documents({
        "companyId": company_id,
    })
    
    ready_documents = await db.documents.count_documents({
        "companyId": company_id,
        "status": "ready",
    })
    
    # Department breakdown using aggregation pipeline
    pipeline = [
        {"$match": {"companyId": company_id, "role": "employee"}},
        {"$group": {"_id": "$department", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    
    departments = []
    async for doc in db.users.aggregate(pipeline):
        departments.append({
            "department": doc["_id"] or "Unassigned",
            "count": doc["count"],
        })
    
    return {
        "total_employees": total_employees,
        "total_documents": total_documents,
        "ready_documents": ready_documents,
        "departments": departments,
        "department_count": len(departments),
    }


@router.get(
    "/companies/{company_id}/employees",
    dependencies=[Depends(require_role(role="hr_admin"))],
)
async def list_employees(
    company_id: str,
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum records to return"),
    department: Optional[str] = Query(default=None, description="Filter by department"),
    search: Optional[str] = Query(default=None, description="Search by name or email"),
):
    """
    List all employees for the company with pagination and optional filters.
    
    Args:
        company_id: Company identifier
        skip: Number of records to skip for pagination
        limit: Maximum number of records to return
        department: Optional department filter
        search: Optional search term for name or email
    
    Returns:
        Paginated list of employees
    """
    db = get_db()
    
    # Build query filters
    query: Dict[str, Any] = {"companyId": company_id, "role": "employee"}
    
    if department:
        query["department"] = department
    
    if search:
        query["$or"] = [
            {"fullName": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]
    
    # Execute queries concurrently
    total_task = db.users.count_documents(query)
    
    cursor = db.users.find(
        query,
        {"passwordHash": 0, "tempPassword": 0},  # Exclude sensitive fields
    ).skip(skip).limit(limit).sort("fullName", 1)
    
    # Process results
    employees = []
    async for emp in cursor:
        employees.append({
            "id": str(emp["_id"]),
            "fullName": emp.get("fullName", ""),
            "email": emp.get("email", ""),
            "department": emp.get("department", ""),
            "jobTitle": emp.get("jobTitle", ""),
            "createdAt": emp.get("createdAt", ""),
        })
    
    total = await total_task
    
    return {
        "employees": employees,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


# ---------------------------------------------------------------------------
# Documents (Policy Files)
# ---------------------------------------------------------------------------

@router.post(
    "/companies/{company_id}/documents",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(role="hr_admin"))],
)
async def upload_document(
    company_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(require_role(role="hr_admin")),
):
    """
    Upload a PDF, DOCX, or TXT policy document.
    Extracts text and stores as policy for RAG/chatbot usage.
    
    Args:
        company_id: Company identifier
        file: The document file to upload
        user: Authenticated user information
    
    Returns:
        Document upload status and metadata
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="File is required")
    
    # Validate file extension
    fname = _normalize_column_name(file.filename)
    allowed_extensions = (".pdf", ".docx", ".txt")
    if not any(fname.endswith(ext) for ext in allowed_extensions):
        raise HTTPException(
            status_code=400,
            detail=f"Only {', '.join(allowed_extensions)} files are supported",
        )
    
    # Read file content
    raw = await file.read()
    file_size = len(raw)
    
    # File size validation (10 MB limit for documents)
    max_size = 10 * 1024 * 1024  # 10 MB
    if file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum limit of {max_size // (1024*1024)} MB",
        )
    
    # Generate document ID and timestamps
    doc_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    db = get_db()
    
    # Insert initial document record as "processing"
    await db.documents.insert_one({
        "_id": doc_id,
        "companyId": company_id,
        "filename": file.filename,
        "size_bytes": file_size,
        "status": "processing",
        "uploadedBy": user.get("email", "unknown"),
        "uploadedAt": now,
        "updatedAt": now,
    })
    
    # Process document text extraction
    try:
        text = _extract_text_from_file(file.filename, raw)
        
        if not text or not text.strip():
            raise ValueError("No text could be extracted from the file")
        
        # Store policy document
        await db.policies.update_one(
            {"companyId": company_id},
            {
                "$set": {
                    f"documents.{doc_id}": {
                        "filename": file.filename,
                        "text": text,
                        "size_bytes": file_size,
                        "uploadedAt": now,
                    },
                    "companyId": company_id,
                    "updatedAt": now,
                },
            },
            upsert=True,
        )
        
        # Rebuild combined policy text for chatbot/RAG
        policy_doc = await db.policies.find_one({"companyId": company_id})
        if policy_doc and "documents" in policy_doc:
            docs = policy_doc["documents"]
            combined = "\n\n---\n\n".join(
                f"[Source: {d['filename']}]\n{d['text']}"
                for d in docs.values()
                if isinstance(d, dict) and "text" in d
            )
            
            await db.policies.update_one(
                {"companyId": company_id},
                {
                    "$set": {
                        "content.full_text": combined,
                        "updatedAt": now,
                    }
                },
            )
        
        # ✅ RAG: Store policy chunks in Pinecone tagged with company_id
        try:
            # Split large documents into chunks of ~1500 chars for better retrieval
            chunk_size = 1500
            chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
            for idx, chunk in enumerate(chunks):
                chunk_id = f"{doc_id}_chunk{idx}"
                vdb_store_policy(
                    company_id=company_id,
                    doc_id=chunk_id,
                    section=file.filename,
                    policy_type="uploaded_document",
                    content=chunk,
                    metadata={"filename": file.filename, "chunk_index": idx, "total_chunks": len(chunks)},
                )
            logger.info(f"Indexed {len(chunks)} chunks in Pinecone for doc {doc_id} (company {company_id})")
        except Exception as vec_err:
            # Vector DB failure is non-fatal — MongoDB still has the full text
            logger.warning(f"Vector DB indexing failed for {doc_id}: {vec_err}")
        
        # Update document status to "ready"
        await db.documents.update_one(
            {"_id": doc_id},
            {
                "$set": {
                    "status": "ready",
                    "updatedAt": now,
                }
            },
        )
        
        final_status = "ready"
        logger.info(f"Document processed successfully: {file.filename} (ID: {doc_id})")
        
    except Exception as e:
        logger.error(f"Document processing failed for {file.filename}: {e}", exc_info=True)
        
        # Update document status to "error"
        await db.documents.update_one(
            {"_id": doc_id},
            {
                "$set": {
                    "status": "error",
                    "error": str(e),
                    "updatedAt": now,
                }
            },
        )
        final_status = "error"
    
    return {
        "id": doc_id,
        "filename": file.filename,
        "size_bytes": file_size,
        "status": final_status,
        "uploaded_at": now,
    }


@router.get(
    "/companies/{company_id}/documents",
    dependencies=[Depends(require_role(role="hr_admin"))],
)
async def list_documents(
    company_id: str,
    status: Optional[str] = Query(default=None, description="Filter by status (ready, processing, error)"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    List all uploaded documents for a company.
    
    Args:
        company_id: Company identifier
        status: Optional status filter
        skip: Pagination offset
        limit: Maximum results per page
    
    Returns:
        List of documents with metadata
    """
    db = get_db()
    
    # Build query
    query: Dict[str, Any] = {"companyId": company_id}
    if status:
        query["status"] = status
    
    # Execute query with sorting and pagination
    cursor = db.documents.find(query).sort("uploadedAt", -1).skip(skip).limit(limit)
    
    docs = []
    async for doc in cursor:
        docs.append({
            "id": str(doc["_id"]),
            "filename": doc.get("filename", ""),
            "size_bytes": doc.get("size_bytes", 0),
            "status": doc.get("status", "processing"),
            "uploaded_at": doc.get("uploadedAt", ""),
            "error": doc.get("error") if doc.get("status") == "error" else None,
        })
    
    total = await db.documents.count_documents(query)
    
    return {
        "documents": docs,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.delete(
    "/companies/{company_id}/documents/{doc_id}",
    dependencies=[Depends(require_role(role="hr_admin"))],
)
async def delete_document(company_id: str, doc_id: str):
    """
    Delete a document and remove its text from the policy store.
    
    Args:
        company_id: Company identifier
        doc_id: Document identifier
    
    Returns:
        Deletion confirmation
    """
    db = get_db()
    
    # Delete document record
    result = await db.documents.delete_one({
        "_id": doc_id,
        "companyId": company_id,
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Remove from policies collection
    await db.policies.update_one(
        {"companyId": company_id},
        {"$unset": {f"documents.{doc_id}": ""}},
    )
    
    # Rebuild combined policy text after deletion
    policy_doc = await db.policies.find_one({"companyId": company_id})
    if policy_doc and "documents" in policy_doc:
        docs = policy_doc.get("documents", {})
        # Clean up None values from $unset
        docs = {k: v for k, v in docs.items() if v is not None}
        
        if docs:
            combined = "\n\n---\n\n".join(
                f"[Source: {d['filename']}]\n{d['text']}"
                for d in docs.values()
                if isinstance(d, dict) and "text" in d
            )
            await db.policies.update_one(
                {"companyId": company_id},
                {
                    "$set": {
                        "content.full_text": combined,
                        "updatedAt": datetime.now(timezone.utc).isoformat(),
                    },
                },
            )
        else:
            # Remove content if no documents remain
            await db.policies.update_one(
                {"companyId": company_id},
                {"$unset": {"content": ""}},
            )
    
    # ✅ RAG: Remove all Pinecone vectors for this document (all chunks)
    try:
        # We stored chunks as {doc_id}_chunk0, {doc_id}_chunk1, etc.
        # Delete the base doc_id pattern — attempt up to 50 chunks
        deleted_chunks = 0
        for idx in range(50):
            chunk_id = f"{doc_id}_chunk{idx}"
            result = vdb_delete_policy(doc_id=chunk_id, company_id=company_id)
            if result:
                deleted_chunks += 1
            else:
                break  # Stop when chunks run out
        logger.info(f"Removed {deleted_chunks} Pinecone chunks for doc {doc_id} (company {company_id})")
    except Exception as vec_err:
        logger.warning(f"Vector DB cleanup failed for {doc_id}: {vec_err}")
    
    logger.info(f"Document deleted: {doc_id} from company {company_id}")
    
    return {
        "status": "deleted",
        "doc_id": doc_id,
    }


# ---------------------------------------------------------------------------
# Employee Import
# ---------------------------------------------------------------------------

@router.post(
    "/companies/{company_id}/employees/preview",
    dependencies=[Depends(require_role(role="hr_admin"))],
)
async def preview_employees(
    company_id: str,
    file: UploadFile = File(...),
):
    """
    Parse uploaded CSV/XLSX and return first 3 rows for preview.
    
    Args:
        company_id: Company identifier
        file: CSV or XLSX file to preview
    
    Returns:
        Preview of first 3 rows with total row count
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="File is required")
    
    # Validate file type
    fname = _normalize_column_name(file.filename)
    if not (fname.endswith(".csv") or fname.endswith((".xlsx", ".xls"))):
        raise HTTPException(
            status_code=400,
            detail="Only CSV and XLSX files are supported for employee import",
        )
    
    # Read and parse file
    raw = await file.read()
    
    try:
        all_rows = _parse_raw_rows(file.filename, raw)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to parse preview file: {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse file: {str(e)}",
        )
    
    if not all_rows:
        raise HTTPException(
            status_code=400,
            detail="No valid rows found in file. Ensure the file has headers and at least one data row.",
        )
    
    # Generate preview (first 3 rows)
    preview_rows = []
    for row in all_rows[:3]:
        emp = _row_to_employee(row)
        if emp["email"]:  # Only include rows with email
            preview_rows.append(
                EmployeePreviewRow(
                    email=emp["email"],
                    fullName=emp["fullName"],
                    role=emp["role_title"],
                    department=emp["department"],
                )
            )
    
    return EmployeeImportPreview(
        rows=preview_rows,
        total_rows=len(all_rows),
    )


@router.post(
    "/companies/{company_id}/employees/import",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(role="hr_admin"))],
)
async def import_employees(
    company_id: str,
    file: UploadFile = File(...),
    sendInvites: bool = Query(default=False, description="Send email invites to imported employees"),
    updateExisting: bool = Query(default=True, description="Update existing employees if found"),
    user: dict = Depends(require_role(role="hr_admin")),
):
    """
    Import employees from CSV/XLSX.
    
    Required columns (case-insensitive, flexible naming):
      - Email (email, email address, work email, etc.)
      - Full Name (full name, name, employee name, etc.)
    
    Optional columns:
      - Role/Job Title (role, job title, position, etc.)
      - Department (department, dept, team, etc.)
    
    Passwords are auto-generated — no password column needed.
    
    Args:
        company_id: Company identifier
        file: CSV or XLSX file with employee data
        sendInvites: Whether to send email invitations
        updateExisting: Whether to update existing employees
        user: Authenticated user information
    
    Returns:
        Import results with counts of created, updated, and skipped records
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="File is required")
    
    # Validate file type
    fname = _normalize_column_name(file.filename)
    if not (fname.endswith(".csv") or fname.endswith((".xlsx", ".xls"))):
        raise HTTPException(
            status_code=400,
            detail="Only CSV and XLSX files are supported for employee import",
        )
    
    # Read and parse file
    raw = await file.read()
    
    try:
        all_rows = _parse_raw_rows(file.filename, raw)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to parse import file: {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse file: {str(e)}",
        )
    
    if not all_rows:
        raise HTTPException(
            status_code=400,
            detail="No valid rows found in file. Ensure the file has headers and at least one data row.",
        )
    
    # Import required module
    try:
        from app.auth import hash_password
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Authentication module not available",
        )
    
    # Initialize results
    results = EmployeeImportResult()
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    
    # Process each row
    for row in all_rows:
        emp = _row_to_employee(row)
        email = emp["email"]
        full_name = emp["fullName"]
        
        # Skip rows without required fields
        if not email or not full_name:
            results.skipped += 1
            logger.warning(f"Skipping row - missing required fields: email={email}, name={full_name}")
            continue
        
        # Generate temporary password
        temp_password = _gen_temp_password()
        
        # Prepare employee data with all available fields
        employee_data = {
            "email": email,
            "fullName": full_name,
            "passwordHash": hash_password(temp_password),
            "role": "employee",
            "jobTitle": emp["role_title"],
            "department": emp["department"],
            "companyId": company_id,
            "tempPassword": temp_password,  # Stored until first login
            "updatedAt": now,
            # Extra fields from expanded CSV columns
            "employeeId": emp.get("employeeId", ""),
            "phone": emp.get("phone", ""),
            "managerName": emp.get("managerName", ""),
            "officeLocation": emp.get("officeLocation", ""),
            "workMode": emp.get("workMode", ""),
            "employmentStatus": emp.get("status", "Active"),
        }
        
        # Check if employee already exists
        existing = await db.users.find_one({
            "email": email,
            "companyId": company_id,
        })
        
        if existing:
            if updateExisting:
                # Update existing employee (don't change password)
                update_fields = {
                    k: v for k, v in employee_data.items()
                    if k not in ("passwordHash", "tempPassword")
                }
                await db.users.update_one(
                    {"_id": existing["_id"]},
                    {"$set": update_fields},
                )
                results.updated += 1
            else:
                results.skipped += 1
        else:
            # Create new employee
            employee_data["createdAt"] = now
            await db.users.insert_one(employee_data)
            results.created += 1
        
        # ✅ RAG: Store/update employee in Pinecone tagged with company_id
        try:
            employee_summary = (
                f"Employee {full_name} works as a {emp.get('role_title') or 'employee'} "
                f"in the {emp.get('department') or 'General'} department. "
                f"Contact email: {email}. "
                f"Office: {emp.get('officeLocation') or 'N/A'}. "
                f"Work mode: {emp.get('workMode') or 'N/A'}. "
                f"Manager: {emp.get('managerName') or 'N/A'}."
            )
            vdb_store_employee(
                company_id=company_id,
                employee_id=email,
                name=full_name,
                department=emp.get("department") or "General",
                designation=emp.get("role_title") or "Employee",
                summary=employee_summary,
                metadata={
                    "phone": emp.get("phone", ""),
                    "manager": emp.get("managerName", ""),
                    "location": emp.get("officeLocation", ""),
                    "work_mode": emp.get("workMode", ""),
                    "employee_id": emp.get("employeeId", ""),
                },
            )
        except Exception as vec_err:
            # Vector DB failure is non-fatal — MongoDB still has the employee data
            logger.warning(f"Vector DB indexing failed for employee {email}: {vec_err}")

    
    # Handle email invites
    if sendInvites:
        total_invites = results.created + results.updated
        logger.info(
            f"Email invites requested for {total_invites} employees "
            f"in company {company_id}"
        )
        # TODO: Implement actual email sending logic
        # This would typically involve:
        # 1. Queueing emails in a background task
        # 2. Using an email service (SendGrid, AWS SES, etc.)
        # 3. Including login instructions and temporary password
    
    logger.info(
        f"Import complete for company {company_id}: "
        f"created={results.created}, updated={results.updated}, skipped={results.skipped}"
    )
    
    return results.model_dump()


# ---------------------------------------------------------------------------
# Employee Management (CRUD)
# ---------------------------------------------------------------------------

from pydantic import BaseModel

class EmployeeUpdateRequest(BaseModel):
    fullName: str
    jobTitle: str
    department: str
    phone: str = ""
    managerName: str = ""
    officeLocation: str = ""
    workMode: str = ""
    employmentStatus: str = ""
    employeeId: str = ""

@router.put("/companies/{company_id}/employees/{employee_id}")
async def update_employee(
    company_id: str,
    employee_id: str,
    payload: EmployeeUpdateRequest,
    user: dict = Depends(require_role(role="hr_admin"))
):
    """Update employee data in MongoDB and sync to Pinecone."""
    if user.get("companyId") != company_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    db = get_db()
    
    # Check if employee exists
    emp = await db.users.find_one({"_id": employee_id, "companyId": company_id})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    update_data = payload.model_dump()
    update_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    
    # Update MongoDB
    await db.users.update_one(
        {"_id": employee_id},
        {"$set": update_data}
    )
    
    # Sync to Pinecone
    try:
        from app.vector_db import store_employee_data as vdb_store_employee
        employee_summary = (
            f"Employee {payload.fullName} works as a {payload.jobTitle or 'employee'} "
            f"in the {payload.department or 'General'} department. "
            f"Contact email: {emp.get('email')}. "
            f"Office: {payload.officeLocation or 'N/A'}. "
            f"Work mode: {payload.workMode or 'N/A'}. "
            f"Manager: {payload.managerName or 'N/A'}."
        )
        vdb_store_employee(
            company_id=company_id,
            employee_id=emp.get("email"),
            name=payload.fullName,
            department=payload.department or "General",
            designation=payload.jobTitle or "Employee",
            summary=employee_summary,
            metadata={
                "phone": payload.phone,
                "manager": payload.managerName,
                "location": payload.officeLocation,
                "work_mode": payload.workMode,
                "employee_id": payload.employeeId,
            },
        )
    except Exception as e:
        logger.warning(f"Vector DB sync failed for {employee_id}: {e}")
        
    return {"message": "Employee updated"}

@router.delete("/companies/{company_id}/employees/{employee_id}")
async def delete_employee(
    company_id: str,
    employee_id: str,
    user: dict = Depends(require_role(role="hr_admin"))
):
    """Delete employee from MongoDB and Pinecone."""
    if user.get("companyId") != company_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    db = get_db()
    emp = await db.users.find_one({"_id": employee_id, "companyId": company_id})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    # Delete from MongoDB
    await db.users.delete_one({"_id": employee_id})
    
    # Delete from Pinecone
    try:
        from app.vector_db import delete_employee as vdb_delete_employee
        vdb_delete_employee(employee_id=emp.get("email"), company_id=company_id)
    except Exception as e:
        logger.warning(f"Vector DB delete failed for {employee_id}: {e}")
        
    return {"message": "Employee deleted"}


# ---------------------------------------------------------------------------
# Workspace Passkey Management
# ---------------------------------------------------------------------------

@router.get("/companies/{company_id}/passkey")
async def get_passkey(
    company_id: str,
    user: dict = Depends(require_role(role="hr_admin"))
):
    if user.get("companyId") != company_id:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    db = get_db()
    company = await db.companies.find_one({"_id": company_id})
    
    if company and company.get("passkey"):
        return {"passkey": company.get("passkey")}
        
    # Generate one if missing
    from app.routes_auth import _generate_passkey
    new_passkey = _generate_passkey()
    
    await db.companies.update_one(
        {"_id": company_id},
        {"$set": {"passkey": new_passkey, "name": company.get("name") if company else "HR Admin"}},
        upsert=True
    )
    
    return {"passkey": new_passkey}

@router.post("/companies/{company_id}/passkey/regenerate")
async def regenerate_passkey(
    company_id: str,
    user: dict = Depends(require_role(role="hr_admin"))
):
    if user.get("companyId") != company_id:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    db = get_db()
    from app.routes_auth import _generate_passkey
    new_passkey = _generate_passkey()
    
    await db.companies.update_one(
        {"_id": company_id},
        {"$set": {"passkey": new_passkey}}
    )
    
    return {"passkey": new_passkey}


# ---------------------------------------------------------------------------
# Query Logs
# ---------------------------------------------------------------------------

@router.get("/companies/{company_id}/query-logs")
async def get_query_logs(
    company_id: str,
    limit: int = 50,
    skip: int = 0,
    user: dict = Depends(require_role(role="hr_admin"))
):
    if user.get("companyId") != company_id:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    db = get_db()
    cursor = db.query_logs.find({"company_id": company_id}).sort("timestamp", -1).skip(skip).limit(limit)
    logs = await cursor.to_list(length=limit)
    
    # Enrich with employee names (could be optimized with a join, but fine for now)
    result = []
    for log in logs:
        log_out = {
            "id": str(log["_id"]),
            "user_id": log.get("user_id"),
            "role": log.get("role"),
            "question": log.get("question"),
            "answer": log.get("answer"),
            "timestamp": log.get("timestamp"),
            "employee_name": "Unknown"
        }
        if log.get("user_id"):
            emp = await db.users.find_one({"_id": log["user_id"]})
            if emp:
                log_out["employee_name"] = emp.get("fullName") or emp.get("email")
        result.append(log_out)
        
    total = await db.query_logs.count_documents({"company_id": company_id})
    return {"logs": result, "total": total}

# ---------------------------------------------------------------------------
# Health Check (Optional but recommended for production)
# ---------------------------------------------------------------------------


@router.get("/health", include_in_schema=False)
async def health_check():
    """Simple health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": "hr-api",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }