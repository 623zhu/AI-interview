"""API v1 总路由：集中管理当前版本的所有业务接口。"""

from fastapi import APIRouter

from app.api.v1 import admin, auth, dashboard, interviews, jobs, questions, reports, resumes


api_router = APIRouter()

# 所有认证接口最终都会拥有 /api/v1/auth 前缀。
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(resumes.router, prefix="/resumes", tags=["Resumes"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
api_router.include_router(questions.router, prefix="/questions", tags=["Questions"])
api_router.include_router(interviews.router, prefix="/interviews", tags=["Interviews"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
