"""Resume data extraction utilities — single source of truth for building resume context.

Used by interview endpoints (create, skip) and the Interview Agent.
"""
from app.models.resume import Resume


def build_resume_context(resume: Resume | None) -> str:
    """Build a structured resume summary string from parsed_data.

    Extracts skills, work experience, projects, and education into a
    single text block suitable for prompt injection.

    Returns "暂无简历信息" if resume or parsed_data is missing.
    """
    if not resume or not resume.parsed_data:
        return "暂无简历信息"

    rd = resume.parsed_data
    parts: list[str] = []

    # ── Summary ──
    summary = rd.get("summary", "")
    if isinstance(summary, str) and summary.strip():
        parts.append(f"职业概述: {summary[:200]}")

    # ── Skills ──
    skills = rd.get("skills", [])
    if skills:
        parts.append("技能: " + ", ".join(skills[:10]))

    # ── Work experience (handle both 'work_experience' and 'experience' keys) ──
    work_exp = rd.get("work_experience") or rd.get("experience") or []
    if isinstance(work_exp, list) and work_exp:
        parts.append("工作/实习经历:")
        for i, exp in enumerate(work_exp[:3]):
            if isinstance(exp, dict):
                company = exp.get("company", "")
                title = exp.get("title", "")
                desc = exp.get("description", "")
                highlights = exp.get("highlights", [])
                highlights_str = "; ".join(highlights[:3]) if highlights else ""
                line = f"  {i+1}. {company} | {title}"
                if desc:
                    line += f" | {desc[:200]}"
                if highlights_str:
                    line += f" | 亮点: {highlights_str}"
                parts.append(line)
            else:
                parts.append(f"  {i+1}. {str(exp)[:200]}")

    # ── Projects ──
    projects = rd.get("projects", [])
    if isinstance(projects, list) and projects:
        parts.append("项目经历:")
        for i, proj in enumerate(projects[:3]):
            if isinstance(proj, dict):
                name = proj.get("name", "")
                role = proj.get("role", "")
                desc = proj.get("description", "")
                tech_stack = proj.get("tech_stack", [])
                highlights = proj.get("highlights", [])
                tech_str = ", ".join(tech_stack[:5]) if tech_stack else ""
                highlights_str = "; ".join(highlights[:3]) if highlights else ""
                line = f"  {i+1}. {name}"
                if role:
                    line += f" ({role})"
                if desc:
                    line += f" | {desc[:150]}"
                if tech_str:
                    line += f" | 技术栈: {tech_str}"
                if highlights_str:
                    line += f" | 亮点: {highlights_str}"
                parts.append(line)
            else:
                parts.append(f"  {i+1}. {str(proj)[:200]}")

    # ── Education ──
    education = rd.get("education", [])
    if isinstance(education, list) and education:
        edu_parts = []
        for edu in education[:2]:
            if isinstance(edu, dict):
                edu_parts.append(
                    f"{edu.get('school','')} {edu.get('major','')} {edu.get('degree','')}"
                )
        if edu_parts:
            parts.append("教育: " + "; ".join(edu_parts))

    return "\n".join(parts) if parts else "暂无简历信息"
