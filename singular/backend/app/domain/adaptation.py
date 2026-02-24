"""
Motor de Adaptação — Singular
Detecta padrões de erro do aluno e ajusta o sistema de ensino.

Lógica central (bigbang.md §6):
  - Detecta quais palavras o aluno sempre esquece
  - Detecta quais estruturas causam confusão
  - Distingue erro de vocabulário vs. erro de estrutura
  - Ajusta: intervalos SRS, tipo de exercício prioritário, novos cards/dia

O erro não é punição — é dado. (bigbang.md §5)
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.domain.models import (
    Card,
    CardType,
    ErrorPattern,
    ExerciseSubmission,
    ExerciseType,
    PatternType,
    ReviewLog,
    SRSState,
    User,
)


# ─── Constantes de detecção ────────────────────────────────────────────────────

# Se taxa de erro em vocab superar este threshold → vocab_weakness
VOCAB_ERROR_THRESHOLD = 0.40

# Se taxa de erro em grammar superar este threshold → grammar_confusion
GRAMMAR_ERROR_THRESHOLD = 0.35

# Se taxa de erro em build_sentence superar este threshold → structure_confusion
STRUCTURE_ERROR_THRESHOLD = 0.45

# Janela de análise (últimos N dias)
ANALYSIS_WINDOW_DAYS = 7

# Mínimo de revisões para análise ser válida
MIN_REVIEWS_FOR_ANALYSIS = 5

# Severidade máxima de um padrão (aumenta com repetição)
MAX_SEVERITY = 1.0

# Incremento de severidade por detecção
SEVERITY_INCREMENT = 0.2


# ─── Funções principais ────────────────────────────────────────────────────────

def analyze_and_update_patterns(user_id: int, db: Session) -> List[ErrorPattern]:
    """
    Analisa o histórico recente do usuário e atualiza os ErrorPatterns.
    Chamado após cada sessão de revisão ou exercício.

    Returns:
        Lista de padrões ativos (atualizados ou criados)
    """
    cutoff = datetime.utcnow() - timedelta(days=ANALYSIS_WINDOW_DAYS)
    active_patterns = []

    # ── Análise de ReviewLog ───────────────────────────────────────────────────
    recent_reviews = (
        db.query(ReviewLog)
        .filter(ReviewLog.user_id == user_id)
        .filter(ReviewLog.reviewed_at >= cutoff)
        .all()
    )

    if len(recent_reviews) >= MIN_REVIEWS_FOR_ANALYSIS:
        vocab_patterns = _analyze_vocab_errors(user_id, recent_reviews, db)
        grammar_patterns = _analyze_grammar_errors(user_id, recent_reviews, db)
        active_patterns.extend(vocab_patterns + grammar_patterns)

    # ── Análise de ExerciseSubmissions ────────────────────────────────────────
    recent_submissions = (
        db.query(ExerciseSubmission)
        .filter(ExerciseSubmission.user_id == user_id)
        .filter(ExerciseSubmission.submitted_at >= cutoff)
        .all()
    )

    if len(recent_submissions) >= MIN_REVIEWS_FOR_ANALYSIS:
        structure_patterns = _analyze_structure_errors(user_id, recent_submissions, db)
        active_patterns.extend(structure_patterns)

    db.commit()
    return active_patterns


def _analyze_vocab_errors(
    user_id: int, reviews: List[ReviewLog], db: Session
) -> List[ErrorPattern]:
    """Detecta fraqueza em vocabulário."""
    vocab_errors = []
    affected_cards = []

    for review in reviews:
        card = db.query(Card).filter(Card.id == review.card_id).first()
        if card and card.card_type == CardType.VOCAB:
            if not review.was_correct:
                vocab_errors.append(review)
                affected_cards.append(card.id)

    vocab_reviews = [
        r for r in reviews
        if _get_card_type(r.card_id, db) == CardType.VOCAB
    ]

    if not vocab_reviews:
        return []

    error_rate = len(vocab_errors) / len(vocab_reviews) if vocab_reviews else 0

    if error_rate >= VOCAB_ERROR_THRESHOLD:
        pattern = _upsert_pattern(
            user_id=user_id,
            pattern_type=PatternType.VOCAB_WEAKNESS,
            description=f"Taxa de erro em vocabulário: {error_rate:.0%} nas últimas revisões.",
            affected_cards=list(set(affected_cards)),
            db=db,
        )
        # Aplica penalidade SRS aos cards afetados
        _apply_srs_penalty_to_cards(list(set(affected_cards)), 0.6, db)
        return [pattern]

    return []


def _analyze_grammar_errors(
    user_id: int, reviews: List[ReviewLog], db: Session
) -> List[ErrorPattern]:
    """Detecta confusão em estruturas gramaticais."""
    grammar_errors = []
    affected_cards = []

    for review in reviews:
        card_type = _get_card_type(review.card_id, db)
        if card_type == CardType.GRAMMAR and not review.was_correct:
            grammar_errors.append(review)
            affected_cards.append(review.card_id)

    grammar_reviews = [
        r for r in reviews
        if _get_card_type(r.card_id, db) == CardType.GRAMMAR
    ]

    if not grammar_reviews:
        return []

    error_rate = len(grammar_errors) / len(grammar_reviews)

    if error_rate >= GRAMMAR_ERROR_THRESHOLD:
        pattern = _upsert_pattern(
            user_id=user_id,
            pattern_type=PatternType.GRAMMAR_CONFUSION,
            description=f"Confusão em estruturas gramaticais: {error_rate:.0%} de erro.",
            affected_cards=list(set(affected_cards)),
            db=db,
        )
        _apply_srs_penalty_to_cards(list(set(affected_cards)), 0.5, db)
        return [pattern]

    return []


def _analyze_structure_errors(
    user_id: int, submissions: List[ExerciseSubmission], db: Session
) -> List[ErrorPattern]:
    """Detecta confusão na ordem de frases via exercícios build_sentence."""
    from app.domain.models import Exercise

    structure_errors = []
    affected_cards = []

    for submission in submissions:
        exercise = db.query(Exercise).filter(
            Exercise.id == submission.exercise_id
        ).first()
        if exercise and exercise.exercise_type == ExerciseType.BUILD_SENTENCE:
            if not submission.is_correct:
                structure_errors.append(submission)
                if exercise.card_id:
                    affected_cards.append(exercise.card_id)

    structure_submissions = [
        s for s in submissions
        if _get_exercise_type(s.exercise_id, db) == ExerciseType.BUILD_SENTENCE
    ]

    if not structure_submissions:
        return []

    error_rate = len(structure_errors) / len(structure_submissions)

    if error_rate >= STRUCTURE_ERROR_THRESHOLD:
        pattern = _upsert_pattern(
            user_id=user_id,
            pattern_type=PatternType.STRUCTURE_CONFUSION,
            description=f"Dificuldade com ordem de frases: {error_rate:.0%} de erro.",
            affected_cards=list(set(affected_cards)),
            db=db,
        )
        return [pattern]

    return []


def get_recommended_exercise_type(user_id: int, db: Session) -> Optional[ExerciseType]:
    """
    Retorna o tipo de exercício mais recomendado para o aluno
    com base nos padrões de erro ativos.
    """
    active_patterns = (
        db.query(ErrorPattern)
        .filter(ErrorPattern.user_id == user_id)
        .filter(ErrorPattern.is_active == True)
        .order_by(ErrorPattern.severity.desc())
        .all()
    )

    if not active_patterns:
        return None

    top_pattern = active_patterns[0]

    # Mapeia padrão → tipo de exercício que combate essa fraqueza
    pattern_to_exercise = {
        PatternType.VOCAB_WEAKNESS: ExerciseType.TRANSLATION,
        PatternType.GRAMMAR_CONFUSION: ExerciseType.FILL_BLANK,
        PatternType.STRUCTURE_CONFUSION: ExerciseType.BUILD_SENTENCE,
    }

    return pattern_to_exercise.get(top_pattern.pattern_type)


def get_daily_new_cards_limit(user_id: int, db: Session, default: int = 10) -> int:
    """
    Retorna o limite diário de novos cards com base nos padrões ativos.
    Se o aluno tem muitos padrões de erro severos, reduz o limite para
    priorizar consolidação (bigbang.md §7: aprender menos, aprender melhor).
    """
    active_patterns = (
        db.query(ErrorPattern)
        .filter(ErrorPattern.user_id == user_id)
        .filter(ErrorPattern.is_active == True)
        .all()
    )

    if not active_patterns:
        return default

    # Calcula severidade média
    avg_severity = sum(p.severity for p in active_patterns) / len(active_patterns)

    # Reduz novos cards proporcionalmente à severidade
    # severity=0.5 → 70% do limite; severity=1.0 → 40% do limite
    reduction = 0.4 + (1.0 - avg_severity) * 0.6
    return max(3, round(default * reduction))


def resolve_pattern_if_improved(user_id: int, db: Session) -> List[ErrorPattern]:
    """
    Verifica se padrões de erro melhoraram e os marca como resolvidos.
    Um padrão é resolvido quando a taxa de erro cai abaixo de 20%.
    """
    resolved = []
    cutoff = datetime.utcnow() - timedelta(days=ANALYSIS_WINDOW_DAYS)

    active_patterns = (
        db.query(ErrorPattern)
        .filter(ErrorPattern.user_id == user_id)
        .filter(ErrorPattern.is_active == True)
        .all()
    )

    recent_reviews = (
        db.query(ReviewLog)
        .filter(ReviewLog.user_id == user_id)
        .filter(ReviewLog.reviewed_at >= cutoff)
        .all()
    )

    for pattern in active_patterns:
        if pattern.items_affected:
            pattern_card_ids = set(pattern.items_affected)
            pattern_reviews = [r for r in recent_reviews if r.card_id in pattern_card_ids]

            if len(pattern_reviews) >= MIN_REVIEWS_FOR_ANALYSIS:
                error_rate = sum(1 for r in pattern_reviews if not r.was_correct) / len(pattern_reviews)
                if error_rate < 0.20:
                    pattern.is_active = False
                    resolved.append(pattern)

    db.commit()
    return resolved


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _upsert_pattern(
    user_id: int,
    pattern_type: PatternType,
    description: str,
    affected_cards: List[int],
    db: Session,
) -> ErrorPattern:
    """Cria ou atualiza um ErrorPattern."""
    existing = (
        db.query(ErrorPattern)
        .filter(ErrorPattern.user_id == user_id)
        .filter(ErrorPattern.pattern_type == pattern_type)
        .filter(ErrorPattern.is_active == True)
        .first()
    )

    if existing:
        existing.count += 1
        existing.severity = min(MAX_SEVERITY, existing.severity + SEVERITY_INCREMENT)
        existing.last_seen_at = datetime.utcnow()
        existing.description = description
        # Merge affected cards sem duplicar
        current = set(existing.items_affected or [])
        existing.items_affected = list(current | set(affected_cards))
        db.flush()
        return existing
    else:
        pattern = ErrorPattern(
            user_id=user_id,
            pattern_type=pattern_type,
            description=description,
            count=1,
            severity=SEVERITY_INCREMENT,
            items_affected=affected_cards,
            is_active=True,
        )
        db.add(pattern)
        db.flush()
        return pattern


def _apply_srs_penalty_to_cards(card_ids: List[int], penalty: float, db: Session):
    """
    Aplica penalidade adaptativa no SRSState dos cards afetados.
    Reduz o intervalo na próxima revisão.
    """
    for card_id in card_ids:
        srs = db.query(SRSState).filter(SRSState.card_id == card_id).first()
        if srs:
            srs.adaptation_penalty = min(1.0, penalty)
    db.flush()


def _get_card_type(card_id: int, db: Session) -> Optional[CardType]:
    """Helper para obter tipo do card sem carregar o objeto completo."""
    card = db.query(Card.card_type).filter(Card.id == card_id).first()
    return card.card_type if card else None


def _get_exercise_type(exercise_id: int, db: Session) -> Optional[ExerciseType]:
    """Helper para obter tipo do exercício."""
    from app.domain.models import Exercise
    ex = db.query(Exercise.exercise_type).filter(Exercise.id == exercise_id).first()
    return ex.exercise_type if ex else None


def get_adaptation_summary(user_id: int, db: Session) -> Dict:
    """
    Retorna resumo das adaptações ativas para o usuário.
    Usado na tela de Progresso.
    """
    active_patterns = (
        db.query(ErrorPattern)
        .filter(ErrorPattern.user_id == user_id)
        .filter(ErrorPattern.is_active == True)
        .all()
    )

    recommended_exercise = get_recommended_exercise_type(user_id, db)
    daily_limit = get_daily_new_cards_limit(user_id, db)

    return {
        "active_patterns": [
            {
                "type": p.pattern_type,
                "description": p.description,
                "severity": p.severity,
                "count": p.count,
                "last_seen": p.last_seen_at.isoformat() if p.last_seen_at else None,
            }
            for p in active_patterns
        ],
        "recommended_exercise_type": recommended_exercise,
        "daily_new_cards_limit": daily_limit,
        "has_active_weaknesses": len(active_patterns) > 0,
    }
