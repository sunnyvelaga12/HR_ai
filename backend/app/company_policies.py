"""
company_policies.py — Per-company policy retrieval with RAG support.

Retrieval strategy (in order):
1. If Pinecone is configured and has relevant chunks → use semantic RAG search
   filtered by company_id (fastest, most relevant for specific queries)
2. If Pinecone returns nothing → fall back to the full MongoDB policy text
3. If neither exists → return a helpful "no policy" placeholder
"""

import json
import logging
from typing import Any

from app.db import get_db

logger = logging.getLogger(__name__)


async def get_company_policy_document(company_id: str) -> dict[str, Any]:
    """Fetch the policy document for a specific company from MongoDB.

    Supports two storage formats:
      1. File-upload format (new): content = { "full_text": "<extracted text>", ... }
      2. JSON-upload format (legacy): content = { <raw policy dict> }

    Falls back to the companies collection if no policies entry exists.
    """
    db = get_db()
    doc = await db.policies.find_one({"companyId": company_id})
    if doc and "content" in doc:
        return doc["content"]

    # Fallback: companies collection (legacy)
    company = await db.companies.find_one({"_id": company_id})
    if company and "policies" in company:
        return company["policies"]

    raise KeyError(f"Policy document not found for companyId={company_id}")


async def get_company_policy_document_text(company_id: str) -> str:
    """Return the full policy document as plain text (MongoDB-based, no RAG).

    Handles both the new file-upload format (returns full_text directly)
    and the legacy JSON format (JSON-serialises the dict).
    """
    try:
        data = await get_company_policy_document(company_id)
    except KeyError:
        return "(No policy document has been uploaded for this company yet.)"

    # New file-upload format: content has a "full_text" key with extracted text
    if isinstance(data, dict) and "full_text" in data:
        return data["full_text"]

    # Legacy JSON format: serialise the whole dict
    if isinstance(data, dict):
        return json.dumps(data, indent=2, ensure_ascii=False)

    # Raw string fallback
    return str(data)


async def get_company_policy_text_with_rag(company_id: str, query: str) -> str:
    """
    Return the most relevant policy context for a given query using RAG (Pinecone).

    Strategy:
    - Try Pinecone semantic search scoped to company_id
    - If Pinecone returns results → use them (best relevance for specific queries)
    - If Pinecone is empty/unavailable → fall back to full MongoDB policy text

    Args:
        company_id: The HR's company identifier
        query: The employee's question (used for semantic matching)

    Returns:
        Policy context string ready to inject into the AI system prompt
    """
    rag_context = ""

    # Attempt Pinecone RAG retrieval
    try:
        from app.vector_db import search_company_context
        rag_context = search_company_context(
            company_id=company_id,
            query=query,
            top_k_policies=6,
            top_k_employees=3,
            score_threshold=0.25,
        )
    except Exception as e:
        logger.warning(
            f"Vector DB search failed for company {company_id}, "
            f"falling back to MongoDB: {e}"
        )

    if rag_context and rag_context.strip():
        logger.info(
            f"Using RAG context ({len(rag_context)} chars) for company {company_id}"
        )
        return rag_context

    # Fallback: full MongoDB policy text
    logger.info(
        f"Pinecone returned no results for company {company_id}, "
        f"using MongoDB full-text fallback"
    )
    return await get_company_policy_document_text(company_id)
