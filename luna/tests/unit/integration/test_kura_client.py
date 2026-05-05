"""Tests for KuraClient using respx to mock httpx."""
from datetime import datetime, timezone

import httpx
import pytest
import respx

from src.integration.dtos import InteractionRequestDTO, TriageRequestDTO
from src.integration.exceptions import KuraApiError, KuraTimeoutError
from src.integration.kura_client import KuraClient

BASE = "http://kura-test.local"
API_KEY = "test-key"


@pytest.fixture
def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient()


@pytest.fixture
def client(http_client: httpx.AsyncClient) -> KuraClient:
    return KuraClient(BASE, API_KEY, timeout=5, http_client=http_client)


def _interaction_dto() -> InteractionRequestDTO:
    return InteractionRequestDTO(
        id_tutor=1,
        ds_canal="WHATSAPP",
        ds_direcao="INBOUND",
        ds_conteudo="meu pet está doente",
        dt_recebimento=datetime.now(tz=timezone.utc),
    )


def _triage_dto() -> TriageRequestDTO:
    return TriageRequestDTO(
        id_interacao=42,
        id_tutor=1,
        sintomas=["vômito"],
        ds_urgencia="MEDIA",
        nr_score=3,
        ds_recomendacao="Acompanhar",
    )


# ── buscar_tutor_por_telefone ─────────────────────────────────────────────────

@respx.mock
async def test_buscar_tutor_200(client: KuraClient) -> None:
    respx.get(f"{BASE}/api/tutores/telefone/5511999999999").mock(
        return_value=httpx.Response(
            200,
            json={
                "id_tutor": 7,
                "nm_tutor": "João",
                "ds_whatsapp": "+5511999999999",
                "id_clinica": 1,
                "pets": [],
            },
        )
    )
    tutor = await client.buscar_tutor_por_telefone("5511999999999")
    assert tutor is not None
    assert tutor.id_tutor == 7
    assert tutor.nm_tutor == "João"


@respx.mock
async def test_buscar_tutor_404_retorna_none(client: KuraClient) -> None:
    respx.get(f"{BASE}/api/tutores/telefone/000").mock(return_value=httpx.Response(404))
    result = await client.buscar_tutor_por_telefone("000")
    assert result is None


@respx.mock
async def test_buscar_tutor_500_levanta_kura_api_error(client: KuraClient) -> None:
    respx.get(f"{BASE}/api/tutores/telefone/123").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )
    with pytest.raises(KuraApiError) as exc_info:
        await client.buscar_tutor_por_telefone("123")
    assert exc_info.value.status_code == 500


@respx.mock
async def test_buscar_tutor_timeout(client: KuraClient) -> None:
    respx.get(f"{BASE}/api/tutores/telefone/999").mock(side_effect=httpx.TimeoutException("t/o"))
    with pytest.raises(KuraTimeoutError):
        await client.buscar_tutor_por_telefone("999")


# ── registrar_interacao ───────────────────────────────────────────────────────

@respx.mock
async def test_registrar_interacao_201(client: KuraClient) -> None:
    respx.post(f"{BASE}/api/luna/interactions").mock(
        return_value=httpx.Response(201, json={"id_interacao": 99})
    )
    id_interacao = await client.registrar_interacao(_interaction_dto())
    assert id_interacao == 99


@respx.mock
async def test_registrar_interacao_authorization_header(client: KuraClient) -> None:
    route = respx.post(f"{BASE}/api/luna/interactions").mock(
        return_value=httpx.Response(201, json={"id_interacao": 1})
    )
    await client.registrar_interacao(_interaction_dto())
    assert route.called
    assert route.calls[0].request.headers["Authorization"] == f"Bearer {API_KEY}"


@respx.mock
async def test_registrar_interacao_500_levanta(client: KuraClient) -> None:
    respx.post(f"{BASE}/api/luna/interactions").mock(return_value=httpx.Response(503, text="err"))
    with pytest.raises(KuraApiError) as exc_info:
        await client.registrar_interacao(_interaction_dto())
    assert exc_info.value.status_code == 503


@respx.mock
async def test_registrar_interacao_timeout(client: KuraClient) -> None:
    respx.post(f"{BASE}/api/luna/interactions").mock(side_effect=httpx.TimeoutException("t/o"))
    with pytest.raises(KuraTimeoutError):
        await client.registrar_interacao(_interaction_dto())


# ── registrar_triagem ─────────────────────────────────────────────────────────

@respx.mock
async def test_registrar_triagem_201(client: KuraClient) -> None:
    respx.post(f"{BASE}/api/luna/triage").mock(
        return_value=httpx.Response(201, json={"id_triagem": 55})
    )
    id_triagem = await client.registrar_triagem(_triage_dto())
    assert id_triagem == 55


@respx.mock
async def test_registrar_triagem_authorization_header(client: KuraClient) -> None:
    route = respx.post(f"{BASE}/api/luna/triage").mock(
        return_value=httpx.Response(201, json={"id_triagem": 1})
    )
    await client.registrar_triagem(_triage_dto())
    assert route.calls[0].request.headers["Authorization"] == f"Bearer {API_KEY}"


# ── verificar_saude ───────────────────────────────────────────────────────────

@respx.mock
async def test_verificar_saude_true(client: KuraClient) -> None:
    respx.get(f"{BASE}/health").mock(return_value=httpx.Response(200))
    assert await client.verificar_saude() is True


@respx.mock
async def test_verificar_saude_false_em_erro(client: KuraClient) -> None:
    respx.get(f"{BASE}/health").mock(side_effect=httpx.ConnectError("down"))
    assert await client.verificar_saude() is False


@respx.mock
async def test_verificar_saude_false_em_503(client: KuraClient) -> None:
    respx.get(f"{BASE}/health").mock(return_value=httpx.Response(503))
    assert await client.verificar_saude() is False
