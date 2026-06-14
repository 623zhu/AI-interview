import json
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# -----------------------------
# 1. Extract JSON block safely
# -----------------------------
def extract_code_fence_json(text: str) -> Optional[str]:
    """Extract JSON from ```json ... ``` blocks (prefer last block)."""
    matches = re.findall(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if not matches:
        return None
    return matches[-1].strip()


def extract_balanced_json(text: str) -> Optional[str]:
    """Extract first balanced JSON object using brace matching."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    return None


def strip_markdown(text: str) -> str:
    """Remove surrounding markdown artifacts."""
    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()

    return text


def clean_json(text: str) -> str:
    """
    Try multiple strategies to extract JSON string from LLM output.
    Order:
    1. code fence JSON
    2. raw balanced JSON
    3. markdown stripped + fallback scan
    """
    if not text:
        raise ValueError("Empty LLM response")

    text = text.strip()

    # 1) fenced JSON
    fenced = extract_code_fence_json(text)
    if fenced:
        return fenced

    # 2) balanced JSON
    balanced = extract_balanced_json(text)
    if balanced:
        return balanced

    # 3) fallback after stripping markdown
    cleaned = strip_markdown(text)
    balanced = extract_balanced_json(cleaned)
    if balanced:
        return balanced

    # last fallback: try full text
    return cleaned


# -----------------------------
# 2. JSON parsing with fallback
# -----------------------------
def parse_json(text: str) -> dict:
    """
    Parse JSON from LLM output with robust fallback handling.
    """
    extracted = clean_json(text)

    # 1) strict JSON
    try:
        return json.loads(extracted)
    except json.JSONDecodeError as e:
        logger.warning(
            "Strict JSON parse failed: %s | preview=%s",
            str(e),
            extracted[:300],
        )

    # 2) optional JSON5 fallback (if installed)
    try:
        import json5  # optional dependency
        return json5.loads(extracted)
    except Exception:
        pass

    # 3) last resort: try to salvage common LLM issues
    try:
        repaired = (
            extracted
            .replace("None", "null")
            .replace("True", "true")
            .replace("False", "false")
        )
        return json.loads(repaired)
    except Exception as e:
        logger.error("Final JSON parse failed. raw=%s", text[:500])
        raise ValueError(
            f"无法解析LLM响应为JSON。错误: {str(e)}\n"
            f"原始片段: {text[:200]}"
        )