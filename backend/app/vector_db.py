"""
vector_db.py — Vector Database Integration for HR Policies & Employee Data

Integrates Pinecone vector database with Sentence Transformers for semantic search.

Key design principle: every vector is tagged with `company_id` in its metadata.
All search queries apply a Pinecone metadata filter `{"company_id": {"$eq": company_id}}`
so that one HR's policies/employees are NEVER visible to another company's employees.
"""

import logging
import json
import os
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.config import settings

logger = logging.getLogger(__name__)

# Global instances
_embeddings_model = None
_pinecone_client = None


def get_embeddings_model():
    """Initialize and cache the Sentence Transformers embedding model."""
    global _embeddings_model
    if _embeddings_model is not None:
        return _embeddings_model

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is not installed. Install backend dependencies before running."
        ) from exc

    model_name = settings.EMBEDDING_MODEL
    logger.info(f"Loading embedding model: {model_name}")
    _embeddings_model = SentenceTransformer(model_name)
    logger.info("Embedding model loaded successfully")
    return _embeddings_model


def get_pinecone_client():
    """Initialize and cache the Pinecone client."""
    global _pinecone_client
    if _pinecone_client is not None:
        return _pinecone_client

    api_key = settings.PINECONE_API_KEY
    if not api_key:
        logger.warning("PINECONE_API_KEY not set. Vector DB operations will be disabled.")
        return None

    try:
        from pinecone import Pinecone
    except ImportError as exc:
        raise RuntimeError(
            "pinecone-client is not installed. Install backend dependencies before running."
        ) from exc

    try:
        _pinecone_client = Pinecone(api_key=api_key)
        logger.info("Pinecone client initialized successfully")
        return _pinecone_client
    except Exception as e:
        logger.error(f"Failed to initialize Pinecone client: {e}")
        return None


_pinecone_index = None


def create_or_get_index():
    """Create Pinecone index if it doesn't exist, or get existing one."""
    global _pinecone_index
    if _pinecone_index is not None:
        return _pinecone_index

    client = get_pinecone_client()
    if not client:
        logger.error("Pinecone client not initialized")
        return None

    index_name = settings.PINECONE_INDEX_NAME
    dimension = settings.PINECONE_DIMENSION

    try:
        # Check if index exists
        existing_indexes = client.list_indexes()
        if index_name not in [idx.name for idx in existing_indexes]:
            logger.info(f"Creating Pinecone index: {index_name}")
            client.create_index(
                name=index_name,
                dimension=dimension,
                metric="cosine",
                spec={
                    "serverless": {
                        "cloud": "aws",
                        "region": settings.PINECONE_ENVIRONMENT,
                    }
                },
            )
            logger.info(f"Index {index_name} created successfully")
        else:
            logger.info(f"Index {index_name} already exists")

        _pinecone_index = client.Index(index_name)
        return _pinecone_index
    except Exception as e:
        logger.error(f"Failed to create/get index: {e}")
        return None


def embed_text(text: str) -> Optional[List[float]]:
    """
    Convert text to embedding vector.

    Args:
        text: Text to embed

    Returns:
        Embedding vector or None if error
    """
    try:
        embeddings_model = get_embeddings_model()
        embedding = embeddings_model.encode(text, convert_to_numpy=False)
        return embedding.tolist() if hasattr(embedding, "tolist") else embedding
    except Exception as e:
        logger.error(f"Error embedding text: {e}")
        return None


# ============================================================================
# Policy Storage & Search (company_id scoped)
# ============================================================================

