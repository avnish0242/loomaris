from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import admin, apps, auth, chat, cloud, github, health, orgs
from app.core.config import settings
from app.database import engine
from app.models import org, platform  # noqa: F401 — registers ORM models with Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="Loomaris API",
    description=(
        "Self-orchestration SaaS platform — build and deploy applications "
        "through natural language chat, powered by Claude API."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# SessionMiddleware required by authlib for OAuth state/nonce (stored in signed cookie)
app.add_middleware(SessionMiddleware, secret_key=settings.JWT_SECRET_KEY, max_age=300)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(orgs.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(apps.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(cloud.router, prefix="/api/v1")
app.include_router(github.router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root():
    return {
        "name": "Loomaris API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/v1/health",
        "login": "/api/v1/auth/google",
    }
