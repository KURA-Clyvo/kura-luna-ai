"""Router de envio outbound de WhatsApp via Twilio.

Endpoint: POST /whatsapp/enviar
Auth: header X-API-Key validado contra LUNA_INBOUND_API_KEY.
LGPD: nunca logar conteúdo da mensagem nem número de telefone — apenas metadados.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.messaging.twilio_client import ITwilioGateway, MessagingError
from src.web.dependencies import get_twilio_gateway, validar_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WhatsApp"])


class WhatsAppEnvioRequest(BaseModel):
    para: str
    mensagem: str


class WhatsAppEnvioResponse(BaseModel):
    status: str
    sid: str


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
    _: Annotated[None, Depends(validar_api_key)],
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
