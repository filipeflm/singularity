"""
Serviço de Transcrição — Singular
Extrai o texto de vídeos do YouTube usando youtube-transcript-api.

Estratégia (sem custos):
  1. Tenta obter transcript do YouTube com preferência ao idioma alvo
  2. Fallback: qualquer transcript disponível
  3. Fallback final: retorna erro descritivo para o usuário

O texto retornado é o insumo principal para o motor de extração da IA.
"""

import re
from dataclasses import dataclass
from typing import Optional

from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)


# ─── Dataclass de resultado ────────────────────────────────────────────────────

@dataclass
class TranscriptResult:
    success: bool
    text: str                        # texto completo concatenado
    language: Optional[str] = None   # código do idioma detectado (ex: "ja")
    title: Optional[str] = None      # título extraído da URL se disponível
    error: Optional[str] = None      # mensagem de erro se success=False


# ─── Extração de video_id ──────────────────────────────────────────────────────

def extract_video_id(url: str) -> Optional[str]:
    """
    Extrai o video_id de diferentes formatos de URL do YouTube.
    Suporta: youtube.com/watch?v=, youtu.be/, youtube.com/shorts/
    """
    patterns = [
        r"(?:v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        r"youtube\.com/embed/([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


# ─── Funções principais ────────────────────────────────────────────────────────

def get_transcript(url: str, preferred_language: str = "ja") -> TranscriptResult:
    """
    Obtém o transcript de um vídeo do YouTube.

    Args:
        url: URL completa do vídeo
        preferred_language: Idioma preferencial (ex: "ja" para japonês)

    Returns:
        TranscriptResult com texto concatenado e metadados
    """
    video_id = extract_video_id(url)
    if not video_id:
        return TranscriptResult(
            success=False,
            text="",
            error="URL inválida. Certifique-se de usar um link do YouTube válido.",
        )

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Tenta idioma preferencial primeiro, depois qualquer disponível
        transcript = None
        language_used = None

        try:
            transcript = transcript_list.find_transcript([preferred_language])
            language_used = preferred_language
        except NoTranscriptFound:
            # Tenta idiomas alternativos comuns
            fallback_languages = ["ja", "en", "pt", "pt-BR", "pt-PT"]
            for lang in fallback_languages:
                if lang == preferred_language:
                    continue
                try:
                    transcript = transcript_list.find_transcript([lang])
                    language_used = lang
                    break
                except NoTranscriptFound:
                    continue

        if not transcript:
            # Pega qualquer transcript disponível
            available = list(transcript_list)
            if not available:
                return TranscriptResult(
                    success=False,
                    text="",
                    error="Nenhum transcript disponível para este vídeo.",
                )
            transcript = available[0]
            language_used = transcript.language_code

        # Busca e concatena os segmentos
        segments = transcript.fetch()
        full_text = _segments_to_text(segments)

        if not full_text.strip():
            return TranscriptResult(
                success=False,
                text="",
                error="O transcript foi obtido mas está vazio.",
            )

        return TranscriptResult(
            success=True,
            text=full_text,
            language=language_used,
        )

    except TranscriptsDisabled:
        return TranscriptResult(
            success=False,
            text="",
            error="Transcrições estão desabilitadas para este vídeo.",
        )
    except VideoUnavailable:
        return TranscriptResult(
            success=False,
            text="",
            error="Vídeo indisponível ou privado.",
        )
    except Exception as e:
        return TranscriptResult(
            success=False,
            text="",
            error=f"Erro ao obter transcript: {str(e)}",
        )


def _segments_to_text(segments: list) -> str:
    """
    Converte lista de segmentos {text, start, duration} em texto corrido.
    Preserva a pontuação e capitalização originais.
    """
    texts = []
    for segment in segments:
        text = segment.get("text", "").strip()
        if text:
            # Remove marcadores de música e outros artefatos comuns
            if text.startswith("[") and text.endswith("]"):
                continue
            if text.startswith("(") and text.endswith(")"):
                continue
            texts.append(text)

    # Junta com espaço, evitando duplicar espaços
    return " ".join(texts)


def get_mock_transcript(language: str = "ja") -> TranscriptResult:
    """
    Retorna um transcript mock para desenvolvimento e testes.
    Simula uma aula de japonês para iniciantes (N5).
    """
    mock_text = """
    皆さん、こんにちは！今日は日本語の基本的な挨拶を学びましょう。
    まず、「おはようございます」は朝の挨拶です。
    「こんにちは」は昼の挨拶で、「こんばんは」は夜の挨拶です。
    次に、自己紹介を練習しましょう。
    「私の名前は田中です」— これは「私の名前は〜です」というパターンです。
    「どうぞよろしくお願いします」は会う時によく使います。
    数字も大切です。一、二、三、四、五。
    「これはいくらですか？」は買い物で使う質問です。
    「ありがとうございます」— お礼を言う時の表現です。
    「すみません」は謝る時や呼びかける時に使います。
    動詞の基本：食べる（たべる）は「食べます」になります。
    「私は毎日日本語を勉強します」— 勉強する（べんきょうする）という動詞です。
    「どこへ行きますか？」— 行く（いく）という動詞と場所の質問。
    形容詞：「大きい」は big、「小さい」は small です。
    「この本は面白いです」— 形容詞の使い方の例です。
    今日学んだことを復習しましょう。挨拶、自己紹介、数字、基本動詞。
    """
    return TranscriptResult(
        success=True,
        text=mock_text.strip(),
        language=language,
        title="日本語入門 - 基本的な挨拶と表現 (Mock)",
    )
