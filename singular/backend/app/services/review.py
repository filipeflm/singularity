"""
Serviço de Revisão — Singular
Gerencia a fila de revisão, submissões e atualização do SRS.

Responsabilidades:
  - Retorna cards devidos para revisão (ordenados por urgência)
  - Processa submissão de revisão → atualiza SRSState → cria ReviewLog
  - Calcula métricas de progresso do aluno
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.domain.adaptation import analyze_and_update_patterns
from app.domain.models import (
    Card,
    ExtractedItem,
    Lesson,
    ReviewLog,
    SRSCardState,
    SRSState,
    User,
)
from app.domain.srs import (
    calculate_next_review,
    calculate_retention_probability,
    get_card_urgency_score,
)


# ─── Fila de revisão ──────────────────────────────────────────────────────────

def get_due_cards(
    user_id: int,
    db: Session,
    limit: int = 20,
    include_new: bool = True,
) -> List[Dict]:
    """
    Retorna cards devidos para revisão, ordenados por urgência.

    Inclui:
    - Cards com due_date <= agora (atrasados ou no prazo)
    - Cards NEW (se include_new=True e dentro do limite diário)

    Returns:
        Lista de dicts com card + srs_state + item info
    """
    now = datetime.utcnow()

    # Query: SRSState due + Card + ExtractedItem
    due_states = (
        db.query(SRSState)
        .filter(SRSState.user_id == user_id)
        .filter(
            and_(
                SRSState.due_date <= now,
                SRSState.state != SRSCardState.NEW if not include_new else True,
            )
        )
        .all()
    )

    if include_new:
        new_states = (
            db.query(SRSState)
            .filter(SRSState.user_id == user_id)
            .filter(SRSState.state == SRSCardState.NEW)
            .limit(10)  # máximo de novos por sessão
            .all()
        )
        # Combina sem duplicar
        all_ids = {s.id for s in due_states}
        for s in new_states:
            if s.id not in all_ids:
                due_states.append(s)

    # Ordena por urgência
    due_states.sort(
        key=lambda s: get_card_urgency_score(s.due_date, s.state, s.lapses, now),
        reverse=True,
    )

    result = []
    for srs in due_states[:limit]:
        card = db.query(Card).filter(Card.id == srs.card_id).first()
        if not card:
            continue

        item = db.query(ExtractedItem).filter(
            ExtractedItem.id == card.extracted_item_id
        ).first()

        lesson = db.query(Lesson).filter(Lesson.id == card.lesson_id).first()

        retention = calculate_retention_probability(
            days_since_review=(now - srs.last_reviewed_at).days if srs.last_reviewed_at else 0,
            stability=srs.stability,
        )

        result.append({
            "srs_id": srs.id,
            "card_id": card.id,
            "card_type": card.card_type.value,
            "front": card.front,
            "back": card.back,
            "hint": card.hint,
            "state": srs.state.value,
            "interval": srs.interval,
            "lapses": srs.lapses,
            "retention_probability": round(retention, 2),
            "due_date": srs.due_date.isoformat() if srs.due_date else None,
            "lesson_title": lesson.title if lesson else None,
            "item_type": item.item_type.value if item else None,
            "context_sentence": item.context_sentence if item else None,
        })

    return result


def submit_review(
    user_id: int,
    card_id: int,
    quality: int,
    response_time_ms: Optional[int],
    db: Session,
) -> Dict:
    """
    Processa uma revisão de card.

    Args:
        user_id: ID do usuário
        card_id: ID do card revisado
        quality: Qualidade da resposta 0-5
        response_time_ms: Tempo de resposta em millisegundos
        db: Sessão do banco

    Returns:
        Dict com novo estado do SRS e feedback
    """
    quality = max(0, min(5, quality))  # garante range 0-5

    srs = (
        db.query(SRSState)
        .filter(SRSState.card_id == card_id)
        .filter(SRSState.user_id == user_id)
        .first()
    )

    if not srs:
        raise ValueError(f"SRSState não encontrado para card {card_id}")

    # Snapshot do estado anterior
    state_before = {
        "state": srs.state.value,
        "interval": srs.interval,
        "ease_factor": srs.ease_factor,
        "repetitions": srs.repetitions,
        "lapses": srs.lapses,
    }

    # Calcula próximo estado
    review_result = calculate_next_review(
        quality=quality,
        current_state=srs.state,
        interval=srs.interval,
        ease_factor=srs.ease_factor,
        repetitions=srs.repetitions,
        lapses=srs.lapses,
        stability=srs.stability,
        adaptation_penalty=srs.adaptation_penalty,
    )

    # Atualiza SRSState
    srs.state = review_result.new_state
    srs.interval = review_result.new_interval
    srs.ease_factor = review_result.new_ease_factor
    srs.repetitions = review_result.new_repetitions
    srs.lapses = review_result.new_lapses
    srs.stability = review_result.new_stability
    srs.due_date = review_result.new_due_date
    srs.last_reviewed_at = datetime.utcnow()
    # Reset penalidade após revisão bem-sucedida
    if review_result.was_correct:
        srs.adaptation_penalty = max(0.0, srs.adaptation_penalty - 0.1)

    # Snapshot do estado depois
    state_after = {
        "state": srs.state.value,
        "interval": srs.interval,
        "ease_factor": srs.ease_factor,
        "repetitions": srs.repetitions,
        "lapses": srs.lapses,
    }

    # Cria ReviewLog
    log = ReviewLog(
        card_id=card_id,
        user_id=user_id,
        quality=quality,
        response_time_ms=response_time_ms,
        was_correct=review_result.was_correct,
        srs_state_before=state_before,
        srs_state_after=state_after,
    )
    db.add(log)
    db.commit()

    # Atualiza padrões de erro (análise assíncrona simplificada)
    try:
        analyze_and_update_patterns(user_id, db)
    except Exception:
        pass  # não bloqueia a revisão se análise falhar

    return {
        "card_id": card_id,
        "was_correct": review_result.was_correct,
        "new_state": review_result.new_state.value,
        "new_interval": review_result.new_interval,
        "next_due": review_result.new_due_date.isoformat(),
        "quality": quality,
        "feedback": _quality_feedback(quality),
    }


def _quality_feedback(quality: int) -> str:
    """Gera feedback textual baseado na qualidade."""
    messages = {
        0: "Não lembrou. O card voltará em breve.",
        1: "Errou, mas a resposta era familiar.",
        2: "Errou, mas reconheceu a resposta correta.",
        3: "Correto, mas foi difícil. Continue praticando!",
        4: "Bom! Com um pouco de hesitação.",
        5: "Perfeito! Resposta fácil e rápida.",
    }
    return messages.get(quality, "Revisão registrada.")


# ─── Métricas de progresso ─────────────────────────────────────────────────────

def get_progress_stats(user_id: int, db: Session) -> Dict:
    """
    Retorna estatísticas de progresso do aluno.
    Usado na tela de Progresso.
    """
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    # Total de cards por estado
    states = (
        db.query(SRSState.state, func.count(SRSState.id))
        .filter(SRSState.user_id == user_id)
        .group_by(SRSState.state)
        .all()
    )
    cards_by_state = {state.value: count for state, count in states}

    # Total de revisões (últimos 7 dias)
    recent_reviews = (
        db.query(ReviewLog)
        .filter(ReviewLog.user_id == user_id)
        .filter(ReviewLog.reviewed_at >= week_ago)
        .all()
    )

    total_recent = len(recent_reviews)
    correct_recent = sum(1 for r in recent_reviews if r.was_correct)
    accuracy_7d = (correct_recent / total_recent * 100) if total_recent > 0 else 0

    # Cards devidos agora
    due_now = (
        db.query(SRSState)
        .filter(SRSState.user_id == user_id)
        .filter(SRSState.due_date <= now)
        .count()
    )

    # Aulas importadas
    total_lessons = (
        db.query(Lesson)
        .filter(Lesson.user_id == user_id)
        .count()
    )

    # Vocabulário "dominado" (estado REVIEW com interval > 7 dias)
    mastered = (
        db.query(SRSState)
        .filter(SRSState.user_id == user_id)
        .filter(SRSState.state == SRSCardState.REVIEW)
        .filter(SRSState.interval > 7)
        .count()
    )

    # Taxa de retenção estimada (média das probabilidades)
    all_states = db.query(SRSState).filter(SRSState.user_id == user_id).all()
    retention_probs = []
    for srs in all_states:
        if srs.last_reviewed_at and srs.stability > 0:
            days = (now - srs.last_reviewed_at).total_seconds() / 86400
            prob = calculate_retention_probability(days, srs.stability)
            retention_probs.append(prob)

    avg_retention = (sum(retention_probs) / len(retention_probs) * 100) if retention_probs else 0

    # Revisões por dia dos últimos 7 dias
    daily_reviews = {}
    for i in range(7):
        day = (now - timedelta(days=i)).date()
        count = sum(
            1 for r in recent_reviews
            if r.reviewed_at.date() == day
        )
        daily_reviews[day.isoformat()] = count

    return {
        "total_cards": sum(cards_by_state.values()),
        "cards_by_state": {
            "new": cards_by_state.get("new", 0),
            "learning": cards_by_state.get("learning", 0),
            "review": cards_by_state.get("review", 0),
            "relearning": cards_by_state.get("relearning", 0),
        },
        "cards_due_now": due_now,
        "mastered_cards": mastered,
        "total_lessons": total_lessons,
        "accuracy_7d": round(accuracy_7d, 1),
        "reviews_7d": total_recent,
        "avg_retention_estimate": round(avg_retention, 1),
        "daily_reviews": daily_reviews,
    }
