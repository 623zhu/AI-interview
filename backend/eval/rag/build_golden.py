"""build_golden.py — 用 LLM 给题库每道题生成多条自然语言 query，作为 RAG 评测黄金集。

用法:
    cd backend
    python -m eval.rag.build_golden                     # 默认: 每题 3 条 query
    python -m eval.rag.build_golden --per-question 5    # 每题 5 条
    python -m eval.rag.build_golden --limit 20          # 只取前 20 题（调试用）

产出:
    eval/rag/golden_auto.jsonl  — 每行一个 JSON:
    {"query": "...", "positive_ids": ["qid"], "skill_nodes": [...], "job_category": "..."}
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from sqlalchemy import select

# 让 backend/ 下的 app 包能被 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.database import async_session_factory
from app.core.llm import get_llm
from app.models.question import Question
from app.utils.json_utils import parse_json

logger = logging.getLogger(__name__)
OUT_FILE = Path(__file__).resolve().parent / "golden_auto.jsonl"

QUERY_GEN_PROMPT = """\
你是面试模拟系统的评测工程师。给你一道面试题，请站在面试官视角，写出 {n} 条"面试官脑子里想问的自然语言检索 query"。

要求：
1. 每条 query 15-40 字，口语化、自然，不要照抄题面
2. 覆盖不同提问角度（追问、换个说法、关联话题）
3. 输出纯 JSON 数组，无其它文字

面试题：
{content}

核心考察点：
{expected_points}
"""


async def generate_queries(content: str, expected_points: str, n: int) -> list[str]:
    llm = get_llm(temperature=0.7)
    prompt = QUERY_GEN_PROMPT.format(
        n=n,
        content=content,
        expected_points=expected_points or "（无）",
    )
    from langchain_core.messages import HumanMessage
    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    text = resp.content if hasattr(resp, "content") else str(resp)
    try:
        arr = parse_json(text)
        if isinstance(arr, dict) and "queries" in arr:
            arr = arr["queries"]
        if isinstance(arr, list):
            return [str(q).strip() for q in arr if q and len(str(q).strip()) >= 5]
    except Exception:
        pass
    # 兜底：按行拆
    lines = [l.strip().strip('"').strip("'").lstrip("- ") for l in text.splitlines() if len(l.strip()) >= 5]
    return lines[:n]


async def main(per_question: int, limit: int | None):
    async with async_session_factory() as db:
        q = select(Question).where(Question.is_active == True).order_by(Question.created_at)
        if limit:
            q = q.limit(limit)
        result = await db.execute(q)
        questions = result.scalars().all()

    if not questions:
        print("[ERROR] 题库为空，请先 seed-questions + sync-questions")
        return

    print(f"共 {len(questions)} 道题，每题生成 {per_question} 条 query ...")

    records = []
    for i, question in enumerate(questions):
        try:
            queries = await generate_queries(question.content, question.expected_points or "", per_question)
        except Exception as e:
            print(f"  [{i+1}] FAILED: {e}")
            continue

        for query in queries:
            records.append({
                "query": query,
                "positive_ids": [question.id],
                "skill_nodes": question.skill_nodes or [],
                "job_category": question.job_category or "",
                "difficulty": question.difficulty,
                "source_content": question.content[:120],
            })
        print(f"  [{i+1}/{len(questions)}] {question.content[:40]}... → {len(queries)} queries")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n[OK] 写入 {len(records)} 条到 {OUT_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成 RAG 评测黄金集")
    parser.add_argument("--per-question", type=int, default=3, help="每题生成几条 query")
    parser.add_argument("--limit", type=int, default=None, help="只取前 N 题（调试用）")
    args = parser.parse_args()
    asyncio.run(main(args.per_question, args.limit))