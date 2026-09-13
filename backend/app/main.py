"""AegisAI FastAPI entrypoint."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.predict import router as predict_router

app = FastAPI(title="AegisAI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(predict_router)


@app.get("/", tags=["root"])
def root() -> dict:
    return {"service": "aegis-ai", "docs": "/docs"}
