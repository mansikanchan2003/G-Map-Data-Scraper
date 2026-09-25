from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from src.routers import config, jobs, businesses, discovery, export, runs, whatsapp, tracking, audience
from src.database import init_db, get_db
from src.utils.logging import setup_logging

from src.config import settings
from contextlib import asynccontextmanager
import logging

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
    logger.info("Database schema initialized")
    yield
    # --- Shutdown ---
    logger.info("Shutdown complete")


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Autonomous Google Maps Business Discovery Agent",
    version="1.0.0",
    lifespan=lifespan
)

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
                "total": db.query(Business).count(),
                "valid": db.query(Business).filter(Business.is_valid == True).count(),
                "invalid": db.query(Business).filter(Business.is_valid == False).count(),
            },
            "last_run": last_run_dict,
        }
    except Exception as e:
        logger.error(f"Stats endpoint error: {e}")
        return {"error": str(e)}
