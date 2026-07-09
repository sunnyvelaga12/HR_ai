"""
cache.py — Production-grade caching and rate limiting for TechNovance HR Chatbot.

Features:
  - Redis / LRU cache for query responses (time-boxed)
  - Sliding window rate limiter (per-IP)
  - Thread-safe implementations
"""

import hashlib
import logging
import time
import os
from collections import defaultdict, OrderedDict
from threading import Lock
from typing import Any, Optional

import redis
from app.config import settings

logger = logging.getLogger(__name__)

# Try to connect to Redis
redis_url = os.environ.get("REDIS_URL")
redis_client = None
if redis_url:
    try:
        redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        redis_client.ping()
        logger.info("Connected to Redis for caching and rate limiting.")
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {e}. Falling back to in-memory.")
        redis_client = None


class TimeboxedCache:
    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self.lock = Lock()

    def _hash_key(self, key: str) -> str:
        return hashlib.md5(key.encode()).hexdigest()[:16]

    def get(self, key: str) -> Optional[Any]:
        if redis_client:
            try:
                return redis_client.get(f"cache:{key}")
            except Exception as e:
                logger.error(f"Redis get error: {e}")
                return None
        
        with self.lock:
            if key not in self.cache:
                return None
            value, timestamp = self.cache[key]
            if time.time() - timestamp > self.ttl_seconds:
                del self.cache[key]
                return None
            self.cache.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        if redis_client:
            try:
                redis_client.setex(f"cache:{key}", self.ttl_seconds, str(value))
                return
            except Exception as e:
                logger.error(f"Redis set error: {e}")
                
        with self.lock:
            if key in self.cache:
                del self.cache[key]
            self.cache[key] = (value, time.time())
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)

    def clear(self) -> None:
        if redis_client:
            try:
                for key in redis_client.scan_iter("cache:*"):
                    redis_client.delete(key)
            except: pass
        with self.lock:
            self.cache.clear()

    @property
    def size(self) -> int:
        if redis_client:
            return 0 # approximate
        with self.lock:
            return len(self.cache)


class SlidingWindowRateLimiter:
    def __init__(self, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        self.rpm_limit = requests_per_minute
        self.rph_limit = requests_per_hour
        self.windows: dict[str, list[float]] = defaultdict(list)
        self.lock = Lock()

    def is_allowed(self, client_id: str) -> bool:
        if redis_client:
            try:
                now = time.time()
                pipe = redis_client.pipeline()
                
                # per minute
                m_key = f"rate:{client_id}:minute"
                pipe.zremrangebyscore(m_key, 0, now - 60)
                pipe.zadd(m_key, {str(now): now})
                pipe.zcard(m_key)
                pipe.expire(m_key, 60)
                
                # per hour
                h_key = f"rate:{client_id}:hour"
                pipe.zremrangebyscore(h_key, 0, now - 3600)
                pipe.zadd(h_key, {str(now): now})
                pipe.zcard(h_key)
                pipe.expire(h_key, 3600)
                
                results = pipe.execute()
                recent_minute = results[2]
                recent_hour = results[6]
                
                if recent_minute > self.rpm_limit or recent_hour > self.rph_limit:
                    return False
                return True
            except Exception as e:
                logger.error(f"Redis rate limit error: {e}")
                # fallback
                
        with self.lock:
            now = time.time()
            minute_ago = now - 60
            hour_ago = now - 3600
            self.windows[client_id] = [ts for ts in self.windows[client_id] if ts > hour_ago]
            recent_minute = [ts for ts in self.windows[client_id] if ts > minute_ago]
            if len(recent_minute) >= self.rpm_limit:
                return False
            if len(self.windows[client_id]) >= self.rph_limit:
                return False
            self.windows[client_id].append(now)
            return True

    def get_remaining_requests(self, client_id: str) -> dict[str, int]:
        if redis_client:
            try:
                recent_minute = redis_client.zcard(f"rate:{client_id}:minute") or 0
                recent_hour = redis_client.zcard(f"rate:{client_id}:hour") or 0
                return {
                    "remaining_per_minute": max(0, self.rpm_limit - recent_minute),
                    "remaining_per_hour": max(0, self.rph_limit - recent_hour),
                }
            except:
                pass
                
        with self.lock:
            now = time.time()
            minute_ago = now - 60
            hour_ago = now - 3600
            recent_minute = len([ts for ts in self.windows.get(client_id, []) if ts > minute_ago])
            recent_hour = len([ts for ts in self.windows.get(client_id, []) if ts > hour_ago])
            return {
                "remaining_per_minute": max(0, self.rpm_limit - recent_minute),
                "remaining_per_hour": max(0, self.rph_limit - recent_hour),
            }


# Global instances
response_cache = TimeboxedCache(
    max_size=100,
    ttl_seconds=settings.CACHE_TTL_SECONDS,
)
rate_limiter = SlidingWindowRateLimiter(
    requests_per_minute=settings.RATE_LIMIT_REQUESTS_PER_MINUTE,
    requests_per_hour=settings.RATE_LIMIT_REQUESTS_PER_HOUR,
)

# Admin-specific rate limiter — much stricter (10 req/min, 50 req/hour)
# Protects /api/admin/* endpoints from brute-force and enumeration attacks
admin_rate_limiter = SlidingWindowRateLimiter(
    requests_per_minute=settings.ADMIN_RATE_LIMIT_PER_MINUTE,
    requests_per_hour=50,
)

def cache_key_for_query(message: str, history_len: int) -> str:
    key_parts = [message.strip().lower(), str(history_len)]
    combined = "|".join(key_parts)
    return hashlib.md5(combined.encode()).hexdigest()
