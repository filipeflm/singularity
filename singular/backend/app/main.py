"""
Singular — API Principal
FastAPI app com todas as rotas registradas.

Startup:
  - Cria tabelas no banco (SQLite)
  - Verifica usuário padrão (single-user MVP)
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import cards, exercises, lessons, progress
from app.database import SessionLocal, create_tables

app = FastAPI(
    title="Singular — Motor de Aprendizado Adaptativo",
    description=(
        "API do Singular: sistema inteligente de aprendizado de idiomas. "
        "Transcreve aulas, extrai conhecimento, gera cards e exercícios adaptativos."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS para o frontend React ─────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rotas ──────────────────────────────────────────────────────────────────────
app.include_router(lessons.router)
app.include_router(cards.router)
app.include_router(exercises.router)
app.include_router(progress.router)


# ── Startup ────────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    """Inicializa banco de dados e usuário padrão."""
    create_tables()
    _ensure_default_user()


def _ensure_default_user():
    """Garante que o usuário padrão (id=1) existe no banco."""
    from app.domain.models import User
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == 1).first()
        if not user:
            user = User(
                id=1,
                name="Estudante",
                email="estudante@singular.app",
                native_language="pt-BR",
            )
            db.add(user)
            db.commit()
    finally:
        db.close()


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "app": "Singular", "version": "0.1.0"}


@app.get("/", tags=["system"])
def root():
    return {
        "message": "Singular API — Motor de Aprendizado Adaptativo",
        "docs": "/docs",
        "version": "0.1.0",
    }
