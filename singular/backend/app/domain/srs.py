"""
Motor de Repetição Espaçada — Singular
Algoritmo SM-2 adaptado com melhorias:

  1. Estados explícitos: new → learning → review → relearning
  2. Penalidade de adaptação: cards com ErrorPattern ativo têm intervalo reduzido
  3. Fator de consistência: alunos inconsistentes têm intervalos mais conservadores
  4. Estabilidade: estimativa de durabilidade da memória

Referência SM-2 original: https://www.supermemo.com/en/archives1990-2015/english/ol/sm2
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from app.domain.models import SRSCardState


# ─── Constantes ───────────────────────────────────────────────────────────────

EASE_FACTOR_MIN = 1.3       # fator de facilidade mínimo (SM-2 padrão)
EASE_FACTOR_DEFAULT = 2.5   # fator inicial
EASE_FACTOR_MAX = 3.5       # teto para evitar intervalos absurdos

# Intervalos de aprendizado intraday (em minutos)
LEARNING_STEPS_MINUTES = [1, 10]  # novo card: revisar após 1min, depois 10min

# Intervalo inicial após sair do estágio de aprendizado
GRADUATING_INTERVAL_DAYS = 1

# Intervalo para cards que voltam de relearning
RELEARNING_INTERVAL_DAYS = 1

# Threshold para detectar lapso (quality < LAPSE_THRESHOLD = errou)
LAPSE_THRESHOLD = 3

# Penalidade de lapso no ease_factor (SM-2: -0.20 por lapso)
LAPSE_EASE_PENALTY = 0.20

# Redução de intervalo por penalidade adaptativa
ADAPTATION_PENALTY_MULTIPLIER = 0.70  # 30% de redução


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class ReviewResult:
    """Resultado de uma revisão — novo estado calculado pelo algoritmo."""
    new_state: SRSCardState
    new_interval: int           # em dias
    new_ease_factor: float
    new_repetitions: int
    new_lapses: int
    new_stability: float
    new_due_date: datetime
    was_correct: bool


# ─── Funções principais ────────────────────────────────────────────────────────

def calculate_next_review(
    quality: int,
    current_state: SRSCardState,
    interval: int,
    ease_factor: float,
    repetitions: int,
    lapses: int,
    stability: float,
    adaptation_penalty: float = 0.0,
    learning_step_index: int = 0,
    now: Optional[datetime] = None,
) -> ReviewResult:
    """
    Calcula o próximo estado SRS após uma revisão.

    Args:
        quality: Qualidade da resposta, 0-5 (convenção SM-2)
                 0-2 = errado, 3-5 = correto (3=difícil, 4=bom, 5=fácil)
        current_state: Estado atual do card
        interval: Intervalo atual em dias
        ease_factor: Fator de facilidade atual
        repetitions: Número de repetições corretas consecutivas
        lapses: Número de lapsos totais
        stability: Estimativa de estabilidade da memória em dias
        adaptation_penalty: Penalidade do motor adaptativo (0.0 = sem penalidade)
        learning_step_index: Passo atual nos learning steps (apenas para state=learning)
        now: Datetime atual (injetável para testes)

    Returns:
        ReviewResult com todos os campos atualizados
    """
    if now is None:
        now = datetime.utcnow()

    was_correct = quality >= LAPSE_THRESHOLD

    # ── Atualizar ease_factor ──────────────────────────────────────────────────
    # Fórmula SM-2: EF' = EF + (0.1 - (5-q) * (0.08 + (5-q) * 0.02))
    new_ease_factor = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ease_factor = max(EASE_FACTOR_MIN, min(EASE_FACTOR_MAX, new_ease_factor))

    # ── Processar por estado atual ─────────────────────────────────────────────

    if current_state == SRSCardState.NEW:
        # Card novo — nunca visto. Inicia learning.
        return _handle_new_card(
            quality, was_correct, new_ease_factor, lapses, stability,
            adaptation_penalty, now
        )

    elif current_state == SRSCardState.LEARNING:
        return _handle_learning_card(
            quality, was_correct, new_ease_factor, lapses, stability,
            adaptation_penalty, learning_step_index, now
        )

    elif current_state == SRSCardState.REVIEW:
        return _handle_review_card(
            quality, was_correct, interval, new_ease_factor, repetitions,
            lapses, stability, adaptation_penalty, now
        )

    elif current_state == SRSCardState.RELEARNING:
        return _handle_relearning_card(
            quality, was_correct, new_ease_factor, lapses, stability,
            adaptation_penalty, now
        )

    # Fallback (não deve ocorrer)
    return _handle_new_card(
        quality, was_correct, new_ease_factor, lapses, stability,
        adaptation_penalty, now
    )


def _handle_new_card(
    quality, was_correct, ease_factor, lapses, stability,
    adaptation_penalty, now
) -> ReviewResult:
    """Primeiro contato com o card — inicia o processo de aprendizado."""
    if was_correct:
        # Avança para o primeiro learning step
        due_date = now + timedelta(minutes=LEARNING_STEPS_MINUTES[0])
        return ReviewResult(
            new_state=SRSCardState.LEARNING,
            new_interval=0,
            new_ease_factor=ease_factor,
            new_repetitions=0,
            new_lapses=lapses,
            new_stability=stability,
            new_due_date=due_date,
            was_correct=True,
        )
    else:
        # Errou na primeira vez — ver de novo em 1 minuto
        due_date = now + timedelta(minutes=1)
        return ReviewResult(
            new_state=SRSCardState.LEARNING,
            new_interval=0,
            new_ease_factor=max(EASE_FACTOR_MIN, ease_factor - LAPSE_EASE_PENALTY),
            new_repetitions=0,
            new_lapses=lapses,
            new_stability=max(0.5, stability * 0.7),
            new_due_date=due_date,
            was_correct=False,
        )


def _handle_learning_card(
    quality, was_correct, ease_factor, lapses, stability,
    adaptation_penalty, learning_step_index, now
) -> ReviewResult:
    """Card em aprendizado inicial — sobe ou desce nos learning steps."""
    if was_correct:
        next_step = learning_step_index + 1
        if next_step >= len(LEARNING_STEPS_MINUTES):
            # Completou todos os steps — gradua para review
            interval = _apply_adaptation_penalty(
                GRADUATING_INTERVAL_DAYS, adaptation_penalty
            )
            due_date = now + timedelta(days=interval)
            new_stability = max(stability, interval * 0.8)
            return ReviewResult(
                new_state=SRSCardState.REVIEW,
                new_interval=interval,
                new_ease_factor=ease_factor,
                new_repetitions=1,
                new_lapses=lapses,
                new_stability=new_stability,
                new_due_date=due_date,
                was_correct=True,
            )
        else:
            # Avança para o próximo step
            due_date = now + timedelta(minutes=LEARNING_STEPS_MINUTES[next_step])
            return ReviewResult(
                new_state=SRSCardState.LEARNING,
                new_interval=0,
                new_ease_factor=ease_factor,
                new_repetitions=0,
                new_lapses=lapses,
                new_stability=stability,
                new_due_date=due_date,
                was_correct=True,
            )
    else:
        # Errou — volta ao início dos steps
        due_date = now + timedelta(minutes=LEARNING_STEPS_MINUTES[0])
        return ReviewResult(
            new_state=SRSCardState.LEARNING,
            new_interval=0,
            new_ease_factor=max(EASE_FACTOR_MIN, ease_factor - LAPSE_EASE_PENALTY),
            new_repetitions=0,
            new_lapses=lapses,
            new_stability=max(0.5, stability * 0.7),
            new_due_date=due_date,
            was_correct=False,
        )


def _handle_review_card(
    quality, was_correct, interval, ease_factor, repetitions,
    lapses, stability, adaptation_penalty, now
) -> ReviewResult:
    """Card consolidado — calcula próximo intervalo longo."""
    if was_correct:
        # Calcula novo intervalo: SM-2 base
        if repetitions == 1:
            new_interval_raw = 6  # segundo acerto → 6 dias
        else:
            new_interval_raw = round(interval * ease_factor)

        # Aplica penalidade adaptativa se existir
        new_interval = _apply_adaptation_penalty(new_interval_raw, adaptation_penalty)
        new_interval = max(1, new_interval)

        # Estabilidade cresce proporcionalmente ao intervalo
        new_stability = new_interval * 0.9
        due_date = now + timedelta(days=new_interval)

        return ReviewResult(
            new_state=SRSCardState.REVIEW,
            new_interval=new_interval,
            new_ease_factor=ease_factor,
            new_repetitions=repetitions + 1,
            new_lapses=lapses,
            new_stability=new_stability,
            new_due_date=due_date,
            was_correct=True,
        )
    else:
        # Lapso — card volta para relearning
        new_lapses = lapses + 1
        new_ease_factor = max(EASE_FACTOR_MIN, ease_factor - LAPSE_EASE_PENALTY)
        new_interval = RELEARNING_INTERVAL_DAYS
        new_stability = max(0.5, stability * 0.5)
        due_date = now + timedelta(days=new_interval)

        return ReviewResult(
            new_state=SRSCardState.RELEARNING,
            new_interval=new_interval,
            new_ease_factor=new_ease_factor,
            new_repetitions=0,
            new_lapses=new_lapses,
            new_stability=new_stability,
            new_due_date=due_date,
            was_correct=False,
        )


def _handle_relearning_card(
    quality, was_correct, ease_factor, lapses, stability,
    adaptation_penalty, now
) -> ReviewResult:
    """Card em reaprendizado após lapso."""
    if was_correct:
        interval = _apply_adaptation_penalty(
            RELEARNING_INTERVAL_DAYS + 1, adaptation_penalty
        )
        new_stability = max(stability, interval * 0.7)
        due_date = now + timedelta(days=interval)
        return ReviewResult(
            new_state=SRSCardState.REVIEW,
            new_interval=interval,
            new_ease_factor=ease_factor,
            new_repetitions=1,
            new_lapses=lapses,
            new_stability=new_stability,
            new_due_date=due_date,
            was_correct=True,
        )
    else:
        # Ainda não consolidou — mantém relearning com intervalo curto
        due_date = now + timedelta(hours=4)
        return ReviewResult(
            new_state=SRSCardState.RELEARNING,
            new_interval=0,
            new_ease_factor=max(EASE_FACTOR_MIN, ease_factor - LAPSE_EASE_PENALTY),
            new_repetitions=0,
            new_lapses=lapses + 1,
            new_stability=max(0.3, stability * 0.5),
            new_due_date=due_date,
            was_correct=False,
        )


def _apply_adaptation_penalty(interval: int, penalty: float) -> int:
    """
    Aplica penalidade adaptativa ao intervalo.
    penalty=0.0 → sem penalidade
    penalty=1.0 → intervalo reduzido a ADAPTATION_PENALTY_MULTIPLIER (30% menor)
    """
    if penalty <= 0:
        return interval
    multiplier = 1.0 - (penalty * (1.0 - ADAPTATION_PENALTY_MULTIPLIER))
    return max(1, round(interval * multiplier))


def get_card_urgency_score(
    due_date: Optional[datetime],
    state: SRSCardState,
    lapses: int,
    now: Optional[datetime] = None,
) -> float:
    """
    Calcula o score de urgência de um card para ordenação da fila de revisão.
    Score maior = mais urgente.

    Considera:
    - Atraso em relação à due_date
    - Cards em relearning têm prioridade
    - Cards com muitos lapsos têm prioridade
    """
    if now is None:
        now = datetime.utcnow()

    base_score = 0.0

    # Prioridade por estado
    state_priority = {
        SRSCardState.RELEARNING: 100.0,
        SRSCardState.LEARNING: 50.0,
        SRSCardState.REVIEW: 10.0,
        SRSCardState.NEW: 1.0,
    }
    base_score += state_priority.get(state, 0)

    # Atraso em horas
    if due_date:
        delay_hours = (now - due_date).total_seconds() / 3600
        base_score += max(0, delay_hours * 2)

    # Lapsos aumentam prioridade
    base_score += lapses * 5

    return base_score


def calculate_retention_probability(
    days_since_review: float,
    stability: float,
) -> float:
    """
    Estima a probabilidade de retenção usando curva de esquecimento de Ebbinghaus.
    R = e^(-t/S) onde t = tempo desde revisão, S = estabilidade
    """
    import math
    if stability <= 0:
        return 0.0
    return math.exp(-days_since_review / stability)
