"""
Domain models — Singular
Entidades centrais do sistema de aprendizado adaptativo.
Cada entidade reflete diretamente a visão do bigbang.md:
  User → Lesson → Transcript → ExtractedItem → Card → Exercise
                                                    ↓
                                               SRSState (revisão espaçada)
                                               ReviewLog → ErrorPattern (adaptação)
"""

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Enum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


# ─── Enums ────────────────────────────────────────────────────────────────────

class LessonStatus(str, PyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class ItemType(str, PyEnum):
    VOCAB = "vocab"
    PHRASE = "phrase"
    GRAMMAR = "grammar"


class CardType(str, PyEnum):
    VOCAB = "vocab"
    PHRASE = "phrase"
    GRAMMAR = "grammar"


class SRSCardState(str, PyEnum):
    NEW = "new"
    LEARNING = "learning"
    REVIEW = "review"
    RELEARNING = "relearning"


class ExerciseType(str, PyEnum):
    TRANSLATION = "translation"       # "Como se diz X?" → resposta livre
    FILL_BLANK = "fill_blank"         # Frase com ___
    BUILD_SENTENCE = "build_sentence" # Palavras embaralhadas para organizar


class PatternType(str, PyEnum):
    VOCAB_WEAKNESS = "vocab_weakness"         # Erra muito vocabulário
    GRAMMAR_CONFUSION = "grammar_confusion"   # Erra estruturas gramaticais
    STRUCTURE_CONFUSION = "structure_confusion"  # Erra ordem de frase


# ─── User ─────────────────────────────────────────────────────────────────────

class User(Base):
    """
    Usuário do sistema. Por ora single-user, mas estruturado para multi-user.
    native_language: idioma nativo do aluno (ex: "pt-BR")
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    native_language = Column(String(10), default="pt-BR")
    created_at = Column(DateTime, server_default=func.now())

    lessons = relationship("Lesson", back_populates="user")
    srs_states = relationship("SRSState", back_populates="user")
    review_logs = relationship("ReviewLog", back_populates="user")
    error_patterns = relationship("ErrorPattern", back_populates="user")


# ─── Lesson ───────────────────────────────────────────────────────────────────

class Lesson(Base):
    """
    Uma aula importada. Ponto de entrada do pipeline.
    A aula é a matéria-prima — não o produto final (bigbang.md §11).
    """
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    url = Column(String(500), nullable=True)
    title = Column(String(300), nullable=True)
    language = Column(String(10), nullable=True)  # ex: "ja" para japonês
    level = Column(String(20), nullable=True)      # ex: "N5", "beginner"
    status = Column(Enum(LessonStatus), default=LessonStatus.PENDING)
    error_message = Column(Text, nullable=True)    # detalhes do erro se status=error
    created_at = Column(DateTime, server_default=func.now())
    processed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="lessons")
    transcript = relationship("Transcript", back_populates="lesson", uselist=False)
    extracted_items = relationship("ExtractedItem", back_populates="lesson")
    cards = relationship("Card", back_populates="lesson")


# ─── Transcript ───────────────────────────────────────────────────────────────

class Transcript(Base):
    """
    Transcrição bruta da aula. Armazenada separadamente para reprocessamento.
    """
    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), unique=True, nullable=False)
    raw_text = Column(Text, nullable=False)
    language = Column(String(10), nullable=True)
    source = Column(String(50), default="youtube_transcript")  # ou "whisper", "manual"
    created_at = Column(DateTime, server_default=func.now())

    lesson = relationship("Lesson", back_populates="transcript")


# ─── ExtractedItem ────────────────────────────────────────────────────────────

class ExtractedItem(Base):
    """
    Item de conhecimento extraído pela IA da transcrição.
    Pode ser vocabulário, frase completa ou padrão gramatical.
    A IA não extrai tudo — seleciona o que realmente importa (bigbang.md §2).
    """
    __tablename__ = "extracted_items"

    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=False)
    item_type = Column(Enum(ItemType), nullable=False)

    # Conteúdo principal
    content = Column(String(500), nullable=False)       # ex: "食べる"
    reading = Column(String(500), nullable=True)        # ex: "たべる" (romaji/furigana)
    translation = Column(String(500), nullable=True)    # ex: "comer"
    context_sentence = Column(Text, nullable=True)      # frase da aula onde apareceu
    explanation = Column(Text, nullable=True)           # explicação gramatical (para grammar)

    # Metadados de relevância (bigbang.md §2 — classifica por frequência, complexidade)
    complexity = Column(Float, default=0.5)  # 0.0 = simples, 1.0 = complexo
    frequency = Column(Float, default=0.5)  # frequência relativa no texto
    usefulness = Column(Float, default=0.5) # utilidade prática estimada pela IA

    created_at = Column(DateTime, server_default=func.now())

    lesson = relationship("Lesson", back_populates="extracted_items")
    cards = relationship("Card", back_populates="extracted_item")


# ─── Card ─────────────────────────────────────────────────────────────────────

class Card(Base):
    """
    Card de revisão gerado a partir de um ExtractedItem.
    Representa a unidade atômica de conhecimento para revisão espaçada.
    """
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, index=True)
    extracted_item_id = Column(Integer, ForeignKey("extracted_items.id"), nullable=False)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=False)
    card_type = Column(Enum(CardType), nullable=False)

    front = Column(Text, nullable=False)  # pergunta/estímulo
    back = Column(Text, nullable=False)   # resposta/informação completa
    hint = Column(Text, nullable=True)    # dica opcional

    created_at = Column(DateTime, server_default=func.now())

    extracted_item = relationship("ExtractedItem", back_populates="cards")
    lesson = relationship("Lesson", back_populates="cards")
    srs_state = relationship("SRSState", back_populates="card", uselist=False)
    exercises = relationship("Exercise", back_populates="card")
    review_logs = relationship("ReviewLog", back_populates="card")


# ─── SRSState ─────────────────────────────────────────────────────────────────

class SRSState(Base):
    """
    Estado do algoritmo de repetição espaçada para um card específico.
    Baseado no SM-2 com adaptações: considera ErrorPattern e consistência do aluno.

    Estados:
      new        → nunca visto
      learning   → em processo inicial (intervalos curtos: 1min, 10min)
      review     → já consolidado (intervalos em dias)
      relearning → esquecido, voltou ao aprendizado
    """
    __tablename__ = "srs_states"

    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(Integer, ForeignKey("cards.id"), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Campos SM-2
    interval = Column(Integer, default=0)          # intervalo em dias (0 = intraday)
    ease_factor = Column(Float, default=2.5)       # fator de facilidade (min 1.3)
    repetitions = Column(Integer, default=0)       # quantas vezes respondeu corretamente
    lapses = Column(Integer, default=0)            # quantas vezes esqueceu após review

    # Estado e agendamento
    state = Column(Enum(SRSCardState), default=SRSCardState.NEW)
    due_date = Column(DateTime, nullable=True)     # quando este card deve ser revisado
    last_reviewed_at = Column(DateTime, nullable=True)

    # Campos adicionais além do SM-2 padrão
    # stability: estimativa de quanto tempo a memória aguenta (em dias)
    stability = Column(Float, default=1.0)
    # adaptation_penalty: penalidade aplicada pelo motor adaptativo (0.0 = sem penalidade)
    adaptation_penalty = Column(Float, default=0.0)

    card = relationship("Card", back_populates="srs_state")
    user = relationship("User", back_populates="srs_states")


# ─── Exercise ─────────────────────────────────────────────────────────────────

class Exercise(Base):
    """
    Exercício ativo gerado a partir de um Card.
    Três tipos: tradução, completar lacuna, construir frase.
    Os exercícios alimentam o motor de adaptação via respostas do aluno.
    """
    __tablename__ = "exercises"

    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(Integer, ForeignKey("cards.id"), nullable=False)
    exercise_type = Column(Enum(ExerciseType), nullable=False)

    prompt = Column(Text, nullable=False)           # enunciado do exercício
    expected_answer = Column(Text, nullable=False)  # resposta correta
    options = Column(JSON, nullable=True)           # para múltipla escolha futura
    context = Column(Text, nullable=True)           # contexto adicional

    created_at = Column(DateTime, server_default=func.now())

    card = relationship("Card", back_populates="exercises")
    submissions = relationship("ExerciseSubmission", back_populates="exercise")


# ─── ExerciseSubmission ───────────────────────────────────────────────────────

class ExerciseSubmission(Base):
    """
    Resposta do usuário a um exercício. Fonte de dados para adaptação.
    """
    __tablename__ = "exercise_submissions"

    id = Column(Integer, primary_key=True, index=True)
    exercise_id = Column(Integer, ForeignKey("exercises.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    user_answer = Column(Text, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    score = Column(Float, default=0.0)             # 0.0–1.0, para respostas parcialmente corretas
    response_time_ms = Column(Integer, nullable=True)
    error_category = Column(String(50), nullable=True)  # categoria do erro detectado

    submitted_at = Column(DateTime, server_default=func.now())

    exercise = relationship("Exercise", back_populates="submissions")


# ─── ReviewLog ────────────────────────────────────────────────────────────────

class ReviewLog(Base):
    """
    Registro histórico de cada revisão de card.
    quality 0-5 seguindo convenção SM-2:
      0 = esquecimento completo
      1 = errado, resposta parecia familiar
      2 = errado, mas resposta correta era fácil ao ver
      3 = correto com dificuldade significativa
      4 = correto após hesitação
      5 = correto e fácil
    """
    __tablename__ = "review_logs"

    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(Integer, ForeignKey("cards.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    quality = Column(Integer, nullable=False)       # 0-5
    response_time_ms = Column(Integer, nullable=True)
    was_correct = Column(Boolean, nullable=False)   # quality >= 3
    srs_state_before = Column(JSON, nullable=True)  # snapshot do estado antes
    srs_state_after = Column(JSON, nullable=True)   # snapshot do estado depois

    reviewed_at = Column(DateTime, server_default=func.now())

    card = relationship("Card", back_populates="review_logs")
    user = relationship("User", back_populates="review_logs")


# ─── ErrorPattern ─────────────────────────────────────────────────────────────

class ErrorPattern(Base):
    """
    Padrão de erro detectado pelo motor adaptativo.
    Representa fraquezas específicas do aluno que devem ser reforçadas.

    O sistema usa esses padrões para:
    - Reduzir intervalo SRS de cards afetados
    - Priorizar tipo de exercício que combate a fraqueza
    - Ajustar quantidade de novos cards por dia
    """
    __tablename__ = "error_patterns"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    pattern_type = Column(Enum(PatternType), nullable=False)

    description = Column(Text, nullable=True)         # descrição legível do padrão
    count = Column(Integer, default=1)                # quantas vezes detectado
    severity = Column(Float, default=0.5)             # 0.0 = leve, 1.0 = crítico
    items_affected = Column(JSON, default=list)       # lista de card_ids afetados
    is_active = Column(Boolean, default=True)         # false = padrão resolvido

    first_detected_at = Column(DateTime, server_default=func.now())
    last_seen_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="error_patterns")
