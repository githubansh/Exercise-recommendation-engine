from fastapi import FastAPI

from app.api import coach, exercises, plans, sessions, slots, users
from app.core.config import settings

app = FastAPI(title=settings.app_name)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(users.router)
app.include_router(exercises.router)
app.include_router(plans.router)
app.include_router(slots.router)
app.include_router(sessions.router)
app.include_router(coach.router)
