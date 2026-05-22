# backend/app.py

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from database import engine, Base
from routes.session_routes import router as session_router
from routes.agent_routes   import router as agent_router
from routes.audio_routes   import router as audio_router
from routes.report_routes  import router as report_router

# ---------------------------------------------------------------------------
# Load .env FIRST before reading any env vars
# ---------------------------------------------------------------------------
# Explicitly point load_dotenv() to the .env file sitting next to app.py
# This guarantees it loads regardless of which directory you run uvicorn from
_ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_ENV_FILE, override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

logger.info(f"Loading .env from: {_ENV_FILE}  (exists={_ENV_FILE.exists()})")

# ---------------------------------------------------------------------------
# Paths — completely automatic, zero configuration needed
#
# __file__ = C:\Users\DELL\Desktop\interview bot\backend\app.py
# BASE_DIR = C:\Users\DELL\Desktop\interview bot\backend
# PROJECT_ROOT = C:\Users\DELL\Desktop\interview bot
# FRONTEND_DIR = C:\Users\DELL\Desktop\interview bot\frontend
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
BASE_DIR = PROJECT_ROOT
# Only use env var override if explicitly set AND the path actually exists
# Otherwise always fall back to automatic sibling-folder detection
def _resolve_dir(env_key: str, default: Path) -> Path:
    """
    Resolves a directory path:
    1. If env var is set AND the path exists → use it
    2. If env var is set but path does NOT exist → warn and use default
    3. If env var not set → use default (auto-detected)
    """
    env_val = os.getenv(env_key, "").strip()
    if env_val:
        p = Path(env_val)
        if p.exists():
            return p
        else:
            logger.warning(
                f"[PATH] {env_key}={env_val} does not exist. "
                f"Falling back to auto-detected: {default}"
            )
    return default


FRONTEND_DIR = _resolve_dir("FRONTEND_DIR", PROJECT_ROOT / "frontend")
UPLOADS_DIR  = _resolve_dir("UPLOADS_DIR",  PROJECT_ROOT / "uploads")
AUDIO_DIR    = _resolve_dir("AUDIO_DIR",    PROJECT_ROOT / "audio")

# ---------------------------------------------------------------------------
# Print resolved paths — you will see these in terminal on startup
# ---------------------------------------------------------------------------
logger.info("=" * 60)
logger.info(f"  BASE_DIR     : {BASE_DIR}")
logger.info(f"  PROJECT_ROOT : {PROJECT_ROOT}")
logger.info(f"  FRONTEND_DIR : {FRONTEND_DIR}")
logger.info(f"  UPLOADS_DIR  : {UPLOADS_DIR}")
logger.info(f"  AUDIO_DIR    : {AUDIO_DIR}")
logger.info(f"  .env loaded  : {_ENV_FILE.exists()}")
logger.info("=" * 60)

# ---------------------------------------------------------------------------
# Startup sanity check — fail fast with clear message
# ---------------------------------------------------------------------------
if not FRONTEND_DIR.exists():
    logger.error(
        f"\n"
        f"{'='*60}\n"
        f"  FRONTEND DIRECTORY NOT FOUND\n"
        f"  Expected at : {FRONTEND_DIR}\n"
        f"  app.py is at: {BASE_DIR}\n"
        f"  Make sure your project looks like:\n"
        f"\n"
        f"  interview bot/\n"
        f"  ├── backend/\n"
        f"  │   └── app.py     ← you are here\n"
        f"  └── frontend/      ← must exist here\n"
        f"      ├── index.html\n"
        f"      ├── interview.html\n"
        f"      └── report.html\n"
        f"{'='*60}"
    )
