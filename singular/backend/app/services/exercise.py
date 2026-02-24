"""
Serviço de Geração de Exercícios — Singular
Gera exercícios ativos para cada card usando Claude ou regras locais.

Três tipos de exercício (bigbang.md §6):
  1. translation   → Tradução ativa: dada uma palavra/frase, o aluno traduz
  2. fill_blank    → Completar lacuna: frase com ___ para preencher
  3. build_sentence → Construir frase: palavras embaralhadas para organizar

Princípio: "O erro não é punição. É dado." (bigbang.md §5)
As respostas são avaliadas e alimentam o motor de adaptação.
"""

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import anthropic

from app.domain.models import Card, ExerciseType, ItemType


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class GeneratedExercise:
    exercise_type: ExerciseType
    prompt: str
    expected_answer: str
    context: Optional[str] = None
    options: Optional[List[str]] = None  # para múltipla escolha futura


@dataclass
class ExerciseGenerationResult:
    success: bool
    exercises: List[GeneratedExercise] = field(default_factory=list)
    error: Optional[str] = None


# ─── Avaliação de resposta ─────────────────────────────────────────────────────

@dataclass
class AnswerEvaluation:
    is_correct: bool
    score: float          # 0.0-1.0
    feedback: str
    error_category: Optional[str] = None  # "spelling", "meaning", "order", etc.


# ─── Prompt de geração ─────────────────────────────────────────────────────────

EXERCISE_SYSTEM_PROMPT = """Você é um gerador de exercícios de idiomas para aprendizado ativo.

Gere exercícios variados e úteis para o item fornecido. Retorne APENAS JSON válido.

TIPOS:
1. translation: "Traduza para [idioma]:" + resposta esperada
2. fill_blank: Frase com ___ onde a resposta pertence. Forneça a frase completa como context.
3. build_sentence: Lista de palavras embaralhadas. O aluno organiza. expected_answer = frase correta.

FORMATO:
{
  "exercises": [
    {
      "type": "translation",
      "prompt": "Como se diz 'comer' em japonês?",
      "expected_answer": "食べる / たべる",
      "context": null
    },
    {
      "type": "fill_blank",
      "prompt": "私は毎日ご飯を___。",
      "expected_answer": "食べます",
      "context": "Preencha com a forma polida do verbo 食べる"
    },
    {
      "type": "build_sentence",
      "prompt": "ご飯を / 私は / 毎日 / 食べます",
      "expected_answer": "私は毎日ご飯を食べます",
      "context": "Organize as palavras para formar: 'Eu como arroz todo dia'"
    }
  ]
}"""


def generate_exercises_for_card(
    card_content: str,
    card_back: str,
    card_type: str,
    context_sentence: str = "",
    target_language: str = "ja",
    native_language: str = "pt-BR",
) -> ExerciseGenerationResult:
    """
    Gera os 3 tipos de exercício para um card via Claude.
    Fallback para geração local se API não disponível.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        # Gera localmente sem API
        return _generate_exercises_locally(
            card_content, card_back, card_type, context_sentence,
            target_language, native_language
        )

    client = anthropic.Anthropic(api_key=api_key)

    user_message = f"""Gere 3 exercícios para este item de {target_language} (aluno fala {native_language}):

Tipo do item: {card_type}
Conteúdo: {card_content}
Significado/Resposta: {card_back}
Frase de contexto: {context_sentence or "não disponível"}

