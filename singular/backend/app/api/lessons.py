"""
API de Aulas — Singular
Rotas para importar e consultar aulas.

POST /lessons          → Cria aula + dispara pipeline
GET  /lessons          → Lista aulas do usuário
GET  /lessons/{id}     → Detalhes de uma aula
GET  /lessons/{id}/status → Status do pipeline
DELETE /lessons/{id}   → Remove aula e todos os dados associados
"""

import threading
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain.models import (
    Card,
    ExtractedItem,
    Exercise,
    Lesson,
    LessonStatus,
    SRSState,
    Transcript,
)
from app.services.pipeline import run_import_pipeline

router = APIRouter(prefix="/lessons", tags=["lessons"])

# ─── Schemas ──────────────────────────────────────────────────────────────────

class LessonCreate(BaseModel):
    url: Optional[str] = None
    title: Optional[str] = None
    language: str = "ja"
    use_mock: bool = False  # True para testar sem API/YouTube


class LessonResponse(BaseModel):
    id: int
    url: Optional[str]
    title: Optional[str]
    language: Optional[str]
    level: Optional[str]
    status: str
    error_message: Optional[str]
    created_at: str
    processed_at: Optional[str]
    cards_count: int = 0
    exercises_count: int = 0

    class Config:
        from_attributes = True


# ─── Rotas ────────────────────────────────────────────────────────────────────

@router.post("", response_model=LessonResponse, status_code=201)
def create_lesson(
    payload: LessonCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Importa uma nova aula.
    O pipeline de processamento roda em background.
    Retorna imediatamente com status=pending.
    """
    # Validação básica
    if not payload.use_mock and not payload.url:
        raise HTTPException(
            status_code=422,
            detail="Forneça uma URL do YouTube ou use use_mock=true para testar.",
        )

    # Cria a aula no banco (status=pending)
    lesson = Lesson(
        user_id=1,  # single-user MVP
        url=payload.url,
        title=payload.title or _extract_title_from_url(payload.url),
        language=payload.language,
        status=LessonStatus.PENDING,
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)

    # Dispara pipeline em background
    background_tasks.add_task(
        _run_pipeline_background,
        lesson_id=lesson.id,
        user_id=1,
        use_mock=payload.use_mock,
    )

    return _lesson_to_response(lesson, db)


@router.get("", response_model=list)
def list_lessons(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    """Lista todas as aulas do usuário, ordenadas por data de criação (mais recente primeiro)."""
    lessons = (
        db.query(Lesson)
        .filter(Lesson.user_id == 1)
        .order_by(Lesson.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_lesson_to_response(l, db) for l in lessons]


@router.get("/{lesson_id}", response_model=LessonResponse)
def get_lesson(lesson_id: int, db: Session = Depends(get_db)):
    """Retorna detalhes de uma aula específica."""
    lesson = _get_or_404(lesson_id, db)
    return _lesson_to_response(lesson, db)


@router.get("/{lesson_id}/status")
def get_lesson_status(lesson_id: int, db: Session = Depends(get_db)):
    """Retorna status do pipeline para polling da UI."""
    lesson = _get_or_404(lesson_id, db)

    cards_count = db.query(Card).filter(Card.lesson_id == lesson_id).count()
    exercises_count = (
        db.query(Exercise)
        .join(Card, Exercise.card_id == Card.id)
        .filter(Card.lesson_id == lesson_id)
        .count()
    )
    items_count = (
        db.query(ExtractedItem).filter(ExtractedItem.lesson_id == lesson_id).count()
    )

    return {
        "lesson_id": lesson_id,
        "status": lesson.status.value,
        "error_message": lesson.error_message,
        "cards_count": cards_count,
        "exercises_count": exercises_count,
        "items_count": items_count,
        "processed_at": lesson.processed_at.isoformat() if lesson.processed_at else None,
    }


@router.get("/{lesson_id}/items")
def get_lesson_items(lesson_id: int, db: Session = Depends(get_db)):
    """Retorna os itens extraídos de uma aula."""
    _get_or_404(lesson_id, db)

    items = (
        db.query(ExtractedItem)
        .filter(ExtractedItem.lesson_id == lesson_id)
        .all()
    )

    return [
        {
            "id": item.id,
            "type": item.item_type.value,
            "content": item.content,
            "reading": item.reading,
            "translation": item.translation,
            "context_sentence": item.context_sentence,
            "explanation": item.explanation,
            "complexity": item.complexity,
            "usefulness": item.usefulness,
        }
        for item in items
    ]


@router.delete("/{lesson_id}", status_code=204)
def delete_lesson(lesson_id: int, db: Session = Depends(get_db)):
    """Remove aula e todos os dados associados (cascade)."""
    lesson = _get_or_404(lesson_id, db)

    # Remove em cascata manualmente (SQLite não tem CASCADE fácil)
    cards = db.query(Card).filter(Card.lesson_id == lesson_id).all()
    for card in cards:
        db.query(Exercise).filter(Exercise.card_id == card.id).delete()
        db.query(SRSState).filter(SRSState.card_id == card.id).delete()
    db.query(Card).filter(Card.lesson_id == lesson_id).delete()
    db.query(ExtractedItem).filter(ExtractedItem.lesson_id == lesson_id).delete()
    db.query(Transcript).filter(Transcript.lesson_id == lesson_id).delete()
    db.delete(lesson)
    db.commit()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_or_404(lesson_id: int, db: Session) -> Lesson:
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Aula não encontrada.")
    return lesson


def _lesson_to_response(lesson: Lesson, db: Session) -> dict:
    cards_count = db.query(Card).filter(Card.lesson_id == lesson.id).count()
    exercises_count = (
        db.query(Exercise)
        .join(Card, Exercise.card_id == Card.id)
        .filter(Card.lesson_id == lesson.id)
        .count()
    )
    return {
        "id": lesson.id,
        "url": lesson.url,
        "title": lesson.title,
        "language": lesson.language,
        "level": lesson.level,
        "status": lesson.status.value,
        "error_message": lesson.error_message,
        "created_at": lesson.created_at.isoformat() if lesson.created_at else None,
        "processed_at": lesson.processed_at.isoformat() if lesson.processed_at else None,
        "cards_count": cards_count,
        "exercises_count": exercises_count,
    }


def _extract_title_from_url(url: Optional[str]) -> Optional[str]:
    """Extrai um título básico da URL enquanto o pipeline não busca o título real."""
    if not url:
        return None
    if "youtu" in url:
        return f"Aula do YouTube"
    return url[:50] if url else None


def _run_pipeline_background(lesson_id: int, user_id: int, use_mock: bool):
    """Executa o pipeline em background com nova sessão do banco."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        run_import_pipeline(
            lesson_id=lesson_id,
            user_id=user_id,
            db=db,
            use_mock=use_mock,
        )
    finally:
        db.close()