else:
    html_files = [f.name for f in FRONTEND_DIR.glob("*.html")]
    logger.info(f"Frontend OK | HTML files found: {html_files}")

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Creating database tables…")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready.")

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True,   exist_ok=True)
    logger.info("Runtime directories ready.")

    yield
    logger.info("Shutting down.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AI Voice Interview System",
    version="1.0.0",
    lifespan=lifespan,
    docs_url ="/docs"  if os.getenv("ENV", "development") != "production" else None,
    redoc_url="/redoc" if os.getenv("ENV", "development") != "production" else None,
)

# ---------------------------------------------------------------------------
# Rate limiter middleware
# ---------------------------------------------------------------------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static mounts — BEFORE routers
# ---------------------------------------------------------------------------
if AUDIO_DIR.exists():
    app.mount("/audio",   StaticFiles(directory=str(AUDIO_DIR)),   name="audio")
    logger.info(f"Mounted /audio   → {AUDIO_DIR}")
else:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/audio",   StaticFiles(directory=str(AUDIO_DIR)),   name="audio")
    logger.info(f"Created & mounted /audio → {AUDIO_DIR}")

if UPLOADS_DIR.exists():
    app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
    logger.info(f"Mounted /uploads → {UPLOADS_DIR}")
else:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
    logger.info(f"Created & mounted /uploads → {UPLOADS_DIR}")

if FRONTEND_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(FRONTEND_DIR)),
        name="frontend_static",
    )
    logger.info(f"Mounted /static  → {FRONTEND_DIR}")

# ---------------------------------------------------------------------------
# API Routers
# ---------------------------------------------------------------------------
app.include_router(session_router, prefix="/session", tags=["Session"])
app.include_router(agent_router,   prefix="/agent",   tags=["Agent"])
app.include_router(audio_router,   prefix="",         tags=["Audio"])
app.include_router(report_router,  prefix="/report",  tags=["Report"])


# ---------------------------------------------------------------------------
# HTML page routes
# ---------------------------------------------------------------------------
def serve_html(filename: str):
    """Serve an HTML file from FRONTEND_DIR with a clear error if missing."""
    path = FRONTEND_DIR / filename
    if not path.exists():
        logger.error(f"HTML file not found: {path}")
        return JSONResponse(
            status_code=404,
            content={
                "detail": (
                    f"'{filename}' not found at {path}.\n"
                    f"FRONTEND_DIR resolved to: {FRONTEND_DIR}\n"
                    f"PROJECT_ROOT is: {PROJECT_ROOT}\n"
                    f"app.py is at: {BASE_DIR / 'app.py'}"
                )
            },
        )
    logger.info(f"Serving {filename} from {path}")
    return FileResponse(str(path))


# @app.get("/", include_in_schema=False)
# async def serve_index():
#     return serve_html("index.html")

@app.get("/")
async def serve_index():
    return FileResponse(Path("frontend") / "index.html")


# @app.get("/", include_in_schema=False)
# async def serve_index():
#     return serve_html("index.html")

# @app.get("/interview",      include_in_schema=False)
@app.get("/interview", include_in_schema=False)
@app.get("/interview.html", include_in_schema=False)
async def serve_interview():
    return serve_html("interview.html")


@app.get("/report",      include_in_schema=False)
@app.get("/report.html", include_in_schema=False)
async def serve_report_page():
    return serve_html("report.html")


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(
        f"Unhandled exception | {request.method} {request.url.path}"
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# Health — shows all resolved paths
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status"          : "ok",
        "base_dir"        : str(BASE_DIR),
        "project_root"    : str(PROJECT_ROOT),
        "frontend_dir"    : str(FRONTEND_DIR),
        "frontend_exists" : FRONTEND_DIR.exists(),
        "html_files"      : (
            [f.name for f in FRONTEND_DIR.glob("*.html")]
            if FRONTEND_DIR.exists() else []
        ),
        "uploads_dir"     : str(UPLOADS_DIR),
        "audio_dir"       : str(AUDIO_DIR),
        "env_file"        : str(_ENV_FILE),
        "env_file_exists" : _ENV_FILE.exists(),
    }