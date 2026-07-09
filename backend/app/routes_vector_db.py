"""
routes_vector_db.py — Vector Database API Routes

Endpoints for storing, searching, and managing HR data in Pinecone.
All operations are scoped by company_id (from the JWT or explicit request field)
so that one HR's data is never visible to another company.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, Query, status
import os
from typing import Optional

from app.vector_db import (
    store_policy_document,
    store_employee_data,
    search_policies,
    search_employees,
    hybrid_search,
    delete_policy,
    delete_employee,
    ingest_policies_from_file,
    get_index_stats,
    clear_namespace,
)
from app.schemas import (
    StorePolicyRequest,
    StoreEmployeeRequest,
    SearchPolicyRequest,
    SearchEmployeeRequest,
    SearchResponse,
    IngestResponse,
    DeleteRequest,
    IndexStats,
    SearchResult,
)
from app.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/vectordb", tags=["Vector Database"])


# ============================================================================
# Policy Management Endpoints
# ============================================================================

@router.post("/policies/store", response_model=dict, status_code=201)
async def store_policy(
    request: StorePolicyRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Store a policy document in the vector database.

    The company_id is taken from the authenticated user's JWT so that
    policies are always scoped to the correct HR organisation.
    """
    company_id = current_user.get("companyId")
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="companyId not found in token",
        )

    try:
        success = store_policy_document(
            company_id=company_id,
            doc_id=request.doc_id,
            section=request.section,
            policy_type=request.policy_type,
            content=request.content,
            metadata=request.metadata,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store policy document",
            )

        return {
            "success": True,
            "message": f"Policy document '{request.doc_id}' stored successfully for company '{company_id}'",
            "doc_id": request.doc_id,
            "company_id": company_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error storing policy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/policies/search", response_model=dict)
async def search_policy(
    query: str,
    top_k: int = 5,
    score_threshold: float = 0.3,
    current_user: dict = Depends(get_current_user),
):
    """
    Search for policies using semantic similarity.

    Results are filtered to the authenticated user's company only.
    """
    company_id = current_user.get("companyId")
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="companyId not found in token",
        )

    if not query or len(query.strip()) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query must be at least 2 characters",
        )

    try:
        results = search_policies(
            company_id=company_id,
            query=query,
            top_k=min(top_k, 20),
            score_threshold=max(0.0, min(score_threshold, 1.0)),
        )

        return {
            "query": query,
            "company_id": company_id,
            "results": results,
            "count": len(results),
        }
    except Exception as e:
        logger.error(f"Error searching policies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search operation failed",
        )


@router.delete("/policies/{doc_id}")
async def delete_policy_endpoint(
    doc_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Delete a policy document from the vector database.

    Uses the authenticated user's company_id to construct the scoped vector ID.
    """
    company_id = current_user.get("companyId")

    try:
        success = delete_policy(doc_id=doc_id, company_id=company_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete policy",
            )

        return {
            "success": True,
            "message": f"Policy '{doc_id}' deleted successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting policy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# ============================================================================
# Employee Data Management Endpoints
# ============================================================================

@router.post("/employees/store", response_model=dict, status_code=201)
async def store_employee(
    request: StoreEmployeeRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Store employee data in the vector database.

    The company_id is taken from the authenticated user's JWT.
    """
    company_id = current_user.get("companyId")
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="companyId not found in token",
        )

    try:
        success = store_employee_data(
            company_id=company_id,
            employee_id=request.employee_id,
            name=request.name,
            department=request.department,
            designation=request.designation,
            summary=request.summary,
            metadata=request.metadata,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store employee data",
            )

        return {
            "success": True,
            "message": f"Employee '{request.name}' stored successfully for company '{company_id}'",
            "employee_id": request.employee_id,
            "company_id": company_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error storing employee: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/employees/search", response_model=dict)
async def search_employee(
    query: str,
    top_k: int = 5,
    score_threshold: float = 0.3,
    current_user: dict = Depends(get_current_user),
):
    """
    Search for employees using semantic similarity.

    Results are filtered to the authenticated user's company only.
    """
    company_id = current_user.get("companyId")
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="companyId not found in token",
        )

    if not query or len(query.strip()) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query must be at least 2 characters",
        )

    try:
        results = search_employees(
            company_id=company_id,
            query=query,
            top_k=min(top_k, 20),
            score_threshold=max(0.0, min(score_threshold, 1.0)),
        )

        return {
            "query": query,
            "company_id": company_id,
            "results": results,
            "count": len(results),
        }
    except Exception as e:
        logger.error(f"Error searching employees: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search operation failed",
        )


