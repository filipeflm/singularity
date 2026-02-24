"""
Seed de Dados — Singular
Cria dados de teste para permitir uso imediato sem precisar importar aula real.

O que este seed cria:
  1. Usuário padrão (id=1)
  2. Uma aula mock de japonês N5 com transcript
  3. 17 ExtractedItems (10 vocab + 4 phrases + 3 grammar)
  4. Cards para cada item
  5. Exercícios (3 por card de vocab/phrase, 1 por grammar)
  6. SRSState inicializado para cada card
  7. Simulação de 7 dias de revisões com padrão de erros realista

Após rodar este seed, a UI já tem dados para explorar todas as funcionalidades.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Adiciona o diretório backend ao path
sys.path.insert(0, str(Path(__file__).parent))

# Carrega variáveis de ambiente se .env existir
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app.database import SessionLocal, create_tables
from app.domain.models import (
    Card,
    CardType,
    Exercise,
    ExerciseSubmission,
    ExerciseType,
    ExtractedItem,
    ItemType,
    Lesson,
    LessonStatus,
    ReviewLog,
    SRSCardState,
    SRSState,
    Transcript,
    User,
)
from app.services.extraction import get_mock_extraction
from app.services.pipeline import run_import_pipeline
from app.services.transcription import get_mock_transcript


def seed():
    """Executa o seed completo."""
    print("🌱 Iniciando seed do Singular...")

    create_tables()
    db = SessionLocal()

    try:
        # Limpa dados existentes para seed limpo
        _clean_db(db)
        print("  ✓ Banco limpo")

        # 1. Usuário
        user = _create_user(db)
        print(f"  ✓ Usuário criado: {user.name} (id={user.id})")

        # 2. Aula mock via pipeline completo (use_mock=True)
        lesson = _create_lesson(db, user.id)
        print(f"  ✓ Aula criada: {lesson.title} (id={lesson.id})")

        # Executa pipeline com dados mock
        print("  ⏳ Executando pipeline mock...")
        result = run_import_pipeline(
            lesson_id=lesson.id,
            user_id=user.id,
            db=db,
            use_mock=True,
        )

        if result.success:
            print(f"  ✓ Pipeline concluído: {result.cards_created} cards, {result.exercises_created} exercícios")
        else:
            print(f"  ✗ Pipeline falhou: {result.error}")
            return

        # 3. Simula histórico de revisões (7 dias)
        print("  ⏳ Simulando histórico de revisões...")
        _simulate_review_history(db, user.id)
        print("  ✓ Histórico de revisões simulado")

        print("\n✅ Seed concluído com sucesso!")
        _print_summary(db, user.id)

    except Exception as e:
        print(f"\n✗ Erro no seed: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


def _clean_db(db):
    """Remove todos os dados existentes para seed limpo."""
    from sqlalchemy import text
    tables = [
        "exercise_submissions", "review_logs", "srs_states",
        "exercises", "cards", "extracted_items", "transcripts",
        "error_patterns", "lessons", "users"
    ]
    for table in tables:
        try:
            db.execute(text(f"DELETE FROM {table}"))
        except Exception:
            pass
    db.commit()


def _create_user(db) -> User:
    """Cria o usuário padrão."""
    user = User(
        id=1,
        name="Estudante",
        email="estudante@singular.app",
        native_language="pt-BR",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_lesson(db, user_id: int) -> Lesson:
    """Cria a aula mock de japonês."""
    lesson = Lesson(
        user_id=user_id,
        url="https://www.youtube.com/watch?v=mock_japanese_lesson",
        title="日本語入門 — Aula 1: Saudações e Apresentações",
        language="ja",
        level="N5",
        status=LessonStatus.PENDING,
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return lesson


def _simulate_review_history(db, user_id: int):
    """
    Simula 7 dias de histórico de revisões.
    Cria um padrão realista:
    - Dias 1-3: muitos acertos (aluno está empolgado)
    - Dia 4: muitos erros de vocabulário (fadiga)
    - Dias 5-7: recuperação gradual

    Isso deve ativar o padrão VOCAB_WEAKNESS no motor adaptativo.
    """
    import random
    random.seed(42)  # reproduzível

    cards = db.query(Card).filter(Card.lesson_id == 1).all()
    if not cards:
        return

    now = datetime.utcnow()

    # Simula revisões nos últimos 7 dias
    for day_offset in range(7, 0, -1):
        review_date = now - timedelta(days=day_offset)

        # Define taxa de acerto por dia
        if day_offset >= 5:
            correct_rate = 0.85  # dias 5-7 atrás: bom desempenho
        elif day_offset == 4:
            correct_rate = 0.40  # dia 4 atrás: muitos erros de vocab
        else:
            correct_rate = 0.70  # dias recentes: recuperando

        # Revisa subset de cards por dia (não todos)
        day_cards = random.sample(cards, min(8, len(cards)))

        for card in day_cards:
            # Determina qualidade da resposta
            is_correct = random.random() < correct_rate

            # Cards de vocab têm mais erros no dia 4
            if day_offset == 4 and card.card_type == CardType.VOCAB:
                is_correct = random.random() < 0.30  # muito erro

            quality = random.choice([4, 5]) if is_correct else random.choice([1, 2])

            srs = db.query(SRSState).filter(
                SRSState.card_id == card.id,
                SRSState.user_id == user_id,
            ).first()

            if not srs:
                continue

            state_before = {
                "state": srs.state.value,
                "interval": srs.interval,
                "ease_factor": srs.ease_factor,
            }

            # Cria ReviewLog
            log = ReviewLog(
                card_id=card.id,
                user_id=user_id,
                quality=quality,
                response_time_ms=random.randint(800, 4000),
                was_correct=is_correct,
                srs_state_before=state_before,
                srs_state_after=state_before,  # simplificado para o seed
                reviewed_at=review_date,
            )
            db.add(log)

            # Atualiza SRS de forma simplificada
            if is_correct:
                srs.repetitions += 1
                srs.state = SRSCardState.REVIEW if srs.repetitions >= 2 else SRSCardState.LEARNING
                srs.interval = min(srs.interval + 1, 7)
                srs.last_reviewed_at = review_date
                srs.due_date = review_date + timedelta(days=srs.interval)
            else:
                srs.lapses += 1
                srs.ease_factor = max(1.3, srs.ease_factor - 0.15)
                srs.state = SRSCardState.RELEARNING if srs.state == SRSCardState.REVIEW else SRSCardState.LEARNING
                srs.interval = max(1, srs.interval // 2)
                srs.last_reviewed_at = review_date
                srs.due_date = review_date + timedelta(hours=4)

    # Ajusta alguns cards para estarem devidos agora (para UI ter algo para revisar)
    due_cards = random.sample(cards, min(5, len(cards)))
    for card in due_cards:
        srs = db.query(SRSState).filter(
            SRSState.card_id == card.id,
            SRSState.user_id == user_id,
        ).first()
        if srs:
            srs.due_date = now - timedelta(hours=1)  # vencido há 1h

    db.commit()

    # Simula também submissões de exercícios
    _simulate_exercise_submissions(db, user_id, now)


def _simulate_exercise_submissions(db, user_id: int, now: datetime):
    """Simula submissões de exercícios para alimentar o motor adaptativo."""
    import random
    random.seed(123)

    exercises = db.query(Exercise).limit(20).all()
    if not exercises:
        return

    for i, exercise in enumerate(exercises):
        days_ago = random.randint(1, 7)
        is_correct = random.random() > 0.45  # ~55% de acerto

        # Mais erros em build_sentence
        if exercise.exercise_type == ExerciseType.BUILD_SENTENCE:
            is_correct = random.random() > 0.55  # ~45% de acerto

        submission = ExerciseSubmission(
            exercise_id=exercise.id,
            user_id=user_id,
            user_answer="resposta_simulada" if not is_correct else exercise.expected_answer,
            is_correct=is_correct,
            score=1.0 if is_correct else random.uniform(0.1, 0.5),
            response_time_ms=random.randint(1000, 6000),
            error_category=None if is_correct else "vocabulary",
            submitted_at=now - timedelta(days=days_ago),
        )
        db.add(submission)

    db.commit()


def _print_summary(db, user_id: int):
    """Imprime resumo do que foi criado."""
    lessons = db.query(Lesson).filter(Lesson.user_id == user_id).count()
    cards = db.query(Card).count()
    exercises = db.query(Exercise).count()
    srs_states = db.query(SRSState).filter(SRSState.user_id == user_id).count()
    review_logs = db.query(ReviewLog).filter(ReviewLog.user_id == user_id).count()

    # Cards por estado
    states = {}
    for state in SRSCardState:
        count = db.query(SRSState).filter(
            SRSState.user_id == user_id,
            SRSState.state == state,
        ).count()
        states[state.value] = count

    # Cards devidos agora
    due_now = db.query(SRSState).filter(
        SRSState.user_id == user_id,
        SRSState.due_date <= datetime.utcnow(),
    ).count()

    print("\n📊 Resumo do seed:")
    print(f"   Aulas:    {lessons}")
    print(f"   Cards:    {cards}")
    print(f"   Exercícios: {exercises}")
    print(f"   Revisões simuladas: {review_logs}")
    print(f"\n   Cards por estado:")
    for state, count in states.items():
        print(f"     {state}: {count}")
    print(f"\n   Cards devidos agora: {due_now}")
    print("\n🚀 Pronto para usar! Rode:")
    print("   Backend: uvicorn app.main:app --reload")
    print("   Frontend: cd ../frontend && npm run dev")


if __name__ == "__main__":
    seed()
