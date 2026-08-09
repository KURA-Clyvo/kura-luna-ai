"""IKuraClient Protocol e KuraClient (httpx async) para a API .NET Kura."""
import logging
from typing import Protocol, runtime_checkable

import httpx

from src.config.logging_config import redigir_url_sensivel
from src.integration.dtos import (
    InteractionRequestDTO,
    TriageRequestDTO,
    TutorContextoDTO,
)
from src.integration.exceptions import KuraApiError, KuraTimeoutError

logger = logging.getLogger(__name__)


@runtime_checkable
class IKuraClient(Protocol):
    """Interface de saída para a API .NET Kura."""

    async def buscar_tutor_por_telefone(self, numero: str) -> TutorContextoDTO | None:
        """Busca tutor pelo número WhatsApp. Retorna None se não encontrado (404)."""
        ...

    async def registrar_interacao(self, dto: InteractionRequestDTO) -> int:
        """Registra uma interação de canal. Retorna o id_interacao gerado."""
        ...

    async def registrar_triagem(self, dto: TriageRequestDTO) -> int:
        """Registra o resultado da triagem. Retorna o id_triagem gerado."""
        ...

    async def verificar_saude(self) -> bool:
        """Verifica se a API Kura está respondendo (GET /health). Nunca levanta."""
        ...


class KuraClient:
    """Implementação concreta de IKuraClient usando httpx.AsyncClient.

    O httpx.AsyncClient é injetado pelo chamador (composition root ou DI do FastAPI),
    permitindo que testes substituam o transporte via respx sem subclassar.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._client = http_client

    # ── helpers ──────────────────────────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        # TASK-68: os 3 endpoints consumidos pela Luna (tutores/telefone,
        # luna/interactions, luna/triage) são autenticados por API Key server-
        # a-servidor via LunaApiKeyAuthFilter (backend-clinica-dotnet), não por
        # JWT — o header exigido é X-Api-Key, não Authorization: Bearer.
        return {"X-Api-Key": self._api_key}

    def _handle_error_status(self, response: httpx.Response) -> None:
        """Levanta KuraApiError para respostas 5xx."""
        if response.status_code >= 500:
            raise KuraApiError(response.status_code, response.text)

    def _levantar_erro_sanitizado(self, response: httpx.Response) -> None:
        """Chama `response.raise_for_status()` e, se levantar, relança com a
        URL redigida (LGPD — TASK-72 fix round 1, achado 1).

        `httpx.HTTPStatusError` embute a URL completa **como texto literal**
        na mensagem da exceção (`httpx._models.Response.raise_for_status`:
        `"{error_type} '{0.status_code} {0.reason_phrase}' for url '{0.url}'"`)
        — não como `record.args` de um log, então `RedigirUrlSensivelFilter`
        (que só opera em `LogRecord`s do logger "httpx") nunca a alcança. Uma
        das rotas que a Luna chama carrega o telefone do tutor nessa URL. Sem
        este método, um 4xx não tratado por `_handle_error_status` (que só
        cobre >=500) — por exemplo um 401 de API key mal configurada, o
        mesmo cenário que a TASK-68 corrigiu do lado do contrato — propaga a
        exceção original até `inbound_message_service.py`, onde
        `logger.exception(...)` grava o traceback completo (telefone
        incluso) no console, em `luna.log` **e** em `LOG_ERRO`
        (`LogErroRepository.from_exception` grava `str(exc)` e
        `traceback.format_exc()` na tabela).

        Centralizado aqui (em vez de remendar cada `except`/`logger.exception`
        no lado do chamador) para cobrir os 3 pontos de chamada de uma vez,
        e porque a Luna não controla o texto que o httpx gera — só pode
        interceptá-lo antes que suba. Reaproveita `KuraApiError`, o mesmo
        tipo já usado para 5xx, em vez de introduzir um tipo novo: o
        `status_code` e o corpo (aqui, a mensagem do httpx já redigida)
        continuam disponíveis para quem tratar o erro a jusante — só o
        trecho sensível da URL é removido, método/status/tipo do erro/path
        genérico continuam visíveis para diagnóstico.

        IMPORTANTE — `from None`, não `from exc`: encadear a causa
        (`raise ... from exc`) preserva `__cause__`, e `logger.exception()` /
        `traceback.format_exc()` formatam a cadeia **inteira**, reimprimindo
        `str(exc)` — a mensagem original do httpx, com o telefone cru —
        mesmo que a exceção nova já esteja sanitizada. Confirmado com um
        repro isolado antes de escrever isto (ver relatório, fix round 1,
        achado 1): com `from exc`, o texto sensível reaparece via "The above
        exception was the direct cause of the following exception"; com
        `from None`, não. `__suppress_context__` também fica `True`
        automaticamente, então nem o `__context__` implícito (que existiria
        mesmo sem `from`) reaparece.
        """
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            mensagem_sanitizada = redigir_url_sensivel(str(exc))
            raise KuraApiError(response.status_code, mensagem_sanitizada) from None

    # ── interface ─────────────────────────────────────────────────────────────

    async def buscar_tutor_por_telefone(self, numero: str) -> TutorContextoDTO | None:
        """Retorna TutorContextoDTO ou None (404). Levanta KuraApiError em 4xx/5xx."""
        try:
            resp = await self._client.get(
                f"{self._base}/api/v1/tutores/telefone/{numero}",
                headers=self._auth_headers(),
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise KuraTimeoutError() from exc

        if resp.status_code == 404:
            # TASK-68: com o endpoint agora existindo (TASK-67), 404 passa a
            # significar "tutor realmente não cadastrado" — legítimo e não
            # logado como erro. Mas registrar em INFO para que um 404 causado
            # por rota errada (regressão futura de URL) fique distinguível de
            # "tutor não encontrado" em vez de silencioso. LGPD: NUNCA logar o
            # número de telefone (mesma regra da TASK-46 em _enviar_fallback).
            logger.info("buscar_tutor_por_telefone: nenhum tutor encontrado (404)")
            return None
        self._handle_error_status(resp)
        self._levantar_erro_sanitizado(resp)
        return TutorContextoDTO.model_validate(resp.json())

    async def registrar_interacao(self, dto: InteractionRequestDTO) -> int:
        """Envia POST /api/v1/luna/interactions. Retorna id_interacao."""
        try:
            resp = await self._client.post(
                f"{self._base}/api/v1/luna/interactions",
                json=dto.model_dump(mode="json"),
                headers=self._auth_headers(),
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise KuraTimeoutError() from exc

        self._handle_error_status(resp)
        self._levantar_erro_sanitizado(resp)
        return int(resp.json()["id_interacao"])

    async def registrar_triagem(self, dto: TriageRequestDTO) -> int:
        """Envia POST /api/v1/luna/triage. Retorna id_triagem."""
        try:
            resp = await self._client.post(
                f"{self._base}/api/v1/luna/triage",
                json=dto.model_dump(mode="json"),
                headers=self._auth_headers(),
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise KuraTimeoutError() from exc

        self._handle_error_status(resp)
        self._levantar_erro_sanitizado(resp)
        return int(resp.json()["id_triagem"])

    async def verificar_saude(self) -> bool:
        """Retorna True se GET /health responder 200. Nunca propaga exceção."""
        try:
            resp = await self._client.get(
                f"{self._base}/health",
                headers=self._auth_headers(),
                timeout=self._timeout,
            )
            return resp.status_code == 200
        except Exception:
            return False
