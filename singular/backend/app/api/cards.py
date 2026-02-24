"""
API de Cards e Revisão — Singular
Rotas para revisão espaçada de cards.

GET  /review/due           → Retorna cards para revisar agora
POST /review/submit        → Submete resultado de uma revisão
GET  /review/stats         → Estatísticas da fila de revisão
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain.models import Card, ExtractedItem, SRSState
from app.services.review import get_due_cards, submit_review

router = APIRouter(prefix="/review", tags=["review"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ReviewSubmit(BaseModel):
    card_id: int
    quality: int = Field(..., ge=0, le=5, description="Qualidade 0-5 (SM-2)")
    response_time_ms: Optional[int] = None


# ─── Rotas ────────────────────────────────────────────────────────────────────

@router.get("/due")
def get_cards_due(
    limit: int = 20,
    include_new: bool = True,
    db: Session = Depends(get_db),
):
    """
    Retorna cards devidos para revisão agora.
    Ordenados por urgência (relearning > learning > review > new).
    """
    cards = get_due_cards(
        user_id=1,
        db=db,
        limit=limit,
        include_new=include_new,
    )
    return {
        "cards": cards,
        "total": len(cards),
    }


@router.post("/submit")
def submit_card_review(
    payload: ReviewSubmit,
    db: Session = Depends(get_db),
):
    """
    Submete o resultado de uma revisão de card.

    quality:
      0 = esquecimento total
      1 = errado, resposta parecia familiar
      2 = errado, mas resposta correta era fácil ao ver
      3 = correto com dificuldade
      4 = correto após hesitação
      5 = correto e fácil
    """
    try:
        result = submit_review(
            user_id=1,
            card_id=payload.card_id,
            quality=payload.quality,
            response_time_ms=payload.response_time_ms,
            db=db,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/stats")
def get_review_queue_stats(db: Session = Depends(get_db)):
    """
    Retorna estatísticas rápidas da fila de revisão.
    Útil para o header da UI mostrar quantos cards estão pendentes.
    """
    from datetime import datetime
    from sqlalchemy import func
    from app.domain.models import SRSCardState

    now = datetime.utcnow()

    due_count = (
        db.query(SRSState)
        .filter(SRSState.user_id == 1)
        .filter(SRSState.due_date <= now)
        .count()
    )

    new_count = (
        db.query(SRSState)
        .filter(SRSState.user_id == 1)
        .filter(SRSState.state == SRSCardState.NEW)
        .count()
    )

    relearning_count = (
        db.query(SRSState)
        .filter(SRSState.user_id == 1)
        .filter(SRSState.state == SRSCardState.RELEARNING)
        .count()
    )

    return {
        "due_now": due_count,
        "new_cards": new_count,
        "relearning": relearning_count,
        "total_pending": due_count + new_count,
    }