Crie um exercício de cada tipo: translation, fill_blank, build_sentence.
Retorne APENAS o JSON."""

    try:
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=800,
            system=EXERCISE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        response_text = message.content[0].text.strip()
        json_text = _extract_json(response_text)
        data = json.loads(json_text)

        exercises = []
        for ex in data.get("exercises", []):
            ex_type = _map_exercise_type(ex.get("type", "translation"))
            exercises.append(GeneratedExercise(
                exercise_type=ex_type,
                prompt=ex.get("prompt", ""),
                expected_answer=ex.get("expected_answer", ""),
                context=ex.get("context"),
                options=ex.get("options"),
            ))

        return ExerciseGenerationResult(success=True, exercises=exercises)

    except (json.JSONDecodeError, anthropic.APIError, Exception) as e:
        # Fallback para geração local
        result = _generate_exercises_locally(
            card_content, card_back, card_type, context_sentence,
            target_language, native_language
        )
        return result


def _generate_exercises_locally(
    content: str,
    back: str,
    card_type: str,
    context_sentence: str,
    target_language: str,
    native_language: str,
) -> ExerciseGenerationResult:
    """
    Geração de exercícios local (sem API).
    Usado como fallback ou quando ANTHROPIC_API_KEY não está configurada.
    """
    exercises = []

    # 1. Tradução ativa
    exercises.append(GeneratedExercise(
        exercise_type=ExerciseType.TRANSLATION,
        prompt=f"Como se diz em {target_language}: \"{_extract_translation(back)}\"?",
        expected_answer=content,
        context=f"Dica: {back}",
    ))

    # 2. Completar lacuna
    if context_sentence and content in context_sentence:
        blanked = context_sentence.replace(content, "___", 1)
        exercises.append(GeneratedExercise(
            exercise_type=ExerciseType.FILL_BLANK,
            prompt=blanked,
            expected_answer=content,
            context="Complete a lacuna com a palavra correta.",
        ))
    else:
        exercises.append(GeneratedExercise(
            exercise_type=ExerciseType.FILL_BLANK,
            prompt=f"___ significa \"{_extract_translation(back)}\" em {target_language}.",
            expected_answer=content,
            context="Preencha com a palavra correta.",
        ))

    # 3. Construir frase
    if context_sentence:
        # Embaralha as palavras da frase de contexto
        words = context_sentence.replace("。", " 。").replace("、", " 、").split()
        if len(words) > 2:
            shuffled = _shuffle_words(words, content)
            exercises.append(GeneratedExercise(
                exercise_type=ExerciseType.BUILD_SENTENCE,
                prompt=" / ".join(shuffled),
                expected_answer=context_sentence,
                context=f"Organize as palavras para formar uma frase com '{content}'",
            ))
        else:
            exercises.append(_default_build_sentence(content, back))
    else:
        exercises.append(_default_build_sentence(content, back))

    return ExerciseGenerationResult(success=True, exercises=exercises)


def evaluate_answer(
    user_answer: str,
    expected_answer: str,
    exercise_type: ExerciseType,
    tolerance: float = 0.85,
) -> AnswerEvaluation:
    """
    Avalia a resposta do usuário comparando com a resposta esperada.

    Estratégia:
    - Normaliza strings (lowercase, sem acentos desnecessários, sem pontuação extra)
    - Calcula similaridade de caracteres
    - Para build_sentence: verifica ordem das palavras
    - Para translation: aceita variações comuns

    Args:
        user_answer: Resposta do usuário
        expected_answer: Resposta esperada
        exercise_type: Tipo do exercício
        tolerance: Score mínimo para considerar correto

    Returns:
        AnswerEvaluation com score e feedback
    """
    if not user_answer or not user_answer.strip():
        return AnswerEvaluation(
            is_correct=False,
            score=0.0,
            feedback="Resposta em branco.",
            error_category="empty",
        )

    user_norm = _normalize_answer(user_answer)
    expected_norm = _normalize_answer(expected_answer)

    # Resposta exata
    if user_norm == expected_norm:
        return AnswerEvaluation(
            is_correct=True,
            score=1.0,
            feedback="Perfeito!",
        )

    # Múltiplas respostas aceitas (separadas por /)
    accepted_answers = [_normalize_answer(a) for a in expected_answer.split("/")]
    if user_norm in accepted_answers:
        return AnswerEvaluation(
            is_correct=True,
            score=1.0,
            feedback="Correto!",
        )

    # Avaliação por tipo
    if exercise_type == ExerciseType.BUILD_SENTENCE:
        return _evaluate_build_sentence(user_norm, expected_norm, user_answer, expected_answer)
    elif exercise_type == ExerciseType.FILL_BLANK:
        return _evaluate_fill_blank(user_norm, accepted_answers, user_answer, expected_answer)
    else:
        return _evaluate_translation(user_norm, accepted_answers, user_answer, expected_answer)


def _evaluate_build_sentence(
    user_norm: str, expected_norm: str,
    user_raw: str, expected_raw: str
) -> AnswerEvaluation:
    """Avalia exercício de construção de frase — pondera ordem das palavras."""
    user_words = set(user_norm.split())
    expected_words = set(expected_norm.split())

    # Palavras corretas mas ordem errada
    if user_words == expected_words:
        return AnswerEvaluation(
            is_correct=False,
            score=0.7,
            feedback=f"Palavras corretas, mas a ordem está errada. Correto: {expected_raw}",
            error_category="order",
        )

    # Palavras parcialmente corretas
    intersection = user_words & expected_words
    if len(expected_words) > 0:
        score = len(intersection) / len(expected_words)
        if score >= 0.7:
            return AnswerEvaluation(
                is_correct=False,
                score=score,
                feedback=f"Quase! Verifique as palavras. Correto: {expected_raw}",
                error_category="order",
            )

    return AnswerEvaluation(
        is_correct=False,
        score=0.0,
        feedback=f"Resposta incorreta. Correto: {expected_raw}",
        error_category="meaning",
    )


def _evaluate_fill_blank(
    user_norm: str, accepted_norms: List[str],
    user_raw: str, expected_raw: str
) -> AnswerEvaluation:
    """Avalia completar lacuna — mais tolerante com variações."""
    # Verifica se começa com a resposta correta
    for accepted in accepted_norms:
        if user_norm.startswith(accepted) or accepted.startswith(user_norm):
            return AnswerEvaluation(
                is_correct=True,
                score=0.9,
                feedback="Correto!",
            )

    return AnswerEvaluation(
        is_correct=False,
        score=0.0,
        feedback=f"Resposta incorreta. Esperado: {expected_raw}",
        error_category="vocabulary",
    )


def _evaluate_translation(
    user_norm: str, accepted_norms: List[str],
    user_raw: str, expected_raw: str
) -> AnswerEvaluation:
    """Avalia tradução — verifica se a resposta contém os elementos chave."""
    # Verifica se a resposta está contida ou contém a resposta esperada
    for accepted in accepted_norms:
        if accepted in user_norm or user_norm in accepted:
            return AnswerEvaluation(
                is_correct=True,
                score=0.85,
                feedback="Correto! (resposta parcialmente aceita)",
            )

    # Cálculo de similaridade simples por caracteres comuns
    score = _char_similarity(user_norm, accepted_norms[0] if accepted_norms else "")

    if score >= 0.7:
        return AnswerEvaluation(
            is_correct=False,
            score=score,
            feedback=f"Próximo, mas não exato. Esperado: {expected_raw}",
            error_category="spelling",
        )

    return AnswerEvaluation(
        is_correct=False,
        score=score,
        feedback=f"Resposta incorreta. Esperado: {expected_raw}",
        error_category="vocabulary",
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _normalize_answer(text: str) -> str:
    """Normaliza resposta para comparação."""
    text = text.strip().lower()
    # Remove pontuação final comum
    text = re.sub(r"[。、！？\.!?,;]$", "", text)
    # Normaliza espaços
    text = re.sub(r"\s+", " ", text)
    return text


def _extract_translation(back: str) -> str:
    """Extrai a tradução principal do campo back do card."""
    # O back pode ser "食べる (comer)" ou só "comer"
    match = re.search(r"\(([^)]+)\)", back)
    if match:
        return match.group(1)
    return back.split("\n")[0].strip()


def _shuffle_words(words: list, anchor: str) -> list:
    """Embaralha palavras mantendo o conteúdo principal no meio."""
    import random
    shuffled = words.copy()
    random.shuffle(shuffled)
    return shuffled


def _default_build_sentence(content: str, back: str) -> GeneratedExercise:
    """Exercício de build_sentence padrão quando não há contexto."""
    return GeneratedExercise(
        exercise_type=ExerciseType.BUILD_SENTENCE,
        prompt=f"Escreva a palavra que significa: {_extract_translation(back)}",
        expected_answer=content,
        context="Digite a resposta correta em japonês.",
    )


def _map_exercise_type(type_str: str) -> ExerciseType:
    """Mapeia string para enum ExerciseType."""
    mapping = {
        "translation": ExerciseType.TRANSLATION,
        "fill_blank": ExerciseType.FILL_BLANK,
        "build_sentence": ExerciseType.BUILD_SENTENCE,
    }
    return mapping.get(type_str, ExerciseType.TRANSLATION)


def _extract_json(text: str) -> str:
    """Extrai JSON de resposta da IA."""
    text = text.strip()
    if text.startswith("{"):
        return text
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.rfind("```")
        if end > start:
            return text[start:end].strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return text[start:end]
    return text


def _char_similarity(s1: str, s2: str) -> float:
    """Calcula similaridade simples por caracteres comuns."""
    if not s1 or not s2:
        return 0.0
    s1_chars = set(s1)
    s2_chars = set(s2)
    intersection = s1_chars & s2_chars
    union = s1_chars | s2_chars
    return len(intersection) / len(union) if union else 0.0