def store_policy_document(
    company_id: str,
    doc_id: str,
    section: str,
    policy_type: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Store a policy document in the vector database, tagged with company_id.

    Args:
        company_id: The HR's company identifier (used for isolation)
        doc_id: Unique identifier for the document chunk
        section: Policy section name
        policy_type: Type of policy (e.g., "leave_policy", "salary_policy")
        content: Full policy text for this chunk
        metadata: Additional metadata to store

    Returns:
        True if successful, False otherwise
    """
    try:
        # Generate embedding
        embedding = embed_text(content)
        if not embedding:
            logger.error(f"Failed to embed policy: {doc_id}")
            return False

        # Prepare metadata — always include company_id for filtering
        meta = {
            "company_id": company_id,
            "doc_id": doc_id,
            "section": section,
            "policy_type": policy_type,
            "data_type": "policy",
            "content_preview": content[:500],  # Store first 500 chars for retrieval
            "created_at": datetime.utcnow().isoformat(),
            **(metadata or {}),
        }

        # Get index and upsert — use company-scoped vector ID to avoid collisions
        index = create_or_get_index()
        if not index:
            logger.error("Failed to get Pinecone index")
            return False

        vector_id = f"{company_id}__policy__{doc_id}"
        index.upsert(
            vectors=[(vector_id, embedding, meta)],
            namespace="policies",
        )

        logger.info(f"Stored policy document: {doc_id} for company: {company_id}")
        return True
    except Exception as e:
        logger.error(f"Error storing policy document: {e}")
        return False


def search_policies(
    company_id: str,
    query: str,
    top_k: int = 5,
    score_threshold: float = 0.3,
) -> List[Dict[str, Any]]:
    """
    Search for policies using semantic similarity, filtered to a specific company.

    Args:
        company_id: The HR's company identifier — only this company's policies are returned
        query: Search query text
        top_k: Number of results to return
        score_threshold: Minimum similarity score (0-1)

    Returns:
        List of matching policies with scores and metadata
    """
    try:
        # Generate embedding for query
        query_embedding = embed_text(query)
        if not query_embedding:
            logger.error("Failed to embed search query")
            return []

        # Search in Pinecone with company_id metadata filter
        index = create_or_get_index()
        if not index:
            logger.error("Failed to get Pinecone index")
            return []

        results = index.query(
            vector=query_embedding,
            top_k=top_k,
            namespace="policies",
            include_metadata=True,
            filter={"company_id": {"$eq": company_id}},
        )

        # Filter by score threshold and format results
        matches = []
        for match in results.get("matches", []):
            if match.get("score", 0) >= score_threshold:
                matches.append({
                    "id": match["id"],
                    "score": match["score"],
                    "metadata": match.get("metadata", {}),
                })

        logger.info(
            f"Found {len(matches)} policies for company {company_id} matching query"
        )
        return matches
    except Exception as e:
        logger.error(f"Error searching policies: {e}")
        return []


def delete_policy(doc_id: str, company_id: Optional[str] = None) -> bool:
    """
    Delete a policy document from the vector database.

    Args:
        doc_id: The original document ID
        company_id: If provided, constructs the scoped vector ID; otherwise uses doc_id directly
    """
    try:
        index = create_or_get_index()
        if not index:
            return False

        vector_id = f"{company_id}__policy__{doc_id}" if company_id else doc_id
        index.delete(ids=[vector_id], namespace="policies")
        logger.info(f"Deleted policy: {vector_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting policy: {e}")
        return False


# ============================================================================
# Employee Storage & Search (company_id scoped)
# ============================================================================

def store_employee_data(
    company_id: str,
    employee_id: str,
    name: str,
    department: str,
    designation: str,
    summary: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Store employee data in the vector database, tagged with company_id.

    Args:
        company_id: The HR's company identifier (used for isolation)
        employee_id: Unique employee identifier (typically email)
        name: Employee name
        department: Department name
        designation: Job designation
        summary: Employee profile summary
        metadata: Additional metadata

    Returns:
        True if successful, False otherwise
    """
    try:
        # Create searchable content
        content = f"{name} {designation} {department} {summary}"

        # Generate embedding
        embedding = embed_text(content)
        if not embedding:
            logger.error(f"Failed to embed employee data: {employee_id}")
            return False

        # Prepare metadata — always include company_id for filtering
        meta = {
            "company_id": company_id,
            "employee_id": employee_id,
            "name": name,
            "department": department,
            "designation": designation,
            "summary": summary,
            "data_type": "employee",
            "created_at": datetime.utcnow().isoformat(),
            **(metadata or {}),
        }

        # Get index and upsert — use company-scoped vector ID to avoid collisions
        index = create_or_get_index()
        if not index:
            logger.error("Failed to get Pinecone index")
            return False

        vector_id = f"{company_id}__employee__{employee_id}"
        index.upsert(
            vectors=[(vector_id, embedding, meta)],
            namespace="employees",
        )

        logger.info(f"Stored employee data: {employee_id} for company: {company_id}")
        return True
    except Exception as e:
        logger.error(f"Error storing employee data: {e}")
        return False


def delete_employee(employee_id: str, company_id: str) -> bool:
    """
    Delete an employee record from the vector database.

    Args:
        employee_id: Unique employee identifier
        company_id: The HR's company identifier (used for scoped vector ID)
    """
    try:
        index = create_or_get_index()
        if not index:
            return False

        vector_id = f"{company_id}__employee__{employee_id}"
        index.delete(ids=[vector_id], namespace="employees")
        logger.info(f"Deleted employee data: {vector_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting employee data: {e}")
        return False


def search_employees(
    company_id: str,
    query: str,
    top_k: int = 5,
    score_threshold: float = 0.3,
) -> List[Dict[str, Any]]:
    """
    Search for employees using semantic similarity, filtered to a specific company.

    Args:
        company_id: The HR's company identifier — only this company's employees are returned
        query: Search query text
        top_k: Number of results to return
        score_threshold: Minimum similarity score (0-1)

    Returns:
        List of matching employees with scores and metadata
    """
    try:
        # Generate embedding for query
        query_embedding = embed_text(query)
        if not query_embedding:
            logger.error("Failed to embed search query")
            return []

        # Search in Pinecone with company_id metadata filter
        index = create_or_get_index()
        if not index:
            logger.error("Failed to get Pinecone index")
            return []

        results = index.query(
            vector=query_embedding,
            top_k=top_k,
            namespace="employees",
            include_metadata=True,
            filter={"company_id": {"$eq": company_id}},
        )

        # Filter by score threshold and format results
        matches = []
        for match in results.get("matches", []):
            if match.get("score", 0) >= score_threshold:
                matches.append({
                    "id": match["id"],
                    "score": match["score"],
                    "metadata": match.get("metadata", {}),
                })

        logger.info(
            f"Found {len(matches)} employees for company {company_id} matching query"
        )
        return matches
    except Exception as e:
        logger.error(f"Error searching employees: {e}")
        return []


def delete_employee(employee_id: str, company_id: Optional[str] = None) -> bool:
    """
    Delete an employee record from the vector database.

    Args:
        employee_id: The original employee ID (email)
        company_id: If provided, constructs the scoped vector ID
    """
    try:
        index = create_or_get_index()
        if not index:
            return False

        vector_id = f"{company_id}__employee__{employee_id}" if company_id else employee_id
        index.delete(ids=[vector_id], namespace="employees")
        logger.info(f"Deleted employee: {vector_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting employee: {e}")
        return False


# ============================================================================
# RAG Context Helper — used by the chat endpoint
# ============================================================================

def search_company_context(
    company_id: str,
    query: str,
    top_k_policies: int = 5,
    top_k_employees: int = 3,
    score_threshold: float = 0.25,
) -> str:
    """
    Retrieve the most relevant policy chunks and employee records for a given query,
    scoped to the specific company. Used to build the AI system prompt context.

    Args:
        company_id: The HR's company identifier
        query: The employee's question
        top_k_policies: Number of policy chunks to retrieve
        top_k_employees: Number of employee records to retrieve
        score_threshold: Minimum similarity score

    Returns:
        Formatted context string to inject into the AI prompt, or empty string if none found
    """
    context_parts: List[str] = []

    # --- Policy context ---
    try:
        policy_results = search_policies(
            company_id=company_id,
            query=query,
            top_k=top_k_policies,
            score_threshold=score_threshold,
        )
        if policy_results:
            policy_text_parts = []
            for r in policy_results:
                meta = r.get("metadata", {})
                section = meta.get("section", "Policy")
                policy_type = meta.get("policy_type", "")
                preview = meta.get("content_preview", "")
                score = r.get("score", 0)
                if preview:
                    policy_text_parts.append(
                        f"[{section} — {policy_type}] (relevance: {score:.2f})\n{preview}"
                    )
            if policy_text_parts:
                context_parts.append(
                    "=== RELEVANT POLICY SECTIONS ===\n"
                    + "\n\n".join(policy_text_parts)
                )
    except Exception as e:
        logger.warning(f"Policy search failed for company {company_id}: {e}")

    # --- Employee context (only for HR-type queries) ---
    try:
        employee_results = search_employees(
            company_id=company_id,
            query=query,
            top_k=top_k_employees,
            score_threshold=score_threshold,
        )
        if employee_results:
            emp_text_parts = []
            for r in employee_results:
                meta = r.get("metadata", {})
                name = meta.get("name", "")
                dept = meta.get("department", "")
                designation = meta.get("designation", "")
                emp_id = meta.get("employee_id", "")
                if name:
                    emp_text_parts.append(
                        f"{name} — {designation}, {dept} (contact: {emp_id})"
                    )
            if emp_text_parts:
                context_parts.append(
                    "=== RELEVANT EMPLOYEE RECORDS ===\n"
                    + "\n".join(emp_text_parts)
                )
    except Exception as e:
        logger.warning(f"Employee search failed for company {company_id}: {e}")

    return "\n\n".join(context_parts)


# ============================================================================
# Hybrid Search (for API endpoints)
# ============================================================================

def hybrid_search(
    query: str,
    top_k: int = 5,
    include_policies: bool = True,
    include_employees: bool = True,
    company_id: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Perform hybrid search across policies and employees.

    Args:
        query: Search query text
        top_k: Number of results per namespace
        include_policies: Whether to search policies
        include_employees: Whether to search employees
        company_id: If provided, filter results to this company only

    Returns:
        Dictionary with policy and employee search results
    """
    results = {}

    if include_policies:
        if company_id:
            results["policies"] = search_policies(company_id, query, top_k)
        else:
            # Legacy path: no company filter (for backward compatibility)
            results["policies"] = _search_all_policies(query, top_k)

    if include_employees:
        if company_id:
            results["employees"] = search_employees(company_id, query, top_k)
        else:
            results["employees"] = _search_all_employees(query, top_k)

    return results


def _search_all_policies(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Search policies without company filter (legacy/admin use only)."""
    try:
        query_embedding = embed_text(query)
        if not query_embedding:
            return []
        index = create_or_get_index()
        if not index:
            return []
        results = index.query(
            vector=query_embedding,
            top_k=top_k,
            namespace="policies",
            include_metadata=True,
        )
        return [
            {"id": m["id"], "score": m["score"], "metadata": m.get("metadata", {})}
            for m in results.get("matches", [])
        ]
    except Exception as e:
        logger.error(f"Error searching all policies: {e}")
        return []


def _search_all_employees(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Search employees without company filter (legacy/admin use only)."""
    try:
        query_embedding = embed_text(query)
        if not query_embedding:
            return []
        index = create_or_get_index()
        if not index:
            return []
        results = index.query(
            vector=query_embedding,
            top_k=top_k,
            namespace="employees",
            include_metadata=True,
        )
        return [
            {"id": m["id"], "score": m["score"], "metadata": m.get("metadata", {})}
            for m in results.get("matches", [])
        ]
    except Exception as e:
        logger.error(f"Error searching all employees: {e}")
        return []


# ============================================================================
# Bulk Ingestion from JSON file (with company_id)
# ============================================================================

def ingest_policies_from_file(file_path: str, company_id: str = "default") -> int:
    """
    Ingest HR policies from a JSON file.

    Args:
        file_path: Path to hr_policies.json
        company_id: The company this policy belongs to

    Returns:
        Number of policies successfully ingested
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            policies_data = json.load(f)

        ingested_count = 0

        # Process each policy section
        if "leave_policy" in policies_data:
            leave_policy = policies_data["leave_policy"]
            for leave_type, details in leave_policy.items():
                if leave_type == "section":
                    continue

                doc_id = f"policy_leave_{leave_type}"
                content = json.dumps(details, indent=2)

                if store_policy_document(
                    company_id=company_id,
                    doc_id=doc_id,
                    section=leave_policy.get("section", "Unknown"),
                    policy_type="leave_policy",
                    content=content,
                    metadata={"leave_type": leave_type},
                ):
                    ingested_count += 1

        if "attendance_policy" in policies_data:
            att_policy = policies_data["attendance_policy"]
            doc_id = "policy_attendance"
            content = json.dumps(att_policy, indent=2)

            if store_policy_document(
                company_id=company_id,
                doc_id=doc_id,
                section=att_policy.get("section", "Unknown"),
                policy_type="attendance_policy",
                content=content,
            ):
                ingested_count += 1

        if "salary_policy" in policies_data:
            sal_policy = policies_data["salary_policy"]
            doc_id = "policy_salary"
            content = json.dumps(sal_policy, indent=2)

            if store_policy_document(
                company_id=company_id,
                doc_id=doc_id,
                section=sal_policy.get("section", "Unknown"),
                policy_type="salary_policy",
                content=content,
            ):
                ingested_count += 1

        logger.info(f"Ingested {ingested_count} policies from file for company {company_id}")
        return ingested_count
    except Exception as e:
        logger.error(f"Error ingesting policies from file: {e}")
        return 0


# ============================================================================
# Index Management
# ============================================================================

def clear_namespace(namespace: str) -> bool:
    """
    Clear all vectors in a namespace (for re-ingestion).

    Args:
        namespace: Namespace to clear ("policies" or "employees")

    Returns:
        True if successful, False otherwise
    """
    try:
        index = create_or_get_index()
        if not index:
            return False

        index.delete(delete_all=True, namespace=namespace)
        logger.info(f"Cleared namespace: {namespace}")
        return True
    except Exception as e:
        logger.error(f"Error clearing namespace: {e}")
        return False


def get_index_stats() -> Optional[Dict[str, Any]]:
    """Get statistics about the vector database index."""
    try:
        index = create_or_get_index()
        if not index:
            return None

        stats = index.describe_index_stats()
        return {
            "index_name": settings.PINECONE_INDEX_NAME,
            "dimension": settings.PINECONE_DIMENSION,
            "stats": stats,
        }
    except Exception as e:
        logger.error(f"Error getting index stats: {e}")
        return None
