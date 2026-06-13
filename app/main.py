from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import coach, exercises, intake, meta, plans, sessions, slots, users
from app.core.config import settings

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    from app.modules.catalog.service import vector_search_status

    return {"status": "ok", "embeddings": vector_search_status()}


app.include_router(users.router)
app.include_router(meta.router)
app.include_router(intake.router)
app.include_router(exercises.router)
app.include_router(plans.router)
app.include_router(slots.router)
app.include_router(sessions.router)
app.include_router(coach.router)
