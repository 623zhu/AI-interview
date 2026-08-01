"""Retrieve a small, policy-safe pool for switching interview topics."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import or_, select

from app.agent.rag import search_questions
from app.core.database import async_session_factory
from app.models.question import Question

logger = logging.getLogger(__name__)


def _candidate_skill_path(
    question: Question, frontier: list[dict[str, Any]]
) -> str:
    nodes = {str(item).lower() for item in (question.skill_nodes or [])}
    for target in frontier:
        path = str(target.get("path") or "")
        name = str(target.get("name") or "")
        if path.lower() in nodes or name.lower() in nodes:
            return path
        if name and name.lower() in question.content.lower():
            return path
    return str(frontier[0].get("path") or "") if frontier else ""


def _serialize_question(
    question: Question, frontier: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "id": question.id,
        "content": question.content,
        "skill_path": _candidate_skill_path(question, frontier),
        "difficulty": question.difficulty,
        "category": question.category,
        "expected_points": question.expected_points or "",
        "evaluation_criteria": question.evaluation_criteria or {},
    }


async def retrieve_question_pool(
    frontier: list[dict[str, Any]],
    job_snapshot: dict[str, Any],
    used_question_ids: list[str],
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """为 SWITCH 目标返回未使用的题库候选，每个技能最多保留两题。

    Chroma 负责按语义给出题目 ID 排名；MySQL 负责返回仍然有效的题目原文。
    向量检索失败时会退回数据库排序，避免整轮面试直接失败。
    """
    if not frontier:
        return []

    job_category = str(job_snapshot.get("category") or "").strip()
    query = " | ".join(
        filter(
            None,
            [
                str(job_snapshot.get("title") or ""),
                *(str(item.get("name") or item.get("path") or "") for item in frontier),
            ],
        )
    )
    desired_difficulty = str(frontier[0].get("difficulty") or "medium")

    # 第一阶段：向量召回和重排，只取得按相关度排序的题目 ID。
    ranked_ids: list[str] = []
    try:
        matches = await search_questions(
            query,
            difficulty=desired_difficulty,
            job_category=job_category or None,
            k=max(limit * 3, 12),
            over_fetch=max(limit * 5, 30),
        )
        ranked_ids = [item.id for item in matches]
    except Exception:
        logger.exception("Question vector retrieval failed; using database fallback")

    # 第二阶段：回到 MySQL 校验题目仍启用、岗位适用且本场尚未使用。
    used = set(used_question_ids)
    async with async_session_factory() as db:
        conditions = [Question.is_active.is_(True)]
        if used:
            conditions.append(Question.id.not_in(used))
        if job_category:
            conditions.append(
                or_(
                    Question.job_category == job_category,
                    Question.job_category.is_(None),
                    Question.job_category == "",
                )
            )

        if ranked_ids:
            result = await db.execute(
                select(Question).where(Question.id.in_(ranked_ids), *conditions)
            )
            by_id = {question.id: question for question in result.scalars().all()}
            questions = [by_id[item_id] for item_id in ranked_ids if item_id in by_id]
        else:
            result = await db.execute(
                select(Question)
                .where(*conditions)
                .order_by(Question.usage_count.asc(), Question.created_at.desc())
                .limit(max(limit * 3, 12))
            )
            questions = list(result.scalars().all())

    # 第三阶段：限制每个技能的候选数量，避免单一技能占满整个候选池。
    per_skill: defaultdict[str, int] = defaultdict(int)
    pool: list[dict[str, Any]] = []
    for question in questions:
        candidate = _serialize_question(question, frontier)
        skill_path = candidate["skill_path"]
        if not skill_path or per_skill[skill_path] >= 2:
            continue
        per_skill[skill_path] += 1
        pool.append(candidate)
        if len(pool) >= limit:
            break
    return pool
