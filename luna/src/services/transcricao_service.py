"""Transcrição de áudio (OpenAI Whisper) e montagem de draft SOAP.

O vet sempre confirma antes de salvar — este módulo só produz sugestão (sem auto-save).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Protocol, runtime_checkable

import httpx
from pydantic import BaseModel

FORMATOS_PERMITIDOS: frozenset[str] = frozenset({"mp3", "m4a", "wav"})
TAMANHO_MAXIMO_BYTES: int = 25 * 1024 * 1024  # limite do Whisper API

_WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"

# Heurística por palavras-chave (free-first PoC). Evolução natural: NER clínico via GPT.
_KEYWORDS_PLANO = (
    "prescr", "tratamento", "retorno em",
    "aplicar", "administrar", "encaminhar", "solicito exame", "medicar",
)
_KEYWORDS_AVALIACAO = (
    "diagnostico", "suspeita", "hipotese", "quadro compativel", "sugestivo de", "provavel",
)
_KEYWORDS_OBJETIVO = (
    "temperatura", "peso", "frequencia cardiaca", "frequencia respiratoria",
    "exame fisico", "ausculta", "palpacao", "mucosa", "linfonodo", "pressao arterial",
)


class TranscricaoError(Exception):
    """Levantado quando a transcrição via Whisper falha."""


class SoapDraft(BaseModel):
    s: str
    o: str
    a: str
    p: str


@runtime_checkable
class IWhisperGateway(Protocol):
    """Interface de transcrição de áudio."""

    async def transcrever(self, conteudo: bytes, nome_arquivo: str, content_type: str) -> str:
        """Transcreve o áudio e retorna o texto. Levanta TranscricaoError em falha."""
        ...


class WhisperGateway:
    """Implementação concreta do IWhisperGateway usando a OpenAI Whisper API via httpx."""

    def __init__(self, api_key: str, http_client: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._http = http_client

    async def transcrever(self, conteudo: bytes, nome_arquivo: str, content_type: str) -> str:
        if not self._api_key:
            raise TranscricaoError("OPENAI_API_KEY não configurada")
        try:
            resp = await self._http.post(
                _WHISPER_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                data={"model": "whisper-1"},
                files={"file": (nome_arquivo, conteudo, content_type)},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise TranscricaoError("Falha ao comunicar com a Whisper API") from exc

        texto = resp.json().get("text")
        if not texto:
            raise TranscricaoError("Whisper retornou transcrição vazia")
        return str(texto)


def _normalize(text: str) -> str:
    """Lowercase + remove diacríticos via decomposição NFKD."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def montar_soap_draft(texto: str) -> SoapDraft:
    """Classifica frases do texto transcrito em S/O/A/P por palavras-chave.

    Sentenças sem palavra-chave reconhecida caem em Subjetivo (relato/queixa, bucket padrão).
    """
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+|\n+", texto) if f.strip()]

    buckets: dict[str, list[str]] = {"s": [], "o": [], "a": [], "p": []}
    for frase in frases:
        norm = _normalize(frase)
        if any(kw in norm for kw in _KEYWORDS_PLANO):
            buckets["p"].append(frase)
        elif any(kw in norm for kw in _KEYWORDS_AVALIACAO):
            buckets["a"].append(frase)
        elif any(kw in norm for kw in _KEYWORDS_OBJETIVO):
            buckets["o"].append(frase)
        else:
            buckets["s"].append(frase)

    return SoapDraft(
        s=" ".join(buckets["s"]),
        o=" ".join(buckets["o"]),
        a=" ".join(buckets["a"]),
        p=" ".join(buckets["p"]),
    )
