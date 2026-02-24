"""
Serviço de Extração de Conhecimento — Singular
Usa Claude (claude-3-haiku) para extrair vocabulário, frases e gramática
de um transcript de aula.

Princípio (bigbang.md §2):
  "O sistema não extrai tudo. Ele seleciona o que realmente importa."

A extração retorna JSON estruturado e validado. Se o JSON for inválido,
a função tenta recuperação parcial antes de falhar.

Custo estimado: claude-3-haiku custa ~$0.00025/1K tokens de input.
Para um transcript típico de 5min (~2000 tokens) + output (~1500 tokens),
o custo por aula é < $0.002 (menos de um centavo).
"""

import json
import os
from dataclasses import dataclass, field
from typing import List, Optional

import anthropic


# ─── Dataclasses de saída ──────────────────────────────────────────────────────

@dataclass
class ExtractedVocabItem:
    content: str           # a palavra (ex: "食べる")
    reading: str           # leitura (ex: "たべる")
    translation: str       # tradução (ex: "comer")
    context_sentence: str  # frase da aula onde apareceu
    complexity: float      # 0.0-1.0
    frequency: float       # frequência relativa no texto
    usefulness: float      # utilidade prática


@dataclass
class ExtractedPhraseItem:
    content: str           # a frase completa
    reading: str           # leitura com furigana (se japonês)
    translation: str       # tradução
    context_sentence: str  # contexto da aula
    complexity: float
    usefulness: float


@dataclass
class ExtractedGrammarItem:
    content: str           # padrão gramatical (ex: "〜ます形")
    explanation: str       # explicação simples
    context_sentence: str  # exemplo da aula
    complexity: float
    usefulness: float


@dataclass
class ExtractionResult:
    success: bool
    vocabulary: List[ExtractedVocabItem] = field(default_factory=list)
    phrases: List[ExtractedPhraseItem] = field(default_factory=list)
    grammar: List[ExtractedGrammarItem] = field(default_factory=list)
    detected_language: str = "ja"
    detected_level: str = "unknown"
    error: Optional[str] = None


# ─── Prompt de extração ───────────────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """Você é um especialista em extração de conhecimento linguístico para sistemas de aprendizado.

Sua tarefa é analisar a transcrição de uma aula de idioma e extrair os elementos mais importantes para aprendizado.

REGRAS CRÍTICAS:
1. Extraia SOMENTE o que é essencial — qualidade sobre quantidade
2. Priorize: alta frequência, alta utilidade prática, contexto claro
3. Para vocabulário: máximo 15 itens por transcript
4. Para frases: máximo 8 itens
5. Para gramática: máximo 5 padrões
6. Retorne APENAS JSON válido, sem texto adicional

