"""
API de Exercícios — Singular
Rotas para exercícios ativos adaptativos.

GET  /exercises           → Retorna exercícios para praticar
POST /exercises/submit    → Submete resposta + avalia + registra
GET  /exercises/by-lesson/{id} → Exercícios de uma aula específica
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain.adaptation import get_recommended_exercise_type
from app.domain.models import Card, Exercise, ExerciseSubmission, ExerciseType
from app.services.exercise import evaluate_answer

router = APIRouter(prefix="/exercises", tags=["exercises"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ExerciseSubmit(BaseModel):
    exercise_id: int
    user_answer: str
    response_time_ms: Optional[int] = None


# ─── Rotas ────────────────────────────────────────────────────────────────────

@router.get("")
def get_exercises(
    limit: int = Query(10, ge=1, le=50),
    exercise_type: Optional[str] = Query(None),
    lesson_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Retorna exercícios para praticar.
    Prioriza o tipo recomendado pelo motor de adaptação.
    """
    # Consulta base
    query = db.query(Exercise).join(Card, Exercise.card_id == Card.id)

    if lesson_id:
        query = query.filter(Card.lesson_id == lesson_id)

    # Filtra por tipo se especificado
    if exercise_type:
        try:
            ex_type = ExerciseType(exercise_type)
            query = query.filter(Exercise.exercise_type == ex_type)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Tipo inválido. Use: translation, fill_blank, build_sentence",
            )
    else:
        # Sem tipo especificado → tenta usar o tipo recomendado pelo motor adaptativo
        recommended = get_recommended_exercise_type(user_id=1, db=db)
        if recommended:
            query = query.filter(Exercise.exercise_type == recommended)

    exercises = query.limit(limit).all()

    return {
        "exercises": [_exercise_to_dict(ex, db) for ex in exercises],
        "total": len(exercises),
    }


@router.post("/submit")
def submit_exercise(
    payload: ExerciseSubmit,
    db: Session = Depends(get_db),
):
    """
    Submete uma resposta para um exercício.
    Avalia automaticamente e registra para o motor adaptativo.
    """
    exercise = db.query(Exercise).filter(Exercise.id == payload.exercise_id).first()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercício não encontrado.")

    # Avalia a resposta
    evaluation = evaluate_answer(
        user_answer=payload.user_answer,
        expected_answer=exercise.expected_answer,
        exercise_type=exercise.exercise_type,
    )

    # Registra a submissão
    submission = ExerciseSubmission(
        exercise_id=exercise.id,
        user_id=1,
        user_answer=payload.user_answer,
        is_correct=evaluation.is_correct,
        score=evaluation.score,
        response_time_ms=payload.response_time_ms,
        error_category=evaluation.error_category,
    )
    db.add(submission)
    db.commit()

    # Atualiza padrões de erro se errou
    if not evaluation.is_correct:
        try:
            from app.domain.adaptation import analyze_and_update_patterns
            analyze_and_update_patterns(user_id=1, db=db)
        except Exception:
            pass

    return {
        "exercise_id": exercise.id,
        "is_correct": evaluation.is_correct,
        "score": evaluation.score,
        "feedback": evaluation.feedback,
        "error_category": evaluation.error_category,
        "expected_answer": exercise.expected_answer,
        "user_answer": payload.user_answer,
    }


@router.get("/by-lesson/{lesson_id}")
def get_exercises_by_lesson(
    lesson_id: int,
    db: Session = Depends(get_db),
):
    """Retorna todos os exercícios de uma aula específica."""
    exercises = (
        db.query(Exercise)
        .join(Card, Exercise.card_id == Card.id)
        .filter(Card.lesson_id == lesson_id)
        .all()
    )

    return {
        "lesson_id": lesson_id,
        "exercises": [_exercise_to_dict(ex, db) for ex in exercises],
        "total": len(exercises),
    }


@router.get("/{exercise_id}")
def get_exercise(exercise_id: int, db: Session = Depends(get_db)):
    """Retorna um exercício específico."""
    exercise = db.query(Exercise).filter(Exercise.id == exercise_id).first()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercício não encontrado.")
    return _exercise_to_dict(exercise, db)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _exercise_to_dict(exercise: Exercise, db: Session) -> dict:
    card = db.query(Card).filter(Card.id == exercise.card_id).first()
    return {
        "id": exercise.id,
        "card_id": exercise.card_id,
        "type": exercise.exercise_type.value,
        "prompt": exercise.prompt,
        "context": exercise.context,
        "options": exercise.options,
        # NÃO expõe expected_answer aqui (enviado só na avaliação)
        "card_type": card.card_type.value if card else None,
    }
