"""R code and JSON extraction from markdown-fenced LLM responses.

LLMs typically return R code or JSON wrapped in markdown fences with
explanatory text.  This module reliably extracts code blocks and JSON
objects so the orchestrator can pass clean data to downstream consumers.
"""

import json
import re

# Matches fenced code blocks with optional ``r`` / ``R`` language tag.
_CODE_BLOCK_RE = re.compile(r"```(?:r|R)?[^\S\n]*\n(.*?)\n```", re.DOTALL)

# Common R patterns used to detect "bare" R code (no fences).
_R_PATTERNS: tuple[str, ...] = (
    "library(",
    "<-",
    "function(",
    "data.frame(",
    "read.csv(",
    "read_csv(",
    "install.packages(",
    "survfit(",
    "coxph(",
    "ggplot(",
    "Surv(",
    "stopifnot(",
    "source(",
)


def contains_r_patterns(text: str) -> bool:
    """Return ``True`` if *text* looks like R code.

    Checks for the presence of common R language constructs such as
    ``library()``, the assignment arrow ``<-``, and ``function()``.
    """
    return any(pattern in text for pattern in _R_PATTERNS)


def extract_r_code(response_text: str) -> str | None:
    """Extract R code from an LLM response.

    Handles the following cases (see PITFALLS.md integration gotchas):

    1. Code inside ````r ... ```` or ````R ... ```` fenced blocks.
    2. Code inside unfenced ```````` ... ```````` blocks (no language tag) --
       included only if the block content looks like R code.
    3. Multiple code blocks -- concatenated in order, separated by blank lines.
    4. Explanatory text between blocks -- stripped; only code is kept.
    5. No code blocks at all -- if the full text contains common R patterns,
       the entire (stripped) text is returned.
    6. Returns ``None`` when no R code can be identified.

    Args:
        response_text: The raw text returned by an LLM.

    Returns:
        Extracted R code as a single string, or ``None`` if no R code was
        found.
    """
    if not response_text or not response_text.strip():
        return None

    blocks = _CODE_BLOCK_RE.findall(response_text)

    if blocks:
        # Filter out empty blocks and strip each block.
        non_empty = [b.strip() for b in blocks if b.strip()]
        if non_empty:
            return "\n\n".join(non_empty)
        # All blocks were empty -- fall through to bare-text check.

    # No fenced blocks found (or all were empty).  Check if the raw text
    # itself is R code.
    stripped = response_text.strip()
    if contains_r_patterns(stripped):
        return stripped

    return None


# ---------------------------------------------------------------------------
# JSON extraction from LLM responses
# ---------------------------------------------------------------------------

_JSON_BLOCK_RE = re.compile(r"```(?:json)?[^\S\n]*\n(.*?)\n```", re.DOTALL)


def extract_json(response_text: str) -> dict | None:
    """Extract a JSON object from an LLM response.

    Handles:
    1. JSON inside ``\u0060\u0060\u0060json ... \u0060\u0060\u0060`` fenced blocks.
    2. JSON inside untagged ``\u0060\u0060\u0060 ... \u0060\u0060\u0060`` blocks.
    3. Bare JSON object (starts with ``{``).
    4. Returns ``None`` if no valid JSON found.

    Args:
        response_text: Raw text from LLM.

    Returns:
        Parsed dict, or ``None`` if no JSON found.
    """
    if not response_text or not response_text.strip():
        return None

    # Try fenced blocks first.
    matches = _JSON_BLOCK_RE.findall(response_text)
    for match in matches:
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            continue

    # Fallback: look for a bare JSON object in the text.
    first_brace = response_text.find("{")
    last_brace = response_text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidate = response_text[first_brace : last_brace + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    return None
