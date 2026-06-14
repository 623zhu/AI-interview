"""Management CLI for AI Interview backend.

Commands:
  python manage.py create-admin [-u <name> -e <email> -p <pwd>]
  python manage.py seed-questions                    Seed questions from seed_data.json
  python manage.py sync-jobs                         Sync MySQL jobs → Chroma
  python manage.py sync-questions                    Sync MySQL questions → Chroma
  python manage.py sync-all                          Rebuild both Chroma collections
"""
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select
from app.core.database import async_session_factory
from app.core.security import hash_password
from app.models.user import User
from app.models.question import Question
from app.models.job_position import JobPosition

SEED_FILE = Path(__file__).parent / "seed_data.json"
SEED_JOBS_FILE = Path(__file__).parent / "seed_jobs.json"


# ── Create Admin ────────────────────────────────────────

async def create_admin(username: str, email: str, password: str):
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.username == username))
        if result.scalar_one_or_none():
            print(f"[ERROR] Username '{username}' already exists")
            return

        result = await db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            print(f"[ERROR] Email '{email}' already registered")
            return

        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            is_admin=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"[OK] Admin created: {user.username} (ID: {user.id})")


# ── Seed Questions ──────────────────────────────────────

def load_seed_questions() -> list[dict]:
    """Load seed questions from JSON file."""
    with open(SEED_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


async def seed_questions():
    """Seed interview questions into MySQL from seed_data.json."""
    async with async_session_factory() as db:
        result = await db.execute(select(Question))
        existing = len(result.scalars().all())
        if existing > 0:
            print(f"[INFO] {existing} questions already exist. Skipping seed.")
            return

        questions = load_seed_questions()
        for q in questions:
            question = Question(
                category=q["category"],
                difficulty=q["difficulty"],
                job_category=q.get("job_category"),
                content=q["content"],
                expected_points=q.get("expected_points"),
                reference_answer=q.get("reference_answer"),
                source="seed",
            )
            db.add(question)

        await db.commit()
        print(f"[OK] Seeded {len(questions)} questions")


# ── Seed Jobs ───────────────────────────────────────────

def load_seed_jobs() -> list[dict]:
    """Load seed jobs from JSON file."""
    with open(SEED_JOBS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


async def seed_jobs():
    """Seed job positions into MySQL from seed_jobs.json."""
    async with async_session_factory() as db:
        result = await db.execute(select(JobPosition))
        existing = len(result.scalars().all())
        if existing > 0:
            print(f"[INFO] {existing} jobs already exist. Skipping seed.")
            return

        jobs = load_seed_jobs()
        for j in jobs:
            job = JobPosition(
                title=j["title"],
                category=j["category"],
                level=j["level"],
                description=j.get("description"),
                requirements=j.get("requirements"),
                salary_range=j.get("salary_range"),
                company_type=j.get("company_type", "互联网"),
            )
            db.add(job)

        await db.commit()
        print(f"[OK] Seeded {len(jobs)} job positions")


# ── RAG Sync Commands ───────────────────────────────────

async def sync_questions():
    """Sync MySQL questions → Chroma."""
    from app.agent.rag import sync_questions_to_chroma
    async with async_session_factory() as db:
        count = await sync_questions_to_chroma(db)
        print(f"[OK] Synced {count} questions to Chroma")


# ── CLI ─────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python manage.py create-admin [-u <name> -e <email> -p <pwd>]")
        print("  python manage.py seed-questions")
        print("  python manage.py seed-jobs")
        print("  python manage.py sync-questions")
        return

    cmd = sys.argv[1]

    if cmd == "create-admin":
        username = email = password = None
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            if args[i] == "-u" and i + 1 < len(args):
                username = args[i + 1]; i += 2
            elif args[i] == "-e" and i + 1 < len(args):
                email = args[i + 1]; i += 2
            elif args[i] == "-p" and i + 1 < len(args):
                password = args[i + 1]; i += 2
            else:
                i += 1

        if username and email and password:
            asyncio.run(create_admin(username, email, password))
        else:
            print("=== 创建管理员账号 ===")
            username = input("用户名: ").strip()
            email = input("邮箱: ").strip()
            password = input("密码: ").strip()
            if not all([username, email, password]):
                print("[ERROR] All fields are required")
                return
            asyncio.run(create_admin(username, email, password))

    elif cmd == "seed-questions":
        asyncio.run(seed_questions())

    elif cmd == "seed-jobs":
        asyncio.run(seed_jobs())

    elif cmd == "sync-questions":
        asyncio.run(sync_questions())

    else:
        print(f"未知命令: {cmd}")


if __name__ == "__main__":
    main()
