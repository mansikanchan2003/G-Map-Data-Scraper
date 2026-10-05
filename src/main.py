from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from src.routers import (config, jobs, businesses, discovery, export, runs,
                         whatsapp, tracking, audience, template_studio, insights,
                         auth as auth_router)
from src.database import init_db, get_db
from src.utils.logging import setup_logging

from src.config import settings
from contextlib import asynccontextmanager
import logging
import os

logger = logging.getLogger("gmap_scraper")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    setup_logging()
    logger.info(
        "Starting Autonomous Google Maps Business Discovery Agent | "
        f"env={settings.environment} | db_backend={'postgresql' if settings.is_postgresql else 'sqlite'}"
    )
    init_db()

    # Someone has to be able to read the approvals queue before anyone can be
    # approved, so the first admin is seeded rather than requested.
    try:
        from src.database import SessionLocal
        from src.services.auth_service import ensure_bootstrap_admin
        db = SessionLocal()
        try:
            ensure_bootstrap_admin(db)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Could not seed the bootstrap admin: {e}")
    logger.info("Database schema initialized")

    # The scraping autopilot. It idles until switched on from the dashboard,
    # and runs in this process so it shares the one browser-capable worker.
    # Off under pytest, where a background thread would race the tests' own
    # databases.
    import sys
    if os.environ.get("DISCOVERY_AUTOPILOT_THREAD", "true").lower() == "true" and "pytest" not in sys.modules:
        from src.services import discovery_autopilot
        discovery_autopilot.start()
    yield
    # --- Shutdown ---
    try:
        from src.services import discovery_autopilot
        discovery_autopilot.stop()
    except Exception:
        pass
    logger.info("Shutdown complete")


from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

app = FastAPI(
    title="Autonomous Google Maps Business Discovery Agent",
    version="1.0.0",
    lifespan=lifespan
)

# ---------------------------------------------------------------------------
# GZip — compresses responses above 500 bytes. The JS bundle drops from
# ~775 KB to ~230 KB, and JSON API responses compress well too.
# ---------------------------------------------------------------------------
app.add_middleware(GZipMiddleware, minimum_size=500)

# ---------------------------------------------------------------------------
# CORS — configurable via CORS_ORIGINS env var (comma-separated).
# Development defaults allow localhost Vite dev server.
# Production must set CORS_ORIGINS to actual frontend origin(s).
# Never use allow_origins=["*"] with credentials.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Authentication gate
# ---------------------------------------------------------------------------
# Applied as middleware rather than a dependency on each router: a route added
# later is then protected by default, which is the safer direction to fail.
#
# The exemptions are the endpoints that cannot carry a session cookie:
#   /health, /ready              - probes, called by Docker and by monitoring
#   /api/v1/auth/*               - signing up and signing in
#   /r/{token}                   - campaign links, opened by recipients
#   /api/v1/whatsapp/webhook     - called by Meta, verified by signature
# Everything under / that is not an API path falls through to the SPA shell,
# which has to load for the login page to exist at all.
PUBLIC_API_PREFIXES = (
    "/health",
    "/ready",
    "/api/v1/auth/",
    "/r/",
    "/api/v1/whatsapp/webhook",
)


@app.middleware("http")
async def require_session(request, call_next):
    from starlette.responses import JSONResponse

    path = request.url.path
    is_api = path.startswith("/api/") or path in ("/docs", "/redoc", "/openapi.json")

    if is_api and not any(path.startswith(p) for p in PUBLIC_API_PREFIXES):
        from src.database import SessionLocal
        from src.services import auth_service

        token = request.cookies.get(auth_service.COOKIE_NAME, "")
        db = SessionLocal()
        try:
            # Called even for an empty token: the lookup rejects it anyway,
            # and short-circuiting here would put the decision in two places.
            user = auth_service.user_from_token(db, token)
        finally:
            db.close()

        if not user:
            return JSONResponse({"detail": "Not signed in"}, status_code=401)

    return await call_next(request)


app.include_router(auth_router.router)
app.include_router(config.router)
app.include_router(jobs.router)
app.include_router(businesses.router)
app.include_router(discovery.router)
app.include_router(export.router)
app.include_router(runs.router)
app.include_router(whatsapp.router)
# Short links live at the root (/r/{token}) so campaign URLs stay short.
app.include_router(tracking.router)
app.include_router(audience.router)
app.include_router(template_studio.router)
app.include_router(insights.router)


