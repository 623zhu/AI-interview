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
    current_comment = ""

    for msg in messages:
        if msg.role == "ai" and msg.message_type in ("question", "follow_up"):
            # Save previous round if complete
            if current_q and current_answer:
                rounds.append({
                    "question": current_q,
                    "answer": current_answer,
                    "comment": current_comment or "",
                })
            current_q = msg.content
            current_answer = ""
            current_comment = ""
        elif msg.role == "user":
            current_answer = msg.content
            extra = msg.extra_data or {}
            current_comment = extra.get("comment", "")
        elif msg.role == "system":
            pass

    # Don't forget last round
    if current_q and current_answer:
        rounds.append({
            "question": current_q,
            "answer": current_answer,
            "comment": current_comment or "",
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

    # Simplified dimensions from profile data
    strengths = [r["comment"] for r in rounds if r["comment"] and ("好" in r["comment"] or "不错" in r["comment"] or "准确" in r["comment"])]
    weaknesses = [r["comment"] for r in rounds if r["comment"] and ("不足" in r["comment"] or "缺" in r["comment"] or "未" in r["comment"])]

    report = ScoreReport(
        session_id=session_id,
        user_id=session.user_id,
        overall_score=0,  # no numeric scoring
        dimension_scores={},
        question_evaluations=rounds,
        strengths=strengths or [],
        weaknesses=weaknesses or [],
        improvements=[],
        full_report=full,
        full_data={"rounds": rounds},
        generated_at=datetime.now(timezone.utc),
    )
    db.add(report)
    await db.flush()
    logger.info("Report %s for session %s (%d rounds)", report.id, session_id, len(rounds))
    return report