@router.delete("/employees/{employee_id}")
async def delete_employee_endpoint(
    employee_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Delete an employee record from the vector database.

    Uses the authenticated user's company_id to construct the scoped vector ID.
    """
    company_id = current_user.get("companyId")

    try:
        success = delete_employee(employee_id=employee_id, company_id=company_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete employee",
            )

        return {
            "success": True,
            "message": f"Employee '{employee_id}' deleted successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting employee: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# ============================================================================
# Hybrid Search Endpoint
# ============================================================================

@router.get("/search", response_model=dict)
async def hybrid_search_endpoint(
    query: str,
    top_k: int = 5,
    include_policies: bool = True,
    include_employees: bool = True,
    score_threshold: float = 0.3,
    current_user: dict = Depends(get_current_user),
):
    """
    Perform hybrid search across both policies and employees.

    Results are filtered to the authenticated user's company only.
    """
    company_id = current_user.get("companyId")
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="companyId not found in token",
        )

    if not query or len(query.strip()) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query must be at least 2 characters",
        )

    try:
        results = hybrid_search(
            query=query,
            top_k=min(top_k, 20),
            include_policies=include_policies,
            include_employees=include_employees,
            company_id=company_id,
        )

        # Filter by score threshold
        filtered_results: dict = {}
        if include_policies:
            filtered_results["policies"] = [
                r for r in results.get("policies", [])
                if r.get("score", 0) >= score_threshold
            ]

        if include_employees:
            filtered_results["employees"] = [
                r for r in results.get("employees", [])
                if r.get("score", 0) >= score_threshold
            ]

        return {
            "query": query,
            "company_id": company_id,
            **filtered_results,
            "total": sum(len(v) for v in filtered_results.values()),
        }
    except Exception as e:
        logger.error(f"Error in hybrid search: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search operation failed",
        )


# ============================================================================
# Data Ingestion Endpoints
# ============================================================================

@router.post("/ingest/policies", response_model=dict)
async def ingest_policies(
    current_user: dict = Depends(get_current_user),
):
    """
    Ingest HR policies from the default hr_policies.json file.

    Policies are tagged with the authenticated user's company_id.
    """
    company_id = current_user.get("companyId")
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="companyId not found in token",
        )

    try:
        # Path to the policies file
        policies_file = os.path.join(
            os.path.dirname(__file__),
            "..",
            "data",
            "hr_policies.json",
        )

        if not os.path.exists(policies_file):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policies file not found",
            )

        count = ingest_policies_from_file(policies_file, company_id=company_id)

        return {
            "success": True,
            "count": count,
            "company_id": company_id,
            "message": f"Successfully ingested {count} policies for company '{company_id}'",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ingesting policies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# ============================================================================
# Index Management Endpoints
# ============================================================================

@router.get("/index/stats")
async def get_stats():
    """
    Get statistics about the vector database index.

    Returns information about the index including dimension and vector count.
    """
    try:
        stats = get_index_stats()

        if not stats:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to retrieve index statistics",
            )

        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting index stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve statistics",
        )


@router.post("/index/clear")
async def clear_index(
    namespace: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Clear all vectors in a namespace (for re-ingestion).

    Parameters:
    - namespace: "policies" or "employees"
    """
    if namespace not in ["policies", "employees"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Namespace must be 'policies' or 'employees'",
        )

    try:
        success = clear_namespace(namespace)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to clear namespace",
            )

        return {
            "success": True,
            "message": f"Namespace '{namespace}' cleared successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing namespace: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health")
async def health_check():
    """Check if vector database is accessible and return connection status."""
    try:
        stats = get_index_stats()
        return {
            "status": "healthy" if stats else "degraded",
            "vector_db_connected": stats is not None,
            "index_name": stats.get("index_name") if stats else None,
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "vector_db_connected": False,
            "error": str(e),
        }
