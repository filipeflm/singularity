"""
Pipeline de Processamento — Singular
Orquestra o fluxo completo: URL → Transcript → Extração → Cards → Exercícios → SRS

Cada etapa é separada e testável individualmente.
O pipeline atualiza o status da aula em cada etapa para feedback em tempo real.

Fluxo (bigbang.md §3):
  ImportLesson
    ├── Step 1: Transcrição
    ├── Step 2: Extração inteligente (Claude)
    ├── Step 3: Geração de Cards
    ├── Step 4: Geração de Exercícios
    └── Step 5: Inicialização SRS
"""

import os
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.domain.models import (
    Card,
    CardType,
    Exercise,
    ExtractedItem,
    ItemType,
    Lesson,
    LessonStatus,
    SRSCardState,
    SRSState,
    Transcript,
)
from app.services.exercise import (
    GeneratedExercise,
    generate_exercises_for_card,
)
from app.services.extraction import (
    ExtractionResult,
    extract_from_transcript,
    get_mock_extraction,
)
from app.services.transcription import (
    TranscriptResult,
    get_mock_transcript,
    get_transcript,
)


# ─── Resultado do pipeline ────────────────────────────────────────────────────

class PipelineResult:
    def __init__(self):
        self.success = False
        self.lesson_id: Optional[int] = None
        self.cards_created: int = 0
        self.exercises_created: int = 0
        self.error: Optional[str] = None
        self.steps_completed: list = []

    def __repr__(self):
        return (
            f"PipelineResult(success={self.success}, "
            f"cards={self.cards_created}, exercises={self.exercises_created})"
        )


# ─── Pipeline principal ────────────────────────────────────────────────────────

def run_import_pipeline(
    lesson_id: int,
    user_id: int,
    db: Session,
    use_mock: bool = False,
) -> PipelineResult:
    """
    Executa o pipeline completo para uma aula.

    Args:
        lesson_id: ID da aula já criada no banco
        user_id: ID do usuário
        db: Sessão do banco
        use_mock: Se True, usa dados mock (sem chamar APIs externas)

    Returns:
        PipelineResult com resultado de cada etapa
    """
    result = PipelineResult()
    result.lesson_id = lesson_id

    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        result.error = f"Aula {lesson_id} não encontrada."
        return result

    # Marca como processando
    lesson.status = LessonStatus.PROCESSING
    db.commit()

    try:
        # ── Step 1: Transcrição ────────────────────────────────────────────────
        transcript_result = _step_transcription(lesson, db, use_mock)
        if not transcript_result.success:
            _mark_error(lesson, transcript_result.error, db)
            result.error = transcript_result.error
            return result
        result.steps_completed.append("transcription")

        # ── Step 2: Extração ───────────────────────────────────────────────────
        extraction_result = _step_extraction(lesson, transcript_result.text, db, use_mock)
        if not extraction_result.success:
            _mark_error(lesson, extraction_result.error, db)
            result.error = extraction_result.error
            return result
        result.steps_completed.append("extraction")

        # Atualiza metadados da aula com dados detectados
        if extraction_result.detected_language:
            lesson.language = extraction_result.detected_language
        if extraction_result.detected_level:
            lesson.level = extraction_result.detected_level
        db.flush()

        # ── Step 3: Geração de Cards ───────────────────────────────────────────
        cards = _step_generate_cards(lesson, extraction_result, db)
        result.cards_created = len(cards)
        result.steps_completed.append("cards")

        # ── Step 4: Geração de Exercícios ──────────────────────────────────────
        exercises_count = _step_generate_exercises(cards, lesson, db, use_mock)
        result.exercises_created = exercises_count
        result.steps_completed.append("exercises")

        # ── Step 5: Inicialização SRS ──────────────────────────────────────────
        _step_init_srs(cards, user_id, db)
        result.steps_completed.append("srs_init")

        # Finaliza
        lesson.status = LessonStatus.READY
        lesson.processed_at = datetime.utcnow()
        db.commit()

        result.success = True
        return result

    except Exception as e:
        db.rollback()
        _mark_error(lesson, f"Erro inesperado: {str(e)}", db)
        result.error = str(e)
        return result


