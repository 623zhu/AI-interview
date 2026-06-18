"""Report formatter — compiles interview conversation into a readable summary."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interview_session import InterviewSession, InterviewMessage
from app.models.score_report import ScoreReport

logger = logging.getLogger(__name__)


async def generate_report(db: AsyncSession, session_id: str) -> ScoreReport:
    """Compile the full interview conversation with per-question comments."""
    session = await db.get(InterviewSession, session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    result = await db.execute(
        select(InterviewMessage)
        .where(InterviewMessage.session_id == session_id)
        .order_by(InterviewMessage.created_at)
    )
    messages = result.scalars().all()

    # Build conversation blocks: question → answer → comment
    rounds = []
    current_q = ""
    current_answer = ""
    current_eval: dict = {}

    for msg in messages:
        if msg.role == "ai" and msg.message_type in ("question", "follow_up"):
            # Save previous round if complete
            if current_q and current_answer:
                rounds.append({
                    "question": current_q,
                    "answer": current_answer,
                    "comment": current_eval.get("comment", ""),
                    "skill_path": current_eval.get("skill_path", ""),
                    "confidence": current_eval.get("confidence"),
                    "depth": current_eval.get("depth"),
                    "gaps": current_eval.get("gaps", ""),
                })
            current_q = msg.content
            current_answer = ""
            current_eval = {}
        elif msg.role == "user":
            current_answer = msg.content
            current_eval = msg.extra_data or {}
        elif msg.role == "system":
            pass

    # Don't forget last round
    if current_q and current_answer:
        rounds.append({
            "question": current_q,
            "answer": current_answer,
            "comment": current_eval.get("comment", ""),
            "skill_path": current_eval.get("skill_path", ""),
            "confidence": current_eval.get("confidence"),
            "depth": current_eval.get("depth"),
            "gaps": current_eval.get("gaps", ""),
        })

    # Build markdown report
    lines = ["# 面试评估报告", "", f"**共 {len(rounds)} 轮对话**", ""]

    for i, r in enumerate(rounds, 1):
        lines.append(f"## 第 {i} 轮")
        lines.append("")
        lines.append(f"**问：** {r['question']}")
        lines.append("")
        lines.append(f"**答：** {r['answer'][:500]}")
        lines.append("")
        if r["comment"]:
            lines.append(f"> 💬 {r['comment']}")
        lines.append("")

    full = "\n".join(lines)

    scored_rounds = [
        r for r in rounds
        if isinstance(r.get("confidence"), (int, float)) and isinstance(r.get("depth"), (int, float))
    ]
    if scored_rounds:
        avg_confidence = sum(float(r["confidence"]) for r in scored_rounds) / len(scored_rounds)
        avg_depth = sum(float(r["depth"]) for r in scored_rounds) / len(scored_rounds)
        overall_score = round((avg_confidence * 0.6 + avg_depth * 0.4) * 100)
    else:
        avg_confidence = None
        avg_depth = None
        overall_score = 0

    strengths = [
        f"{r.get('skill_path') or f'第{i}轮'}：{r.get('comment')}"
        for i, r in enumerate(rounds, 1)
        if isinstance(r.get("confidence"), (int, float)) and float(r["confidence"]) >= 0.7 and r.get("comment")
    ]
    weaknesses = [
        f"{r.get('skill_path') or f'第{i}轮'}：{r.get('gaps') or r.get('comment')}"
        for i, r in enumerate(rounds, 1)
        if (
            (isinstance(r.get("confidence"), (int, float)) and float(r["confidence"]) < 0.6)
            or r.get("gaps")
        )
    ]

    report = ScoreReport(
        session_id=session_id,
        user_id=session.user_id,
        overall_score=overall_score,
        dimension_scores={
            "avg_confidence": round(avg_confidence, 3) if avg_confidence is not None else None,
            "avg_depth": round(avg_depth, 3) if avg_depth is not None else None,
            "score_formula": "overall_score = (avg_confidence * 0.6 + avg_depth * 0.4) * 100",
        },
        question_evaluations=rounds,
        strengths=strengths or [],
        weaknesses=weaknesses or [],
        improvements=[],
        full_report=full,
        full_data={
            "rounds": rounds,
            "scoring": {
                "scored_round_count": len(scored_rounds),
                "avg_confidence": avg_confidence,
                "avg_depth": avg_depth,
            },
        },
        generated_at=datetime.now(timezone.utc),
    )
    db.add(report)
    await db.flush()
    logger.info("Report %s for session %s (%d rounds)", report.id, session_id, len(rounds))
    return report
