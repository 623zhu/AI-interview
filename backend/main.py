"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from contextlib import suppress
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os

from app.core.config import settings
from app.core.database import engine
from app.core.errors import install_exception_handlers
from app.core.health import health_payload, readiness_payload
from app.core.logging import configure_logging
from app.core.observability import RequestIDMiddleware
from app.core.redis import close_redis, get_redis
from app.core.graph_runtime import close_graph_runtime, start_graph_runtime
from app.api.v1.router import api_router
from app.services.report_service import recover_pending_reports

configure_logging(settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
    await start_graph_runtime()
    report_recovery = asyncio.create_task(recover_pending_reports())

    yield

    # Shutdown
    if not report_recovery.done():
        report_recovery.cancel()
        with suppress(asyncio.CancelledError):
            await report_recovery
    await close_graph_runtime()
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(RequestIDMiddleware)
install_exception_handlers(app)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return health_payload()


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint for dependency availability."""
    status_code, payload = await readiness_payload(engine=engine, redis_factory=get_redis)
    return JSONResponse(status_code=status_code, content=payload)
