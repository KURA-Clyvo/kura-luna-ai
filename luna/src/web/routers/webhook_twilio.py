"""Router para o webhook de mensagens WhatsApp inbound do Twilio."""
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response

from src.config.settings import Settings
from src.messaging.twilio_inbound import (
    montar_twiml_ack,
    parse_inbound_payload,
    validar_assinatura,
)
from src.services.inbound_message_service import InboundMessageService
from src.web.dependencies import get_inbound_service, get_settings

router = APIRouter(tags=["webhook"])


def _url_assinada(request: Request, settings: Settings) -> str:
    """URL que o Twilio assinou: a PÚBLICA configurada no console, não a que chegou aqui.

    Atrás de túnel/proxy (localtunnel, ngrok, container Docker) `request.url` é
    `http://localhost:8000/...` enquanto o Twilio assinou `https://<túnel>/...` — a
    assinatura nunca batia e todo inbound levava 403. Só funcionava com o uvicorn direto
    no host, onde o X-Forwarded-Proto vindo de 127.0.0.1 é confiável por padrão.
    `WEBHOOK_PUBLIC_URL` é exatamente a URL cadastrada no console do Twilio.
    """
    publica = settings.WEBHOOK_PUBLIC_URL.strip()
    if not publica:
        return str(request.url)
    return f"{publica}?{request.url.query}" if request.url.query else publica


async def validar_twilio_signature(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Dependency: valida X-Twilio-Signature antes de processar o payload.

    Raises:
        HTTPException 403: se o header estiver ausente ou a assinatura for inválida.
    """
    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        raise HTTPException(status_code=403, detail="X-Twilio-Signature ausente")

    form_data = await request.form()
    url = _url_assinada(request, settings)
    params = dict(form_data)

    if not validar_assinatura(signature, url, params, settings.TWILIO_TOKEN):
        raise HTTPException(status_code=403, detail="Assinatura Twilio inválida")


@router.post(
    "/webhook/twilio/whatsapp",
    dependencies=[Depends(validar_twilio_signature)],
    response_class=Response,
)
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    inbound_service: Annotated[InboundMessageService, Depends(get_inbound_service)],
) -> Response:
    """Recebe mensagens WhatsApp do Twilio.

    Retorna TwiML vazio em < 200ms. Todo processamento ocorre em BackgroundTask.
    """
    form_data = await request.form()
    try:
        msg = parse_inbound_payload(dict(form_data))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    background_tasks.add_task(inbound_service.processar, msg)

    return Response(
        content=montar_twiml_ack(),
        media_type="application/xml",
        status_code=200,
    )
