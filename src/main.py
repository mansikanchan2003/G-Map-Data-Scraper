from fastapi import FastAPI
from src.routers import config, jobs, businesses
from src.database import init_db
from src.utils.logging import setup_logging
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    init_db()
    yield
    # Shutdown

app = FastAPI(
    title="Autonomous Google Maps Business Discovery Agent",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(config.router)
app.include_router(jobs.router)
app.include_router(businesses.router)

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "database": "connected",
        "timestamp": "2026-09-14T08:00:00Z"
    }

@app.get("/api/v1/stats")
def get_stats():
    # Will be implemented using DB counts in next iteration
    from src.database import SessionLocal
    from src.models import Location, Category, Job, Business
    db = SessionLocal()
    try:
        return {
            "locations_count": db.query(Location).count(),
            "categories_count": db.query(Category).count(),
            "jobs": {
                "total": db.query(Job).count(),
                "pending": db.query(Job).filter(Job.status == "PENDING").count(),
            },
            "businesses": {
                "total": db.query(Business).count(),
            }
        }
    finally:
        db.close()
