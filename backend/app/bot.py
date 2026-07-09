import httpx
import logging
import warnings
from typing import List, Optional

from app.config import settings
from app.policies import get_policy_document_text
from app.policies_search import find_relevant_sections
from app.schemas import ChatMessage
from app.utils import retry_with_backoff

logger = logging.getLogger(__name__)

try:
    import google.api_core.exceptions as google_exceptions
except ImportError:
    google_exceptions = None

try:
    from google import genai
    from google.genai.errors import ClientError as GenaiClientError
    _USE_NEW_GENAI = True
except ImportError:
    import google.generativeai as genai
    from google.api_core.exceptions import GoogleAPIError as GenaiClientError
    _USE_NEW_GENAI = False
    warnings.warn(
        "google.generativeai is deprecated. Install google-genai and switch to google.genai for production.",
        DeprecationWarning,
        stacklevel=2,
    )


class AIServiceError(RuntimeError):
    """Raised when the configured AI provider returns a service error."""


class AIRateLimitError(AIServiceError):
    """Raised when the configured AI provider is rate-limited or quota-exhausted."""


# Global connection pool for GROQ (production optimization)
_groq_client: Optional[httpx.Client] = None


def _get_groq_client() -> httpx.Client:
    """
    Get or create a reusable GROQ HTTP client.
    
    Connection pooling eliminates per-request overhead.
    Thread-safe singleton pattern.
    """
    global _groq_client
    
    if _groq_client is None:
        if not settings.GROQ_API_KEY or settings.GROQ_API_KEY == "YOUR_GROQ_API_KEY":
            raise ValueError(
                "GROQ_API_KEY is not configured. Please set a valid key in backend/.env before starting the server."
            )
        
        _groq_client = httpx.Client(
            base_url=settings.GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "TechNovance-HRBot/1.0",
            },
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
        logger.info("GROQ HTTP client initialized with connection pooling")
    
    return _groq_client


@retry_with_backoff(
    max_retries=3,
    base_backoff_ms=100,
    exponential_base=2.0,
)
def _call_groq_chat(message: str, conversation_history: list[dict[str, str]]) -> str:
    """
    Call GROQ API with automatic retry on transient failures.
    
    Exponential backoff protects against rate limits and transient network issues.
    """
    payload = {
        "model": settings.GROQ_MODEL_NAME,
        "messages": conversation_history,
        "temperature": 0.0,
        "max_tokens": 1024,
    }

    try:
        client = _get_groq_client()
        response = client.post("/chat/completions", json=payload)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        if exc.response.status_code == 429:
            raise AIRateLimitError(
                f"GROQ rate limit exceeded. Please try again later."
            ) from exc
        if exc.response.status_code >= 500:
            raise AIServiceError(
                f"GROQ API error ({exc.response.status_code}): Server error"
            ) from exc
        raise AIServiceError(
            f"GROQ API error ({exc.response.status_code})"
        ) from exc
    except httpx.RequestError as exc:
        raise AIServiceError(
            f"Unable to contact GROQ API: Connection error"
        ) from exc

    try:
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise AIServiceError("GROQ API response malformed: missing choices.")

        message_data = choices[0].get("message") or {}
        content = message_data.get("content") or choices[0].get("text") or ""
        if isinstance(content, dict):
            content = content.get("content", "")

        return (content or "").strip()
    except (KeyError, TypeError) as exc:
        raise AIServiceError(f"Failed to parse GROQ response: {str(exc)}") from exc


def close_groq_client() -> None:
    """Close the GROQ client connection pool (cleanup on shutdown)."""
    global _groq_client
    if _groq_client is not None:
        _groq_client.close()
        _groq_client = None
        logger.info("GROQ HTTP client closed")

# System Prompt Template
SYSTEM_PROMPT = """
You are HRBot, the official HR Policy Assistant for TechNovance Solutions Pvt. Ltd.

YOUR RULES — FOLLOW THESE WITHOUT EXCEPTION:
1. ONLY answer from the HR policy document provided below. Do NOT use any outside knowledge about HR practices, other companies, or general policies.
2. ALWAYS cite the specific policy section in your answer. Format the citation clearly, for example: "Per Section X.Y (Policy Name)..." or "Per Section X — [Name]...".
3. If a question is NOT covered in the policy document, respond EXACTLY:
   "This is not covered in the policy document. Please reach out to HR directly at hr@technovance.com or call +91-40-2345-6789."
   Do NOT try to answer it using external information or generate a helpful-sounding but unsanctioned answer.
4. If someone asks about their PERSONAL data (their leave balance, their salary, their appraisal score, their joining date, etc.), say:
   "I can only provide policy information. For personal data, please log in to the HRMS portal at https://hrms.technovance.internal or contact HR at hr@technovance.com."
5. For SCENARIO-BASED questions (e.g., "I have a doctor's appointment tomorrow, what leave should I apply?"), identify the correct leave type from the policy document, explain the eligibility, and mention the approval process.
6. Keep answers concise but complete. Use bullet points for multi-part answers.
7. Be professional, warm, and helpful. You represent the HR department.
8. If a question is ambiguous, ask ONE clarifying question before answering.

THE COMPLETE HR POLICY DOCUMENT:
{policy_document}
"""


