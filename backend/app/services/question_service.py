"""Question generation service — delegates to Interview Agent + RAG.

For actual question generation, see:
- app.agent.rag.search_questions() — semantic search via Chroma
- app.agent.interview_agent.InterviewManager — interview orchestration
"""
from app.models.resume import Resume
from app.models.job_position import JobPosition
from app.agent.rag import search_questions
from app.utils.resume_utils import build_resume_context


async def generate_questions(
    resume: Resume,
    job: JobPosition,
    config: dict
) -> list[dict]:
    """Generate interview questions using RAG semantic search.

    Args:
        resume: Parsed resume with skills, experience, projects.
        job: Target job position with title, category, level.
        config: Dict with question_count, difficulty_distribution, etc.

    Returns:
        List of question dicts with content, category, difficulty, etc.
    """
    count = config.get("question_count", 7) if config else 7
    resume_summary = build_resume_context(resume)
    search_text = f"{job.title} {job.category} {resume_summary}"

    results = await search_questions(query=search_text, category=None, k=count)

    questions = []
    for i, r in enumerate(results):
        questions.append({
            "question_number": i + 1,
            "id": r.metadata.get("mysql_id", r.id) if isinstance(r.metadata, dict) else r.id,
            "content": r.metadata.get("content", "") if isinstance(r.metadata, dict) else "",
            "category": r.metadata.get("category", "scenario") if isinstance(r.metadata, dict) else "scenario",
            "difficulty": r.metadata.get("difficulty", "medium") if isinstance(r.metadata, dict) else "medium",
        })

    return questions