# ─── Steps individuais ────────────────────────────────────────────────────────

def _step_transcription(
    lesson: Lesson, db: Session, use_mock: bool
) -> TranscriptResult:
    """
    Step 1: Obtém o transcript do vídeo.
    Salva no banco como objeto Transcript.
    """
    if use_mock or not lesson.url:
        transcript_result = get_mock_transcript()
    else:
        transcript_result = get_transcript(
            lesson.url,
            preferred_language=lesson.language or "ja",
        )

    if transcript_result.success:
        # Salva no banco
        transcript = Transcript(
            lesson_id=lesson.id,
            raw_text=transcript_result.text,
            language=transcript_result.language,
            source="mock" if use_mock else "youtube_transcript",
        )
        db.add(transcript)

        # Atualiza título se disponível
        if transcript_result.title and not lesson.title:
            lesson.title = transcript_result.title

        db.flush()

    return transcript_result


def _step_extraction(
    lesson: Lesson,
    transcript_text: str,
    db: Session,
    use_mock: bool,
) -> ExtractionResult:
    """
    Step 2: Extrai vocabulário, frases e gramática via Claude.
    Salva ExtractedItems no banco.
    """
    if use_mock:
        extraction_result = get_mock_extraction()
    else:
        extraction_result = extract_from_transcript(
            transcript_text=transcript_text,
            target_language=lesson.language or "ja",
            native_language="pt-BR",
        )

    if extraction_result.success:
        # Salva vocabulário
        for vocab in extraction_result.vocabulary:
            item = ExtractedItem(
                lesson_id=lesson.id,
                item_type=ItemType.VOCAB,
                content=vocab.content,
                reading=vocab.reading,
                translation=vocab.translation,
                context_sentence=vocab.context_sentence,
                complexity=vocab.complexity,
                frequency=vocab.frequency,
                usefulness=vocab.usefulness,
            )
            db.add(item)

        # Salva frases
        for phrase in extraction_result.phrases:
            item = ExtractedItem(
                lesson_id=lesson.id,
                item_type=ItemType.PHRASE,
                content=phrase.content,
                reading=phrase.reading,
                translation=phrase.translation,
                context_sentence=phrase.context_sentence,
                complexity=phrase.complexity,
                usefulness=phrase.usefulness,
            )
            db.add(item)

        # Salva gramática
        for grammar in extraction_result.grammar:
            item = ExtractedItem(
                lesson_id=lesson.id,
                item_type=ItemType.GRAMMAR,
                content=grammar.content,
                explanation=grammar.explanation,
                context_sentence=grammar.context_sentence,
                complexity=grammar.complexity,
                usefulness=grammar.usefulness,
            )
            db.add(item)

        db.flush()

    return extraction_result


def _step_generate_cards(
    lesson: Lesson,
    extraction: ExtractionResult,
    db: Session,
) -> list:
    """
    Step 3: Gera Cards a partir dos ExtractedItems.
    Para cada item, cria um Card com front/back significativos.
    """
    cards = []
    extracted_items = db.query(ExtractedItem).filter(
        ExtractedItem.lesson_id == lesson.id
    ).all()

    for item in extracted_items:
        card = _create_card_from_item(item, lesson.id, db)
        if card:
            cards.append(card)

    db.flush()
    return cards