def get_system_instruction(
    query: str, *, policy_document_text: str | None = None
) -> str:
    """Build system instruction.

    If `policy_document_text` is provided, we inject it directly.
    Otherwise we use the legacy single-company file-based selection.
    """
    if policy_document_text is not None:
        return SYSTEM_PROMPT.format(policy_document=policy_document_text)

    try:
        policy_doc = find_relevant_sections(query, max_chars=3000)
    except Exception:
        policy_doc = get_policy_document_text()

    return SYSTEM_PROMPT.format(policy_document=policy_doc)




def _build_history(history: List[ChatMessage]) -> list[dict[str, str]]:
    """Limit history to the most recent 10 messages and map roles for the Gemini client."""
    return [
        {"role": "user" if msg.role == "user" else "assistant", "content": msg.content}
        for msg in history[-10:]
    ]


def _create_genai_client():
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
        raise ValueError(
            "GEMINI_API_KEY is not configured. Please set a valid key in backend/.env before starting the server."
        )

    if _USE_NEW_GENAI:
        return genai.Client(api_key=settings.GEMINI_API_KEY)

    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai


def generate_bot_response(
    message: str,
    history: List[ChatMessage],
    *,
    policy_document_text: str | None = None,
) -> str:

    """

    Queries the configured AI provider using the model with strict system instruction.
    
    Features:
    - Caches responses for identical queries with same history length
    - Supports multi-turn chat history
    - Returns plain text response
    """
    from app.cache import cache_key_for_query, response_cache
    
    system_instruction = get_system_instruction(
        message, policy_document_text=policy_document_text
    )

    
    # Try cache first (especially for common HR questions)
    cache_key = cache_key_for_query(message, len(history))
    cached_response = response_cache.get(cache_key)
    if cached_response:
        logger.info("Cache hit for query", extra={"message_len": len(message)})
        return cached_response

    # Include the system prompt at the head of history to enforce policy rules.
    conversation_history = [
        {"role": "system", "content": system_instruction},
        *(_build_history(history)),
    ]

    if settings.active_provider == "groq":
        response = _call_groq_chat(message=message, conversation_history=conversation_history)
    else:
        client = _create_genai_client()
        try:
            if _USE_NEW_GENAI:
                gemini_history = [
                    {"role": item["role"] if item["role"] != "assistant" else "model", "parts": [{"text": item["content"]}]}
                    for item in _build_history(history)
                ]
                chat = client.chats.create(
                    model=settings.AI_MODEL_NAME,
                    history=gemini_history,
                    config={"system_instruction": system_instruction}
                )
                response = chat.send_message(message)
                response = response.text or ""
            else:
                gemini_history = [
                    {"role": item["role"] if item["role"] != "assistant" else "model", "parts": [item["content"]]}
                    for item in _build_history(history)
                ]
                model = genai.GenerativeModel(
                    model_name=settings.AI_MODEL_NAME,
                    system_instruction=system_instruction,
                )
                chat = model.start_chat(history=gemini_history)
                api_response = chat.send_message(message)
                response = api_response.text
        except Exception as exc:
            # Map Google API errors to our custom error types
            if google_exceptions is not None:
                if isinstance(exc, google_exceptions.ResourceExhausted):
                    raise AIRateLimitError(
                        "Gemini API quota exceeded. Please try again later."
                    ) from exc
                if isinstance(exc, (google_exceptions.Unauthenticated, google_exceptions.InvalidArgument)):
                    raise AIServiceError(
                        f"Gemini API configuration error: {str(exc)}"
                    ) from exc
                if isinstance(exc, google_exceptions.GoogleAPIError):
                    raise AIServiceError(
                        f"Gemini API error: {str(exc)}"
                    ) from exc
            # Re-raise if not a Google API error
            raise

    # Cache the response for future identical queries
    response_cache.set(cache_key, response)
    return response
