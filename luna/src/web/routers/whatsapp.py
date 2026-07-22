"""Router de envio outbound de WhatsApp via Twilio.

Endpoint: POST /whatsapp/enviar
Auth: header X-API-Key validado contra LUNA_INBOUND_API_KEY.
LGPD: nunca logar conteúdo da mensagem nem número de telefone — apenas metadados.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from src.config.settings import Settings
from src.messaging.twilio_client import ITwilioGateway, MessagingError
from src.web.dependencies import get_settings, get_twilio_gateway

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WhatsApp"])


class WhatsAppEnvioRequest(BaseModel):
    para: str
    mensagem: str


class WhatsAppEnvioResponse(BaseModel):
    status: str
    sid: str


def _verificar_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    """Dependência de autenticação: compara header X-API-Key com LUNA_INBOUND_API_KEY."""
    chave_esperada = settings.LUNA_INBOUND_API_KEY
    if not chave_esperada or x_api_key != chave_esperada:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida")


@router.post(
    "/whatsapp/enviar",
    response_model=WhatsAppEnvioResponse,
    summary="Envia mensagem WhatsApp via Twilio",
    description=(
        "Envia uma mensagem WhatsApp para o número informado. "
        "Requer header `X-API-Key` válido. "
        "LGPD: conteúdo da mensagem e telefone nunca são logados."
    ),
)
def enviar_whatsapp(
    req: WhatsAppEnvioRequest,
    _: Annotated[None, Depends(_verificar_api_key)],
    twilio: Annotated[ITwilioGateway, Depends(get_twilio_gateway)],
) -> WhatsAppEnvioResponse:
    # LGPD: logar apenas tipo de operação e metadados — nunca o conteúdo
    logger.info("whatsapp.enviar tipo=outbound")
    try:
        sid = twilio.enviar_whatsapp(req.para, req.mensagem)
    except MessagingError as exc:
        logger.error("whatsapp.enviar falhou codigo=%s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Falha ao enviar mensagem via Twilio") from exc
    return WhatsAppEnvioResponse(status="enviado", sid=sid)
