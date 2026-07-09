"""
main.py — FastAPI application for the TechNovance HR Policy Chatbot.
"""

import logging
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.config import settings
from app.policies import load_policies
from app.schemas import ChatRequest, ChatResponse
from app.bot import AIRateLimitError, AIServiceError, generate_bot_response, close_groq_client
from app.routes_auth import router as auth_router
from app.routes_hr import router as hr_router
from app.routes_vector_db import router as vectordb_router
from app.routes_document_ingest import router as document_router
from app.routes_employee import router as employee_router
from app.routes_admin import router as admin_router
from app.deps import get_current_user
from app.company_policies import (
    get_company_policy_document_text,
    get_company_policy_text_with_rag,
)
from app.cache import rate_limiter, cache_key_for_query, response_cache
from app.utils import generate_request_id, sanitize_input, StructuredLogger

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = StructuredLogger(__name__)
std_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting TechNovance HR Chatbot API (v1.0.0)", environment=settings.ENVIRONMENT)

    if not settings.is_api_configured:
        logger.warning(
            "AI provider not configured — /api/chat will return 503",
            provider=settings.active_provider,
        )

    # ✅ FIX: Don't crash the server if policies are missing
    # The /api/chat endpoint handles this case with a 503
    try:
        load_policies()
        logger.info("HR policy document loaded successfully")
    except FileNotFoundError as exc:
        logger.warning(
            f"Policy file not found: {exc} — /api/chat will return 503 until resolved"
        )
    except Exception as exc:
        logger.error(f"Unexpected error loading policies: {exc}")

    yield

    logger.info("Shutting down HR Chatbot API")
    close_groq_client()
    logger.info("Resources cleaned up")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="TechNovance HR Chatbot API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware — request tracking (registered FIRST = innermost at runtime)
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = generate_request_id()
    request.state.request_id = request_id

    # ✅ FIX: Safe IP extraction with full fallback chain
    forwarded_for = request.headers.get("X-Forwarded-For")
    real_ip = request.headers.get("X-Real-IP")

    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    elif real_ip:
        client_ip = real_ip.strip()
    elif request.client:
        client_ip = request.client.host
    else:
        client_ip = "unknown"

    request.state.client_ip = client_ip

    # Rate limiting
    if not rate_limiter.is_allowed(client_ip):
        std_logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"X-Request-ID": request_id},
            content={
                "detail": "Too many requests. Rate limit exceeded.",
                "request_id": request_id,
            },
        )

    response = await call_next(request)

    remaining = rate_limiter.get_remaining_requests(client_ip)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-RateLimit-Remaining"] = str(remaining["remaining_per_minute"])

    return response


# ---------------------------------------------------------------------------
# CORS — registered LAST = outermost at runtime
# ✅ This ensures CORS headers appear on ALL responses including 500s
# ---------------------------------------------------------------------------
CORS_ORIGINS = settings.allowed_origins_list or []
if not CORS_ORIGINS:
    CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
    std_logger.warning("CORS origins not configured — falling back to localhost:3000 only")

# Always ensure both localhost variants are included
_extra = []
for origin in list(CORS_ORIGINS):
    if "localhost:3000" in origin and "http://127.0.0.1:3000" not in CORS_ORIGINS:
        _extra.append("http://127.0.0.1:3000")
    if "127.0.0.1:3000" in origin and "http://localhost:3000" not in CORS_ORIGINS:
        _extra.append("http://localhost:3000")
CORS_ORIGINS = list(set(CORS_ORIGINS + _extra))

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],  # ✅ FIX: added missing methods
    allow_headers=["Content-Type", "X-Request-ID", "Authorization"],
    expose_headers=["X-Request-ID", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    max_age=3600,
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(hr_router)
app.include_router(vectordb_router)
app.include_router(document_router)
app.include_router(employee_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", status_code=status.HTTP_200_OK, tags=["Operations"])
async def health_check(request: Request):
    return {
        "status": "healthy",
        "company": settings.COMPANY_NAME,
        "api_configured": settings.is_api_configured,
        "environment": settings.ENVIRONMENT,
        "cache_size": response_cache.size,
        "version": "1.0.0",
        "request_id": getattr(request.state, "request_id", None),
    }


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------
@app.post("/api/chat", response_model=ChatResponse, tags=["Chat"])
async def chat_endpoint(
    request: ChatRequest,
    http_request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Send a user message and receive an HR-policy-grounded response.
    - 200  Success
    - 422  Validation error
    - 429  Rate limit exceeded
    - 503  API key not configured
    - 500  Unexpected error
    """
    request_id = getattr(http_request.state, "request_id", "unknown")
    client_ip = getattr(http_request.state, "client_ip", "unknown")

    logger.info(
        "Chat request received",
        request_id=request_id,
        client_ip=client_ip,
        message_len=len(request.message),
        history_len=len(request.history),
    )

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    company_id = user.get("companyId")
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing companyId in token",
        )

    if not settings.is_api_configured:
        logger.warning("Chat request rejected — API not configured", request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"The AI service is not configured for provider '{settings.active_provider}'. "
                "Please contact the system administrator."
            ),
        )

    try:
        sanitized_message = sanitize_input(request.message, max_length=4000)
    except ValueError as exc:
        logger.warning(f"Invalid user input: {exc}", request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    try:
        # Use RAG: fetch semantically-relevant policy chunks from Pinecone
        # scoped to this company, with MongoDB as fallback
        policy_document_text = await get_company_policy_text_with_rag(
            company_id, sanitized_message
        )
        bot_reply = generate_bot_response(
            message=sanitized_message,
            history=request.history,
            policy_document_text=policy_document_text,
        )
        logger.info("Chat response generated", request_id=request_id, response_len=len(bot_reply))

        # Log query to MongoDB
        try:
            from app.db import get_db
            from datetime import datetime, timezone
            db = get_db()
            user_id = user.get("sub") or user.get("id")
            
            # Background task to insert log (or just await it)
            await db.query_logs.insert_one({
                "company_id": company_id,
                "user_id": user_id,
                "role": user.get("role"),
                "question": sanitized_message,
                "answer": bot_reply,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as log_exc:
            logger.error(f"Failed to log query: {log_exc}")

        return ChatResponse(response=bot_reply)

    except AIRateLimitError as exc:
        logger.warning(f"Rate-limit error: {exc}", request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="API provider rate limit exceeded. Please try again later.",
        )
    except AIServiceError as exc:
        logger.error(f"AI service error: {exc}", request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service error. Please try again later.",
        )
    except ValueError as exc:
        logger.error(f"Configuration error: {exc}", request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service configuration error. Please contact administrator.",
        )
    except Exception as exc:
        logger.error(f"Unhandled error in /api/chat: {exc}", request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again.",
        )


# ---------------------------------------------------------------------------
# Custom 422 handler
# ---------------------------------------------------------------------------
@app.exception_handler(422)
async def validation_exception_handler(request: Request, exc):
    return JSONResponse(
        status_code=422,
        content={"error": "Validation error", "details": str(exc)},
    )


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=9000, reload=True)