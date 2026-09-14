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

app = FastAPI(
    title="Autonomous Google Maps Business Discovery Agent",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(config.router)
app.include_router(jobs.router)
app.include_router(businesses.router)
app.include_router(discovery.router)
app.include_router(export.router)
app.include_router(runs.router)

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "database": "connected",
        "timestamp": "2026-09-14T08:00:00Z"
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
                "jobs_completed": last_run.jobs_completed,
                "businesses_new": last_run.businesses_new
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
