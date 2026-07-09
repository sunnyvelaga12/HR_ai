import logging
import os
from urllib.parse import quote_plus

from app.config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_mongodb_client():
    """Create (or reuse) an async MongoDB client with pooling.

    Uses motor (async). We keep a module-level singleton so the app can
    reuse connections efficiently.

    To avoid RFC 3986 escaping issues (e.g. @ : / ? # % in usernames/passwords),
    credentials are read from separate env vars and URL-encoded.
    """
    global _client
    if _client is not None:
        return _client

    try:
        from motor.motor_asyncio import AsyncIOMotorClient
    except ImportError as exc:
        raise RuntimeError(
            "motor is not installed. Install backend dependencies before running."
        ) from exc

    # Backward compatible fallback: if MONGODB_URI is explicitly provided,
    # use it as-is.
    fallback_uri = os.getenv("MONGODB_URI") or settings.__dict__.get("MONGODB_URI")

    mongo_user = os.getenv("MONGO_USER") or settings.__dict__.get("MONGO_USER", "")
    mongo_password = os.getenv("MONGO_PASSWORD") or settings.__dict__.get(
        "MONGO_PASSWORD", ""
    )
    mongo_host = os.getenv("MONGO_HOST") or settings.__dict__.get("MONGO_HOST", "")
    mongo_db = os.getenv("MONGO_DB") or settings.__dict__.get("MONGO_DB", "")

    mongo_auth_source = os.getenv("MONGO_AUTH_SOURCE") or settings.__dict__.get(
        "MONGO_AUTH_SOURCE", ""
    )

    # Prefer separated credentials when present; otherwise fall back.
    if mongo_user and mongo_password and mongo_host and mongo_db:
        quoted_user = quote_plus(mongo_user)
        quoted_password = quote_plus(mongo_password)

        # Construct final URI safely.
        # Host should typically look like: cluster0.xxxxx.mongodb.net
        # (without scheme).
        auth_source_qs = (
            f"&authSource={quote_plus(mongo_auth_source)}"
            if mongo_auth_source
            else ""
        )
        uri = (
            f"mongodb+srv://{quoted_user}:{quoted_password}@{mongo_host}/{mongo_db}"
            f"?retryWrites=true&w=majority{auth_source_qs}"
        )
    else:
        if not fallback_uri:
            missing = [
                "MONGO_USER",
                "MONGO_PASSWORD",
                "MONGO_HOST",
                "MONGO_DB",
            ]
            provided = {
                "MONGO_USER": bool(mongo_user),
                "MONGO_PASSWORD": bool(mongo_password),
                "MONGO_HOST": bool(mongo_host),
                "MONGO_DB": bool(mongo_db),
            }
            missing = [k for k, ok in provided.items() if not ok]
            raise RuntimeError(
                "MongoDB configuration is missing required env vars. "
                f"Missing: {', '.join(missing)}. "
                "Set separated vars (MONGO_USER, MONGO_PASSWORD, MONGO_HOST, MONGO_DB) "
                "to avoid URI escaping issues. "
                "Alternatively, set MONGODB_URI (may fail if username/password contain special characters)."
            )

        uri = fallback_uri

    # Initialize client with connection pooling and SSL fix for Windows/Atlas
    tls_kwargs = {
        "tls": True,
        "tlsAllowInvalidCertificates": True,
    }
    try:
        import certifi

        tls_kwargs["tlsCAFile"] = certifi.where()
    except ImportError:
        pass

    _client = AsyncIOMotorClient(
        uri,
        maxPoolSize=50,
        minPoolSize=2,
        maxIdleTimeMS=60000,
        serverSelectionTimeoutMS=15000,
        connectTimeoutMS=10000,
        socketTimeoutMS=30000,
        **tls_kwargs,
    )
    logger.info("MongoDB client initialized with connection pooling")
    return _client


def get_db():
    """Return an async database handle.

    Mongo Atlas connection string should include a default database.
    If not, we fall back to 'hrbot'.
    """
    client = _get_mongodb_client()

    # motor/AsyncIOMotorClient exposes get_default_database() when DB is in URI.
    try:
        db = client.get_default_database()
        if db is not None:
            return db
    except Exception:
        pass

    return client["hrbot"]