FORMATO DE RESPOSTA (JSON estrito):
{
  "detected_language": "ja",
  "detected_level": "N5",
  "vocabulary": [
    {
      "content": "食べる",
      "reading": "たべる",
      "translation": "comer",
      "context_sentence": "私は毎日ご飯を食べます。",
      "complexity": 0.2,
      "frequency": 0.8,
      "usefulness": 0.9
    }
  ],
  "phrases": [
    {
      "content": "どうぞよろしくお願いします",
      "reading": "どうぞよろしくおねがいします",
      "translation": "Muito prazer, por favor me trate bem",
      "context_sentence": "Usada em apresentações formais",
      "complexity": 0.4,
      "usefulness": 0.95
    }
  ],
  "grammar": [
    {
      "content": "〜ます (forma educada do verbo)",
      "explanation": "Forma polida do verbo. Adiciona 'ます' ao radical do verbo. Ex: 食べ + ます = 食べます",
      "context_sentence": "私は日本語を勉強します。",
      "complexity": 0.3,
      "usefulness": 1.0
    }
  ]
}"""


def extract_from_transcript(
    transcript_text: str,
    target_language: str = "ja",
    native_language: str = "pt-BR",
    max_retries: int = 2,
) -> ExtractionResult:
    """
    Extrai vocabulário, frases e gramática de um transcript usando Claude.

    Args:
        transcript_text: Texto da transcrição
        target_language: Idioma sendo aprendido (ex: "ja")
        native_language: Idioma nativo do aluno (ex: "pt-BR")
        max_retries: Tentativas em caso de JSON inválido

    Returns:
        ExtractionResult com listas estruturadas de items extraídos
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return ExtractionResult(
            success=False,
            error="ANTHROPIC_API_KEY não configurada. Adicione no arquivo .env",
        )

    client = anthropic.Anthropic(api_key=api_key)

    # Trunca transcript muito longo (economiza tokens)
    max_transcript_chars = 4000
    if len(transcript_text) > max_transcript_chars:
        transcript_text = transcript_text[:max_transcript_chars] + "\n[...transcript truncado...]"

    user_message = f"""Analise esta transcrição de aula de {target_language} e extraia o conhecimento linguístico essencial.
O aluno é falante nativo de {native_language}.

TRANSCRIÇÃO:
{transcript_text}

Retorne APENAS o JSON estruturado conforme as instruções. Sem explicações adicionais."""

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            message = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=2000,
                system=EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            response_text = message.content[0].text.strip()

            # Tenta extrair JSON mesmo se houver texto ao redor
            json_text = _extract_json_from_response(response_text)
            data = json.loads(json_text)

            return _parse_extraction_response(data)

        except json.JSONDecodeError as e:
            last_error = f"JSON inválido na tentativa {attempt + 1}: {str(e)}"
            continue
        except anthropic.APIError as e:
            return ExtractionResult(
                success=False,
                error=f"Erro na API Anthropic: {str(e)}",
            )
        except Exception as e:
            return ExtractionResult(
                success=False,
                error=f"Erro inesperado na extração: {str(e)}",
            )

    return ExtractionResult(
        success=False,
        error=f"Falha após {max_retries + 1} tentativas. Último erro: {last_error}",
    )


def _extract_json_from_response(text: str) -> str:
    """
    Extrai JSON de uma resposta que pode conter texto adicional.
    Procura pelo primeiro { e último } para isolar o JSON.
    """
    # Tenta JSON puro primeiro
    text = text.strip()
    if text.startswith("{"):
        return text

    # Procura bloco de código markdown
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.rfind("```")
        if end > start:
            return text[start:end].strip()

    if "```" in text:
        start = text.find("```") + 3
        end = text.rfind("```")
        if end > start:
            return text[start:end].strip()

    # Procura primeiro { e último }
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return text[start:end]

    return text


def _parse_extraction_response(data: dict) -> ExtractionResult:
    """Converte o dict JSON em ExtractionResult tipado."""
    try:
        vocabulary = []
        for item in data.get("vocabulary", []):
            vocabulary.append(ExtractedVocabItem(
                content=item.get("content", ""),
                reading=item.get("reading", ""),
                translation=item.get("translation", ""),
                context_sentence=item.get("context_sentence", ""),
                complexity=float(item.get("complexity", 0.5)),
                frequency=float(item.get("frequency", 0.5)),
                usefulness=float(item.get("usefulness", 0.5)),
            ))

        phrases = []
        for item in data.get("phrases", []):
            phrases.append(ExtractedPhraseItem(
                content=item.get("content", ""),
                reading=item.get("reading", ""),
                translation=item.get("translation", ""),
                context_sentence=item.get("context_sentence", ""),
                complexity=float(item.get("complexity", 0.5)),
                usefulness=float(item.get("usefulness", 0.5)),
            ))

        grammar = []
        for item in data.get("grammar", []):
            grammar.append(ExtractedGrammarItem(
                content=item.get("content", ""),
                explanation=item.get("explanation", ""),
                context_sentence=item.get("context_sentence", ""),
                complexity=float(item.get("complexity", 0.5)),
                usefulness=float(item.get("usefulness", 0.5)),
            ))

        return ExtractionResult(
            success=True,
            vocabulary=vocabulary,
            phrases=phrases,
            grammar=grammar,
            detected_language=data.get("detected_language", "ja"),
            detected_level=data.get("detected_level", "unknown"),
        )

    except Exception as e:
        return ExtractionResult(
            success=False,
            error=f"Erro ao parsear resposta da extração: {str(e)}",
        )


