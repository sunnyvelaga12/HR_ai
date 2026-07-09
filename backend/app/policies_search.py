"""
policies_search.py — lightweight policy section selector to limit prompt size.

This module provides a small, dependency-free function that selects the most
relevant sections for a user's query using simple keyword matching. It is used
by the bot to avoid sending the entire policy document on every request and
thus prevents hitting token-per-minute limits on providers like GROQ.
"""

import json
import re
from typing import Any
from app.policies import load_policies


def find_relevant_sections(query: str, max_chars: int = 3000) -> str:
    """
    Return a concatenated text of the most relevant policy sections for `query`.

    This performs a simple keyword-match ranking and returns enough sections
    without exceeding `max_chars`. If no matches are found, it returns a
    compact summary (first few top-level sections).
    """
    policies = load_policies()
    query = (query or "").lower()
    keywords = [w for w in re.findall(r"\w+", query) if len(w) > 2]

    def section_text(sec_key: str, sec_val: Any) -> str:
        return f"{sec_key}: {json.dumps(sec_val, ensure_ascii=False)}"

    scored: list[tuple[int, str]] = []
    for key, val in policies.items():
        txt = section_text(key, val).lower()
        score = sum(txt.count(k) for k in keywords) if keywords else 0
        scored.append((score, key))

    scored.sort(key=lambda x: x[0], reverse=True)

    selected = []
    total_len = 0
    for score, key in scored:
        if score == 0 and selected:
            break
        snippet = f"\nSection: {key}\n{section_text(key, policies[key])}\n"
        if total_len + len(snippet) > max_chars:
            continue
        selected.append(snippet)
        total_len += len(snippet)

    if not selected:
        keys = list(policies.keys())[:6]
        summary = {k: policies[k] for k in keys}
        return json.dumps(summary, indent=2, ensure_ascii=False)

    return "\n".join(selected)