def _create_card_from_item(item: ExtractedItem, lesson_id: int, db: Session) -> Optional[Card]:
    """Cria um Card a partir de um ExtractedItem."""
    if item.item_type == ItemType.VOCAB:
        # Front: palavra + leitura | Back: tradução + contexto
        front = item.content
        if item.reading and item.reading != item.content:
            front += f"\n({item.reading})"

        back = item.translation or ""
        if item.context_sentence:
            back += f"\n\n例文: {item.context_sentence}"

        card = Card(
            extracted_item_id=item.id,
            lesson_id=lesson_id,
            card_type=CardType.VOCAB,
            front=front,
            back=back,
            hint=item.reading,
        )

    elif item.item_type == ItemType.PHRASE:
        front = item.content
        back = item.translation or ""
        if item.context_sentence:
            back += f"\n\n使い方: {item.context_sentence}"

        card = Card(
            extracted_item_id=item.id,
            lesson_id=lesson_id,
            card_type=CardType.PHRASE,
            front=front,
            back=back,
        )

    elif item.item_type == ItemType.GRAMMAR:
        front = f"📝 {item.content}"
        back = item.explanation or ""
        if item.context_sentence:
            back += f"\n\n例: {item.context_sentence}"

        card = Card(
            extracted_item_id=item.id,
            lesson_id=lesson_id,
            card_type=CardType.GRAMMAR,
            front=front,
            back=back,
            hint=item.context_sentence,
        )
    else:
        return None

    db.add(card)
    return card


def _step_generate_exercises(
    cards: list,
    lesson: Lesson,
    db: Session,
    use_mock: bool,
) -> int:
    """
    Step 4: Gera exercícios para cada card.
    Para MVP, gera para vocab e phrase (grammar tem exercício implícito no card).
    """
    total = 0

    for card in cards:
        # Pula cards de gramática para economizar tokens (o card já é o exercício)
        if card.card_type == CardType.GRAMMAR and not use_mock:
            # Gera apenas 1 exercício de fill_blank para gramática
            item = db.query(ExtractedItem).filter(
                ExtractedItem.id == card.extracted_item_id
            ).first()
            if item:
                _create_single_exercise_for_grammar(card, item, db)
                total += 1
            continue

        item = db.query(ExtractedItem).filter(
            ExtractedItem.id == card.extracted_item_id
        ).first()
        if not item:
            continue

        result = generate_exercises_for_card(
            card_content=item.content,
            card_back=card.back,
            card_type=card.card_type.value,
            context_sentence=item.context_sentence or "",
            target_language=lesson.language or "ja",
            native_language="pt-BR",
        )

        if result.success:
            for gen_ex in result.exercises:
                exercise = Exercise(
                    card_id=card.id,
                    exercise_type=gen_ex.exercise_type,
                    prompt=gen_ex.prompt,
                    expected_answer=gen_ex.expected_answer,
                    context=gen_ex.context,
                    options=gen_ex.options,
                )
                db.add(exercise)
                total += 1

    db.flush()
    return total


def _create_single_exercise_for_grammar(card: Card, item: ExtractedItem, db: Session):
    """Cria um exercício de fill_blank para card de gramática."""
    from app.domain.models import ExerciseType

    if item.context_sentence and item.content:
        # Cria fill_blank com a frase de exemplo
        exercise = Exercise(
            card_id=card.id,
            exercise_type=ExerciseType.FILL_BLANK,
            prompt=f"Complete usando o padrão '{item.content}':\n{item.context_sentence}",
            expected_answer=item.context_sentence,
            context=item.explanation,
        )
        db.add(exercise)


def _step_init_srs(cards: list, user_id: int, db: Session):
    """
    Step 5: Inicializa o SRSState para cada card.
    Todos começam como NEW com due_date = agora (disponível imediatamente).
    """
    for card in cards:
        srs = SRSState(
            card_id=card.id,
            user_id=user_id,
            interval=0,
            ease_factor=2.5,
            repetitions=0,
            lapses=0,
            state=SRSCardState.NEW,
            due_date=datetime.utcnow(),  # disponível imediatamente
            stability=1.0,
            adaptation_penalty=0.0,
        )
        db.add(srs)
    db.flush()


def _mark_error(lesson: Lesson, error_message: str, db: Session):
    """Marca aula com status de erro."""
    lesson.status = LessonStatus.ERROR
    lesson.error_message = error_message
    try:
        db.commit()
    except Exception:
        db.rollback()
