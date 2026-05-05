"""IKuraClient Protocol e KuraClient (httpx async) para a API .NET Kura."""
from typing import Protocol, runtime_checkable

import httpx

from src.integration.dtos import (
    InteractionRequestDTO,
    TriageRequestDTO,
    TutorContextoDTO,
)
from src.integration.exceptions import KuraApiError, KuraTimeoutError


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
        return {"Authorization": f"Bearer {self._api_key}"}

    def _handle_error_status(self, response: httpx.Response) -> None:
        """Levanta KuraApiError para respostas 5xx."""
        if response.status_code >= 500:
            raise KuraApiError(response.status_code, response.text)

    # ── interface ─────────────────────────────────────────────────────────────

    async def buscar_tutor_por_telefone(self, numero: str) -> TutorContextoDTO | None:
        """Retorna TutorContextoDTO ou None (404). Levanta KuraApiError em 5xx."""
        try:
            resp = await self._client.get(
                f"{self._base}/api/tutores/telefone/{numero}",
                headers=self._auth_headers(),
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise KuraTimeoutError() from exc

        if resp.status_code == 404:
            return None
        self._handle_error_status(resp)
        resp.raise_for_status()
        return TutorContextoDTO.model_validate(resp.json())

    async def registrar_interacao(self, dto: InteractionRequestDTO) -> int:
        """Envia POST /api/luna/interactions. Retorna id_interacao."""
        try:
            resp = await self._client.post(
                f"{self._base}/api/luna/interactions",
                json=dto.model_dump(mode="json"),
                headers=self._auth_headers(),
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise KuraTimeoutError() from exc

        self._handle_error_status(resp)
        resp.raise_for_status()
        return int(resp.json()["id_interacao"])

    async def registrar_triagem(self, dto: TriageRequestDTO) -> int:
        """Envia POST /api/luna/triage. Retorna id_triagem."""
        try:
            resp = await self._client.post(
                f"{self._base}/api/luna/triage",
                json=dto.model_dump(mode="json"),
                headers=self._auth_headers(),
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise KuraTimeoutError() from exc

        self._handle_error_status(resp)
        resp.raise_for_status()
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
