from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from src.routers import config, jobs, businesses, discovery, export, runs
from src.database import init_db, get_db
from src.utils.logging import setup_logging
from src.services.discovery_engine import discovery_engine
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    init_db()
    yield
    # Shutdown
    discovery_engine.close()

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Autonomous Google Maps Business Discovery Agent",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(config.router)
app.include_router(jobs.router)
app.include_router(businesses.router)
app.include_router(discovery.router)
app.include_router(export.router)
app.include_router(runs.router)

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    from sqlalchemy import text
    from datetime import datetime, timezone
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception:
        db_status = "unhealthy"
        
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "version": "1.0.0",
        "database": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/v1/stats")
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
                "duration_seconds": last_run.duration_seconds
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
            "last_run": last_run_dict
        }
    except Exception as e:
        return {"error": str(e)}
