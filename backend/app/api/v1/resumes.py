"""Resume endpoints: upload, list, detail, delete, reparse."""
import asyncio
import os
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.api.deps import get_current_user
from app.models.user import User
from app.models.resume import Resume
from app.schemas.resume import ResumeOut, ResumeListItem
from app.agent.parse_agent import parse_resume

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_TYPES = {"application/pdf": "pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx"}
MAX_SIZE = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


@router.post("/upload", status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    auto_parse: bool = Form(default=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a resume file (PDF/DOCX)."""
    # Validate file type
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式，请上传 PDF 或 DOCX")

    # Validate file size
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail=f"文件大小不能超过 {settings.MAX_UPLOAD_SIZE_MB}MB")

    # Save file
    file_ext = ALLOWED_TYPES[file.content_type]
    filename = f"{uuid.uuid4()}.{file_ext}"
    file_path = os.path.join(settings.UPLOAD_DIR, filename)

    with open(file_path, "wb") as f:
        f.write(content)

    # Extract text in a thread to avoid blocking the event loop
    raw_text = await asyncio.to_thread(_extract_text, file_path, file_ext)

    resume = Resume(
        user_id=current_user.id,
        original_filename=file.filename or "unknown",
        file_path=file_path,
        file_type=file_ext,
        file_size=len(content),
        raw_text=raw_text,
        parse_status="processing",
    )
    db.add(resume)
    await db.flush()
    await db.refresh(resume)

    # Run AI parsing
    if auto_parse and raw_text:
        try:
            parsed = await parse_resume(raw_text)
            resume.parsed_data = parsed
            resume.parse_status = "completed"
        except Exception as exc:
            logger.warning("Resume parse failed for %s: %s", resume.id, exc)
            resume.parse_status = "failed"
            resume.parse_error = str(exc)[:500]
        await db.flush()
        await db.refresh(resume)

    return {
        "code": 201,
        "message": "上传成功" + ("，解析完成" if resume.parse_status == "completed" else "，解析失败"),
        "data": ResumeOut.model_validate(resume).model_dump()
    }


@router.get("")
async def list_resumes(
    page: int = 1,
    page_size: int = 20,
    parse_status: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List resumes for current user."""
    query = select(Resume).where(Resume.user_id == current_user.id)
    count_query = select(func.count(Resume.id)).where(Resume.user_id == current_user.id)

    if parse_status:
        query = query.where(Resume.parse_status == parse_status)
        count_query = count_query.where(Resume.parse_status == parse_status)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Resume.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    resumes = result.scalars().all()

    return {
        "code": 200,
        "data": {
            "items": [ResumeListItem.model_validate(r).model_dump() for r in resumes],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    }


@router.get("/{resume_id}")
async def get_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get resume detail."""
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == current_user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")

    return {
        "code": 200,
        "data": ResumeOut.model_validate(resume).model_dump()
    }


@router.delete("/{resume_id}")
async def delete_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a resume and its uploaded file."""
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == current_user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")

    # Delete file (best-effort, don't fail if file is missing or locked)
    if resume.file_path:
        try:
            if os.path.exists(resume.file_path):
                os.remove(resume.file_path)
        except OSError as e:
            logger.warning("Failed to delete resume file %s: %s", resume.file_path, e)

    await db.delete(resume)
    await db.flush()
    return {"code": 200, "message": "删除成功"}


@router.post("/{resume_id}/reparse")
async def reparse_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger re-parsing of a resume."""
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == current_user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")

    if not resume.raw_text:
        raise HTTPException(status_code=400, detail="简历无文本内容可解析")

    resume.parse_status = "processing"
    resume.parsed_data = None
    resume.parse_error = None
    await db.flush()

    # Run AI parsing
    try:
        parsed = await parse_resume(resume.raw_text)
        resume.parsed_data = parsed
        resume.parse_status = "completed"
    except Exception as exc:
        logger.warning("Resume reparse failed for %s: %s", resume.id, exc)
        resume.parse_status = "failed"
        resume.parse_error = str(exc)[:500]
    await db.flush()
    await db.refresh(resume)

    return {
        "code": 200,
        "message": "重新解析完成" if resume.parse_status == "completed" else "重新解析失败",
        "data": ResumeOut.model_validate(resume).model_dump()
    }


def _extract_text(file_path: str, file_type: str) -> str:
    """Extract text from PDF or DOCX file. Placeholder for full implementation."""
    try:
        if file_type == "pdf":
            import pdfplumber
            text_parts = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
            return "\n".join(text_parts)
        elif file_type == "docx":
            from docx import Document
            doc = Document(file_path)
            return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    except Exception as e:
        return f"[文本提取失败: {str(e)}]"
    return ""
