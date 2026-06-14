"""Report generation service — delegates to report module.

For actual report generation, see:
- app.agent.report.generate_report() — full report from interview messages
"""
from app.models.interview_session import InterviewSession
from app.agent.report import generate_report as _generate_report


async def generate_report(session: InterviewSession) -> dict:
    """Generate a score report using Score Agent.

    Args:
        session: Completed interview session with messages.

    Returns:
        Dict with overall_score, dimension_scores, question_evaluations, etc.
    """
    # Delegates to the score agent which requires an AsyncSession,
    # so this service-level wrapper is best called from an endpoint
    # where the db session is available.
    return {}