def get_mock_extraction() -> ExtractionResult:
    """
    Retorna extração mock para desenvolvimento/testes.
    Conteúdo de uma aula básica de japonês (N5).
    """
    return ExtractionResult(
        success=True,
        detected_language="ja",
        detected_level="N5",
        vocabulary=[
            ExtractedVocabItem("食べる", "たべる", "comer", "私は毎日ご飯を食べます。", 0.2, 0.9, 0.95),
            ExtractedVocabItem("飲む", "のむ", "beber", "水を飲みます。", 0.2, 0.8, 0.90),
            ExtractedVocabItem("行く", "いく", "ir", "学校へ行きます。", 0.2, 0.95, 0.95),
            ExtractedVocabItem("来る", "くる", "vir", "友達が来ます。", 0.3, 0.85, 0.90),
            ExtractedVocabItem("見る", "みる", "ver/assistir", "映画を見ます。", 0.2, 0.85, 0.90),
            ExtractedVocabItem("大きい", "おおきい", "grande", "この犬は大きいです。", 0.2, 0.8, 0.85),
            ExtractedVocabItem("小さい", "ちいさい", "pequeno", "この猫は小さいです。", 0.2, 0.8, 0.85),
            ExtractedVocabItem("面白い", "おもしろい", "interessante/divertido", "この本は面白いです。", 0.3, 0.75, 0.88),
            ExtractedVocabItem("勉強する", "べんきょうする", "estudar", "毎日日本語を勉強します。", 0.3, 0.9, 0.95),
            ExtractedVocabItem("ありがとう", "ありがとう", "obrigado (informal)", "ありがとうございます。", 0.1, 0.95, 1.0),
        ],
        phrases=[
            ExtractedPhraseItem(
                "どうぞよろしくお願いします",
                "どうぞよろしくおねがいします",
                "Muito prazer / Por favor me trate bem",
                "Usada em apresentações formais",
                0.5, 0.95,
            ),
            ExtractedPhraseItem(
                "これはいくらですか？",
                "これはいくらですか？",
                "Quanto custa isto?",
                "Pergunta essencial para compras",
                0.3, 0.90,
            ),
            ExtractedPhraseItem(
                "私の名前は〜です",
                "わたしのなまえは〜です",
                "Meu nome é ~",
                "Padrão de apresentação pessoal",
                0.2, 0.95,
            ),
            ExtractedPhraseItem(
                "すみません",
                "すみません",
                "Com licença / Desculpe",
                "Usada para pedir desculpas ou chamar atenção",
                0.1, 1.0,
            ),
        ],
        grammar=[
            ExtractedGrammarItem(
                "〜ます (forma educada)",
                "Forma polida dos verbos japoneses. Usado em situações formais e com desconhecidos. Adiciona 'ます' ao radical do verbo.",
                "私は毎日日本語を勉強します。",
                0.4, 1.0,
            ),
            ExtractedGrammarItem(
                "〜は〜です (estrutura básica de identidade)",
                "Padrão fundamental: [tópico]は[informação]です. Equivale a '[tópico] é [informação]'.",
                "私は学生です。(Eu sou estudante.)",
                0.2, 1.0,
            ),
            ExtractedGrammarItem(
                "〜を〜 (partícula de objeto direto)",
                "A partícula を marca o objeto direto de um verbo. Responde 'o quê?' da ação.",
                "日本語を勉強します。(Estudo japonês.)",
                0.4, 0.95,
            ),
        ],
    )
