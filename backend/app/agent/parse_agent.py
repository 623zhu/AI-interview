from langchain_core.messages import SystemMessage, HumanMessage
from app.core.llm import get_llm
from app.utils.json_utils import parse_json
from app.agent.prompts import RESUME_PARSE_PROMPT
def _extract_json(text: str) -> dict:
    """Extract JSON object from LLM response. Delegates to shared utility."""
    return parse_json(text)


def _validate_parsed(data: dict) -> dict:
    """Ensure required fields exist with correct types. Non-destructive — preserves extra data."""
    array_fields = ("skills", "work_experience", "projects", "education",
                    "languages", "certifications")
    dict_fields = ("personal_info",)
    str_fields = ("summary",)

    # Fill missing required keys with sensible defaults
    for key in array_fields:
        if key not in data:
            data[key] = []
        elif not isinstance(data[key], list):
            data[key] = []
    for key in dict_fields:
        if key not in data:
            data[key] = {}
        elif not isinstance(data[key], dict):
            data[key] = {}
    for key in str_fields:
        if key not in data:
            data[key] = None

    # Ensure extra field exists
    if "extra" not in data:
        data["extra"] = {}
    elif not isinstance(data.get("extra"), dict):
        data["extra"] = {}

    return data


# ── Main ────────────────────────────────────────────────────────────────────


async def parse_resume(raw_text: str) -> dict:
    """Parse raw resume text into structured JSON.

    Args:
        raw_text: The full text extracted from the resume file.

    Returns:
        Structured dict with personal_info, skills, work_experience, etc.

    Raises:
        ValueError: If the LLM response cannot be parsed.
    """
    # Truncate very long texts to avoid token limits
    max_chars = 8000
    if len(raw_text) > max_chars:
        text = raw_text[:max_chars] +"\n\n[文本已截断，原始长度: {} 字符]".format(len(raw_text))
    else:
        text = raw_text
    llm = get_llm(temperature=0.1)
    messages = [
        SystemMessage(content=RESUME_PARSE_PROMPT),
        HumanMessage(content=f"请解析以下简历原文：\n\n{text}"),
    ]

    response = await llm.ainvoke(messages)
    content = response.content if hasattr(response, 'content') else str(response)

    parsed = _extract_json(content)
    return _validate_parsed(parsed)