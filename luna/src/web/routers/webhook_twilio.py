"""Router para o webhook de mensagens WhatsApp inbound do Twilio."""
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response

from src.messaging.twilio_inbound import (
    montar_twiml_ack,
    parse_inbound_payload,
    validar_assinatura,
)
from src.services.inbound_message_service import InboundMessageService
from src.web.dependencies import get_inbound_service, get_settings

router = APIRouter(tags=["webhook"])


async def validar_twilio_signature(
    request: Request,
    settings=Depends(get_settings),  # type: ignore[assignment]
) -> None:
    """Dependency: valida X-Twilio-Signature antes de processar o payload.

    Raises:
        HTTPException 403: se o header estiver ausente ou a assinatura for inválida.
    """
    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        raise HTTPException(status_code=403, detail="X-Twilio-Signature ausente")

    form_data = await request.form()
    url = str(request.url)
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
