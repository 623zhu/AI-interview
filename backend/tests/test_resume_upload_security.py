from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.api.v1.resumes import detect_resume_file_type, download_resume_file
from app.core.config import settings
from app.models.resume import Resume
from tests.test_interviews import _seed_user_resume_job


def test_detect_resume_file_type_uses_magic_bytes():
    assert detect_resume_file_type(b"%PDF-1.7\n...") == "pdf"
    assert detect_resume_file_type(b"PK\x03\x04...word/document.xml") == "docx"
    assert detect_resume_file_type(b"not really a resume") is None


@pytest.mark.asyncio
async def test_download_resume_file_requires_owner_and_upload_path(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    owner, resume, _job = await _seed_user_resume_job(db_session)
    other_user, _other_resume, _other_job = await _seed_user_resume_job(
        db_session,
        username="bob",
        email="bob@example.com",
    )

    stored_file = tmp_path / "resume.pdf"
    stored_file.write_bytes(b"%PDF-1.7\n")
    resume.file_path = str(stored_file)
    resume.file_type = "pdf"
    await db_session.flush()

    response = await download_resume_file(resume.id, current_user=owner, db=db_session)
    assert isinstance(response, FileResponse)

    with pytest.raises(HTTPException) as exc:
        await download_resume_file(resume.id, current_user=other_user, db=db_session)
    assert exc.value.status_code == 404

    outside_file = Path(tmp_path).parent / "outside.pdf"
    outside_file.write_bytes(b"%PDF-1.7\n")
    resume.file_path = str(outside_file)
    await db_session.flush()

    with pytest.raises(HTTPException) as path_exc:
        await download_resume_file(resume.id, current_user=owner, db=db_session)
    assert path_exc.value.status_code == 400
