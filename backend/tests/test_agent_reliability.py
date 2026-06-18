import asyncio
import json

import pytest
from langgraph.errors import GraphRecursionError

from app.agent.interview_agent import InterviewManager
from app.agent.tools import build_react_prompt
from app.core.config import settings


class RecordingAgent:
    def __init__(self):
        self.payload = None
        self.config = None

    async def ainvoke(self, payload, config=None):
        self.payload = payload
        self.config = config
        return {"messages": []}


class SlowAgent:
    async def ainvoke(self, payload, config=None):
        await asyncio.sleep(1)
        return {"messages": []}


@pytest.mark.asyncio
async def test_agent_invoke_passes_recursion_limit(monkeypatch):
    monkeypatch.setattr(settings, "REACT_AGENT_RECURSION_LIMIT", 7)
    monkeypatch.setattr(settings, "INTERVIEW_AGENT_TIMEOUT_SECONDS", 1)
    manager = InterviewManager(db=None, redis=None)
    agent = RecordingAgent()

    result = await manager._invoke_agent(agent, {"messages": ["hello"]})

    assert result == {"messages": []}
    assert agent.payload == {"messages": ["hello"]}
    assert agent.config == {"recursion_limit": 7}


@pytest.mark.asyncio
async def test_agent_invoke_enforces_timeout(monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_AGENT_TIMEOUT_SECONDS", 0.01)
    manager = InterviewManager(db=None, redis=None)

    with pytest.raises(TimeoutError):
        await manager._invoke_agent(SlowAgent(), {"messages": []})


def test_agent_error_payload_classifies_timeout():
    payload = InterviewManager._agent_error_payload(TimeoutError())

    assert payload["code"] == "agent_timeout"
    assert payload["retryable"] is True


def test_agent_error_payload_classifies_recursion_limit():
    payload = InterviewManager._agent_error_payload(GraphRecursionError("too deep"))

    assert payload["code"] == "agent_iteration_limit"
    assert payload["retryable"] is True


def test_agent_error_payload_classifies_unknown_failure():
    payload = InterviewManager._agent_error_payload(RuntimeError("boom"))

    assert payload["code"] == "agent_turn_failed"
    assert payload["retryable"] is True


def test_clean_candidate_message_removes_markdown_and_internal_note():
    text = (
        '聊回你做的项目——你提到了"两层记忆系统"，'
        '**如果让你重新设计这个记忆系统，你会怎么规划短期记忆和长期记忆的架构？**\n\n'
        "（我选第0题微调措辞，结合他在项目里实际提到的记忆系统设计来问）"
    )

    cleaned = InterviewManager._clean_candidate_message(text)

    assert "**" not in cleaned
    assert "我选第0题" not in cleaned
    assert "微调措辞" not in cleaned
    assert "你会怎么规划短期记忆和长期记忆的架构？" in cleaned


def test_meta_message_detects_internal_selection_text():
    assert InterviewManager._is_meta_message("我选第0题微调措辞，结合候选人项目来问")


def test_parse_agent_output_uses_candidate_message_only():
    raw = json.dumps(
        {
            "action": "ask_next",
            "candidate_message": "你会如何设计长期记忆的更新策略？",
            "internal_note": "我选第0题并结合项目微调措辞。",
        },
        ensure_ascii=False,
    )

    parsed = InterviewManager._parse_agent_output(raw)

    assert parsed["candidate_message"] == "你会如何设计长期记忆的更新策略？"
    assert "我选第0题" in parsed["internal_note"]


def test_parse_agent_output_accepts_json_code_fence():
    raw = """```json
{"action":"ask_next","candidate_message":"你如何评估 RAG 召回效果？","internal_note":"内部说明"}
```"""

    parsed = InterviewManager._parse_agent_output(raw)

    assert parsed["candidate_message"] == "你如何评估 RAG 召回效果？"


def test_parse_agent_output_marks_plain_text_invalid():
    parsed = InterviewManager._parse_agent_output("请解释你在项目里怎么做召回评估？")

    assert parsed["valid"] is False
    assert parsed["candidate_message"] == ""
    assert "召回评估" in parsed["internal_note"]


def test_fallback_question_uses_first_clean_rag_candidate():
    question = InterviewManager._fallback_question([
        {"content": "**请解释你如何评估 RAG 系统的召回效果？**"},
        {"content": "请讲讲你的项目难点。"},
    ])

    assert question == "请解释你如何评估 RAG 系统的召回效果？"


def test_fallback_question_uses_generic_when_no_rag_candidate():
    question = InterviewManager._fallback_question([])

    assert "项目" in question
    assert "技术难点" in question


def test_react_prompt_renders_structured_output_contract():
    prompt = build_react_prompt(
        job_title="后端工程师",
        job_category="backend",
        resume_summary="候选人做过 RAG 项目",
        total_q=6,
        answered_count=1,
        asked_topics="RAG 评估",
        recent_history="候选人：回答内容",
        latest_answer="我会构造测试集",
    )

    assert '"candidate_message"' in prompt
    assert '"internal_note"' in prompt
    assert "后端工程师" in prompt
