"""Prompt guardrails applied before any agent runs."""

import re

BLOCK_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)", re.IGNORECASE),
    re.compile(r"(reveal|show|print|repeat)\s+(your\s+)?(system|developer)\s+prompt", re.IGNORECASE),
    re.compile(r"(bypass|override|disable)\s+(safety|guardrails|policy|policies|rules)", re.IGNORECASE),
    re.compile(r"jailbreak|dan\s+mode|do\s+anything\s+now", re.IGNORECASE),
    re.compile(r"act\s+as\s+(a\s+)?(lawyer|doctor|hacker|jailbroken\s+ai)", re.IGNORECASE),
    re.compile(r"pretend\s+(to\s+be|you\s+are)\s+(unrestricted|jailbroken|evil)", re.IGNORECASE),
    re.compile(r"\b(murder|bomb|weapon|hate\s*speech|racist|sexist|porn|sex\s*chat|explicit)\b", re.IGNORECASE),
    re.compile(r"\bkill\s+(him|her|them|someone|people|myself)\b", re.IGNORECASE),
]

BLOCKED_MESSAGE = (
    "Request blocked by safety policy. Please ask a finance or startup question without "
    "jailbreak attempts or harmful content."
)


def is_blocked(text: str) -> bool:
    text = (text or "").strip()
    return bool(text) and any(p.search(text) for p in BLOCK_PATTERNS)