@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """
    Liveness + database connectivity check.
    Returns HTTP 200 with status='healthy' when the API is alive and
    the database is reachable. Returns HTTP 200 with status='unhealthy'
    when the database is unreachable (so load-balancer probes can detect it).
    """
    from sqlalchemy import text
    from datetime import datetime, timezone

    db_status = "unhealthy"
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as exc:
        logger.error(f"Health check database failure: {exc}")

    overall = "healthy" if db_status == "healthy" else "unhealthy"
    return {
        "status": overall,
        "version": "1.0.0",
        "database": db_status,
        "db_backend": "postgresql" if settings.is_postgresql else "sqlite",
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Health"])
def readiness_check(db: Session = Depends(get_db)):
    """
    Readiness probe. Identical to /health for this single-process deployment.
    Returns 503 via exception if database is not reachable.
    """
    from sqlalchemy import text
    from fastapi import HTTPException

    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error(f"Readiness check failed: {exc}")
        raise HTTPException(status_code=503, detail="Database not reachable")

    return {"status": "ready"}


@app.get("/api/v1/stats", tags=["Stats"])
def get_stats(db: Session = Depends(get_db)):
    from src.models import Location, Category, Job, Business, RunLog
    from src.models.business import CONTACTABLE
    try:
        last_run = db.query(RunLog).order_by(RunLog.started_at.desc()).first()
        last_run_dict = None
        if last_run:
            last_run_dict = {
                "run_id": last_run.run_id,
                "started_at": last_run.started_at.isoformat() if last_run.started_at else None,
                "status": last_run.status,
                "jobs_total": last_run.jobs_total,
                "jobs_completed": last_run.jobs_completed,
                "jobs_failed": last_run.jobs_failed,
                "businesses_discovered": last_run.businesses_discovered,
                "businesses_new": last_run.businesses_new,
                "businesses_updated": last_run.businesses_updated,
                "businesses_duplicate": last_run.businesses_duplicate,
                "email_enriched": last_run.email_enriched,
                "duration_seconds": last_run.duration_seconds,
            }

        return {
            "locations_count": db.query(Location).count(),
            "categories_count": db.query(Category).count(),
            "jobs": {
                "total": db.query(Job).count(),
                "pending": db.query(Job).filter(Job.status == "PENDING").count(),
                "running": db.query(Job).filter(Job.status == "RUNNING").count(),
                "completed": db.query(Job).filter(Job.status == "COMPLETED").count(),
                "partial": db.query(Job).filter(Job.status == "PARTIAL").count(),
                "failed": db.query(Job).filter(Job.status == "FAILED").count(),
                "blocked": db.query(Job).filter(Job.status == "BLOCKED").count(),
            },
            "businesses": {
                "total": db.query(Business).filter(CONTACTABLE).count(),
                "valid": db.query(Business).filter(CONTACTABLE, Business.is_valid == True).count(),
                "invalid": db.query(Business).filter(CONTACTABLE, Business.is_valid == False).count(),
            },
            "last_run": last_run_dict,
        }
    except Exception as e:
        logger.error(f"Stats endpoint error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Built frontend
# ---------------------------------------------------------------------------
# Serving the bundle from the API keeps the deployment to a single upstream
# port, which is what the reverse proxy in front of this expects: one
# location, one proxy_pass. It also makes the API same-origin, so there are no
# CORS rules to keep in step with the public URL.
#
# Mounted last so every API route above wins; the SPA only ever answers for
# paths nothing else claimed.
_FRONTEND_DIR = os.environ.get("FRONTEND_DIST_DIR", "/app/frontend_dist")

if os.path.isdir(_FRONTEND_DIR):
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(_FRONTEND_DIR, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        """
        Hands back a real file when one exists, and index.html otherwise.

        The app routes on the URL hash, so deep links never reach the server as
        paths — but a favicon or a logo does, and those must not be answered
        with the HTML page.
        """
        candidate = os.path.normpath(os.path.join(_FRONTEND_DIR, full_path))
        # normpath collapses "..", so this rejects traversal out of the bundle.
        if (
            full_path
            and candidate.startswith(os.path.abspath(_FRONTEND_DIR))
            and os.path.isfile(candidate)
        ):
            return FileResponse(candidate)

        # index.html names the hashed bundle, so a cached copy pins the browser
        # to whichever build it was fetched with — a deploy then changes
        # nothing until someone thinks to hard-refresh. The assets it points at
        # are content-hashed and safe to cache; this file never is.
        return FileResponse(
            os.path.join(_FRONTEND_DIR, "index.html"),
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    logger.info(f"Serving frontend bundle from {_FRONTEND_DIR}")
else:
    logger.info(
        f"No frontend bundle at {_FRONTEND_DIR}; API-only mode "
        "(the Vite dev server serves the UI in development)"
    )
