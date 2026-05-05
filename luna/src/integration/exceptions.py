"""Exceções de integração com a API .NET Kura."""


class KuraApiError(Exception):
    """Levantado em respostas 5xx da API Kura."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Kura API error {status_code}: {body}")


class KuraTimeoutError(Exception):
    """Levantado quando a chamada à API Kura excede o timeout configurado."""


class KuraNotFoundError(Exception):
    """Levantado quando um recurso não é encontrado na API Kura (404)."""


class KuraAuthError(Exception):
    """Levantado em respostas 401/403 da API Kura."""
