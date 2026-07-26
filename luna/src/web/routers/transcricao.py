"""Router de transcrição de áudio → draft SOAP.

Endpoint: POST /transcricao
Auth: header X-API-Key validado contra LUNA_INBOUND_API_KEY (mesmo esquema de /whatsapp/enviar).
LGPD: nunca logar conteúdo transcrito, nome de arquivo nem OPENAI_API_KEY.
O vet sempre confirma antes de salvar — este endpoint só devolve sugestão (sem auto-save).
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel

from src.config.settings import Settings
from src.services.transcricao_service import (
    FORMATOS_PERMITIDOS,
    TAMANHO_MAXIMO_BYTES,
    IWhisperGateway,
    SoapDraft,
    TranscricaoError,
    montar_soap_draft,
)
from src.web.dependencies import get_settings, get_whisper_gateway

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Transcrição"])


class TranscricaoResponse(BaseModel):
    transcricao: str | None
    soap: SoapDraft | None


def _verificar_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    """Dependência de autenticação: compara header X-API-Key com LUNA_INBOUND_API_KEY."""
    chave_esperada = settings.LUNA_INBOUND_API_KEY
    if not chave_esperada or x_api_key != chave_esperada:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida")


def _extensao(nome_arquivo: str) -> str:
    return nome_arquivo.rsplit(".", 1)[-1].lower() if "." in nome_arquivo else ""


@router.post(
    "/transcricao",
    response_model=TranscricaoResponse,
    summary="Transcreve áudio de consulta e gera draft SOAP",
    description=(
        "Recebe áudio (mp3/m4a/wav, até 25MB), transcreve via Whisper e monta um draft "
        "SOAP (S/O/A/P) por heurística de palavras-chave. Requer header `X-API-Key` válido. "
        "Se a Whisper falhar, retorna transcricao/soap nulos para edição manual — nunca 500. "
        "O vet deve sempre revisar e confirmar antes de salvar."
    ),
)
async def transcrever_audio(
    _: Annotated[None, Depends(_verificar_api_key)],
    whisper: Annotated[IWhisperGateway, Depends(get_whisper_gateway)],
    audio: UploadFile = File(...),
) -> TranscricaoResponse:
    extensao = _extensao(audio.filename or "")
    if extensao not in FORMATOS_PERMITIDOS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato de áudio não suportado: use {', '.join(sorted(FORMATOS_PERMITIDOS))}",
        )

    conteudo = await audio.read()
    if len(conteudo) > TAMANHO_MAXIMO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arquivo excede o limite de 25MB da Whisper API",
        )

    # LGPD: logar apenas metadados — nunca o conteúdo do áudio nem a transcrição
    logger.info("transcricao.iniciada formato=%s tamanho_bytes=%d", extensao, len(conteudo))
    try:
        texto = await whisper.transcrever(
            conteudo, audio.filename or "audio", audio.content_type or "application/octet-stream"
        )
    except TranscricaoError:
        logger.error("transcricao.whisper_indisponivel")
        return TranscricaoResponse(transcricao=None, soap=None)

    soap = montar_soap_draft(texto)
    logger.info("transcricao.concluida tamanho_texto=%d", len(texto))
    return TranscricaoResponse(transcricao=texto, soap=soap)
