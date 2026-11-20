from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.db import SessionLocal
from app.jobs.queue import grading_queue
from app.routers import assignments, feedback, grading, submissions


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await grading_queue.start()
    try:
        yield
    finally:
        await grading_queue.stop()


app = FastAPI(title="RubricRunner API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assignments.router)
app.include_router(submissions.router)
app.include_router(feedback.router)
app.include_router(grading.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Report service health, including a real database round-trip."""
    db_status = "ok"
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        db_status = "down"
    return {"status": "ok", "db": db_status}
