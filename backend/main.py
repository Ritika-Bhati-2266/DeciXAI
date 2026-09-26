"""
DecisionAI Engine — Production Entry Point

A Hybrid Decision Intelligence System combining ML Prediction,
SHAP Explainability, RAG-based Evidence Retrieval, and LLM-generated
Action Plans across career, finance, startup, and policy domains.
"""
from __future__ import annotations

import os
import sys
import time

# Windows consoles default to cp1252, which crashes on roadmap/XAI symbols
# (>=, em-dashes, emoji). Force UTF-8 so logging/printing never raises
# UnicodeEncodeError regardless of terminal code page.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from middleware.security import (
    APIKeyMiddleware,
    BodySizeLimitMiddleware,
    RequestTrackingMiddleware,
)
from middleware.rate_limiter import RateLimitMiddleware
from middleware.audit_logger import AuditLogMiddleware
from routers import career, finance, startup, policy, chatbot, export, audit, auth, decisions, apikeys, loan_application
from utils.app_logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:3001,http://127.0.0.1:3002,http://127.0.0.1:5173").split(",")
    if origin.strip()
]

app = FastAPI(
    title="DecisionAI Engine",
    description=(
        "AI-powered Explainable Decision Intelligence System. "
        "Combines ML models, SHAP explainability, RAG retrieval, and LLM reasoning "
        "across Career, Finance, Startup, and Policy domains."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "DeciXAI Team",
        "url": "https://github.com/RiyanshiVerma-11/DeciXAI",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# ---------------------------------------------------------------------------
# Middleware stack (order matters — outermost first)
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestTrackingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(APIKeyMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
# app.add_middleware(AuditLogMiddleware)

# ---------------------------------------------------------------------------
# Versioned API routes — /api/v1/...
# ---------------------------------------------------------------------------

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(decisions.router, prefix="/api/v1/decisions", tags=["Decisions Workspace"])
app.include_router(apikeys.router, prefix="/api/v1/keys", tags=["Developer API Keys"])
app.include_router(career.router, prefix="/api/v1/career", tags=["Career"])
app.include_router(finance.router, prefix="/api/v1/finance", tags=["Finance"])
app.include_router(startup.router, prefix="/api/v1/startup", tags=["Startup"])
app.include_router(policy.router, prefix="/api/v1/policy", tags=["Policy"])
app.include_router(chatbot.router, prefix="/api/v1/chatbot", tags=["Chatbot"])
app.include_router(export.router, prefix="/api/v1/export", tags=["Export"])
app.include_router(audit.router, prefix="/api/v1/audit", tags=["Audit Trail"])
app.include_router(loan_application.router, prefix="/loan-application", tags=["Finance Application"])

# Backward-compatible routes (no /api/v1 prefix) — keeps existing clients working.
app.include_router(career.router, prefix="/career", tags=["Career (legacy)"], include_in_schema=False)
app.include_router(finance.router, prefix="/finance", tags=["Finance (legacy)"], include_in_schema=False)
app.include_router(startup.router, prefix="/startup", tags=["Startup (legacy)"], include_in_schema=False)
app.include_router(policy.router, prefix="/policy", tags=["Policy (legacy)"], include_in_schema=False)
app.include_router(chatbot.router, prefix="/chatbot", tags=["Chatbot (legacy)"], include_in_schema=False)

# ---------------------------------------------------------------------------
# Health & status endpoints
# ---------------------------------------------------------------------------

_STARTUP_TIME = time.time()


@app.get("/api/v1/health", tags=["System"])
def health_check():
    """
    Production health check endpoint.
    Returns model availability status and uptime.
    """
    from services.model_service import get_model_status

    uptime_seconds = round(time.time() - _STARTUP_TIME, 1)
    model_status = get_model_status()

    all_healthy = all(model_status.values())
    return {
        "status": "healthy" if all_healthy else "degraded",
        "uptime_seconds": uptime_seconds,
        "version": "2.0.0",
        "models": model_status,
    }


@app.get("/", tags=["System"])
def root():
    return {
        "status": "DecisionAI Engine running",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


# ---------------------------------------------------------------------------
# Startup / Warm-up logic
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """
    Solves the 'Cold Start' problem by pre-loading models and 
    warming up the LLM during container boot.
    Also initializes the authentication database.
    """
    logger.info("system_startup warm_up_initiated=true")

    # 0. Initialize auth database
    from utils.database import init_db
    init_db()
    logger.info("auth_database initialized=true")
    
    # 1. Warm up ML Models
    from services.model_service import get_model_status
    status = get_model_status()
    logger.info("ml_models_loaded status=%s", status)

    # 2. Warm up LLM (Groq / OpenAI / Local)
    import httpx
    api_key = os.getenv("GROQ_API_KEY")
    llm_url = os.getenv("GROQ_API_URL") or os.getenv("LLM_API_URL") or os.getenv("OLLAMA_API_URL")
    model = os.getenv("GROQ_MODEL") or os.getenv("LLM_MODEL") or os.getenv("OLLAMA_MODEL", "openai/gpt-oss-20b")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if llm_url:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    llm_url,
                    json={"model": model, "messages": [{"role": "user", "content": "hi"}], "stream": False},
                    headers=headers,
                    timeout=2.0
                )
            logger.info("llm_warmup_triggered success=true")
        except Exception:
            logger.info("llm_warmup_skipped")


@app.on_event("shutdown")
async def shutdown_event():
    # Close the authentication database connection.
    from utils.database import close_db
    close_db()
    logger.info("auth_database closed=true")


# ---------------------------------------------------------------------------
# Global error handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(
        "unhandled_error path=%s request_id=%s error=%s",
        request.url.path,
        request_id,
        exc.__class__.__name__,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "path": request.url.path,
            "error_type": exc.__class__.__name__,
            "request_id": request_id,
        },
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("BACKEND_PORT", "8002"))
    host = os.getenv("BACKEND_HOST", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port, reload=True)

