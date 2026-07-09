import json
import logging
import os
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


def _resolve_policy_path() -> str:
    """Return the absolute path to hr_policies.json regardless of the CWD."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "data", "hr_policies.json"))


@lru_cache(maxsize=1)
def load_policies() -> dict[str, Any]:
    """Load and cache the HR policy JSON from disk (legacy single-company mode)."""
    # LRU cache (size=1) ensures the file is read exactly once per process
    # lifetime — subsequent calls return the cached dict at O(1) speed.

    path = _resolve_policy_path()
    logger.info("Loading HR policies from %s", path)

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"HR policy file not found: '{path}'. "
            "Ensure 'backend/data/hr_policies.json' exists before starting the server."
        )

    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    logger.info("HR policies loaded — %d top-level sections.", len(data))
    return data


def get_policy_document_text() -> str:
    """Return the full policy dict serialised as an indented JSON string for prompt injection."""
    return json.dumps(load_policies(), indent=2, ensure_ascii=False)

