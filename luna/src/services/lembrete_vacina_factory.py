"""Fábrica de composição do LembreteVacinaService (LU-04).

Extraída de ``cli/main.py::_create_lembrete_service`` para ser reutilizada
também pelo scheduler do ``lifespan`` e pelo endpoint
``POST /jobs/lembrete-vacina/executar`` — antes desta extração a montagem só
existia na CLI e cada consumidor novo teria que duplicá-la (achado do brief:
"não duplique a montagem").

Não cria nem fecha o ``OracleConnectionPool``: quem chama decide o ciclo de
vida do pool (a CLI cria um pool próprio por invocação e fecha no ``finally``;
o servidor HTTP reusa o pool único do ``lifespan``).

``TwilioGateway.__init__`` valida a credencial no construtor (SDK da Twilio)
— sem ``TWILIO_SID``/``TWILIO_TOKEN``/``TWILIO_FROM_NUMBER`` válidos, esta
função levanta ``twilio.base.exceptions.TwilioException`` (achado F4-1,
`lu-03-revisao.md`). Quem chama esta fábrica em um contexto que não pode
derrubar o processo (endpoint HTTP, tick do scheduler) precisa capturar essa
exceção e responder de forma declarada — nunca deixar o processo morrer.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.db.repositories.log_erro_repo import LogErroRepository
from src.db.repositories.notificacao_repo import NotificacaoRepository
from src.db.repositories.vacina_repo import VacinaRepository
from src.messaging.twilio_client import TwilioGateway
from src.services.notification_service import LembreteVacinaService

if TYPE_CHECKING:
    from src.config.settings import Settings
    from src.db.connection import OracleConnectionPool


def criar_lembrete_service(
    settings: "Settings", pool: "OracleConnectionPool"
) -> LembreteVacinaService:
    """Compõe o LembreteVacinaService com os repositórios e o gateway Twilio.

    Pode levantar ``twilio.base.exceptions.TwilioException`` se as
    credenciais Twilio estiverem ausentes/inválidas (validado no construtor
    do SDK) — ver docstring do módulo.
    """
    vacina_repo = VacinaRepository(pool)
    notificacao_repo = NotificacaoRepository(pool)
    log_repo = LogErroRepository(pool)
    gateway = TwilioGateway(
        account_sid=settings.TWILIO_SID,
        auth_token=settings.TWILIO_TOKEN,
        from_number=settings.TWILIO_FROM_NUMBER,
    )
    return LembreteVacinaService(vacina_repo, notificacao_repo, gateway, log_repo)
