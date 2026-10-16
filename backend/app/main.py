from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.decisions import router as decisions_router
from app.api.evaluation import router as evaluation_router
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.models import router as models_router


app = FastAPI(
    title="LLM Resource Optimization Gateway",
    description="Multi-agent LLM routing and resource optimization gateway.",
    version="0.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(
    health_router,
    prefix="/health",
    tags=["Health"],
)

app.include_router(
    chat_router,
    prefix="/chat",
    tags=["Chat"],
)

app.include_router(
    conversations_router,
    prefix="/conversations",
    tags=["Conversations"],
)

app.include_router(
    decisions_router,
    prefix="/decisions",
    tags=["Decisions"],
)

app.include_router(
    evaluation_router,
    prefix="/evaluation",
    tags=["Evaluation"],
)

app.include_router(
    models_router,
    prefix="/models",
    tags=["Models"],
)

app.include_router(
    metrics_router,
    prefix="/metrics",
    tags=["Metrics"],
)


@app.get("/", tags=["Root"])
def root():
    return {
        "name": "LLM Resource Optimization Gateway",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }