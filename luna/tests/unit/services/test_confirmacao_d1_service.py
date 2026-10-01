"""Testes do ConfirmacaoD1Service (REC-16)."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integration.dtos import ConfirmacaoPendenteItemDTO
from src.integration.exceptions import KuraApiError
from src.messaging.twilio_client import MessagingError, StatusMensagem
from src.services.confirmacao_d1_service import ConfirmacaoD1Service
from src.services.pendencia_confirmacao_store import PendenciaConfirmacaoStore


def _candidato(
    id_agendamento: int = 1,
    id_tutor: int = 7,
    ds_whatsapp: str = "+5511999999999",
) -> ConfirmacaoPendenteItemDTO:
    return ConfirmacaoPendenteItemDTO(
        id_agendamento=id_agendamento,
        id_clinica=1,
        id_tutor=id_tutor,
        ds_whatsapp=ds_whatsapp,
        nm_tutor="João",
        nm_pet="Rex",
        dt_agendamento=datetime(2026, 10, 2, 14, 30, tzinfo=UTC),
        ds_servico="Consulta",
    )


@pytest.fixture
def kura_client() -> AsyncMock:
    client = AsyncMock()
    client.buscar_confirmacao_pendente.return_value = [_candidato()]
    return client


@pytest.fixture
def twilio_gateway() -> MagicMock:
    gw = MagicMock()
    gw.enviar_whatsapp.return_value = "SMtest123"
    gw.consultar_status.return_value = StatusMensagem(status="delivered")
    return gw


@pytest.fixture
def store() -> PendenciaConfirmacaoStore:
    return PendenciaConfirmacaoStore()


@pytest.fixture
def log_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(
    kura_client: AsyncMock,
    twilio_gateway: MagicMock,
    store: PendenciaConfirmacaoStore,
    log_repo: MagicMock,
) -> ConfirmacaoD1Service:
    return ConfirmacaoD1Service(kura_client, twilio_gateway, store, log_repo)


def _sem_sleep():
    """Patch de asyncio.sleep no módulo do serviço -- as mordidas não precisam
    esperar os intervalos reais de polling do G0 item 10."""
    return patch("src.services.confirmacao_d1_service.asyncio.sleep", new=AsyncMock())


# ── caminho feliz ────────────────────────────────────────────────────────────

async def test_envia_mensagem_confirma_status_e_marca_enviado(
    service: ConfirmacaoD1Service,
    kura_client: AsyncMock,
    twilio_gateway: MagicMock,
) -> None:
    with _sem_sleep():
        resumo = await service.executar()

    assert resumo.total == 1
    assert resumo.enviadas == 1
    assert resumo.falhas == 0
    twilio_gateway.enviar_whatsapp.assert_called_once()
    kura_client.marcar_lembrete_enviado.assert_awaited_once_with(1)


async def test_registra_pendencia_apos_envio_confirmado(
    service: ConfirmacaoD1Service, store: PendenciaConfirmacaoStore
) -> None:
    with _sem_sleep():
        await service.executar()

    pendencia = store.buscar("5511999999999")
    assert pendencia is not None
    assert pendencia.id_agendamento == 1
    assert pendencia.id_tutor == 7


# ── G2 achado D — chave do store simétrica com o que o webhook produz ──────

@pytest.mark.parametrize(
    "ds_whatsapp",
    [
        "+5511999999999",  # E.164 (o que o .NET manda hoje, A-12)
        "5511999999999",  # DDI sem "+"
        "11999999999",  # nacional, sem DDI -- formato legado medido no Oracle
    ],
)
async def test_chave_da_pendencia_sempre_bate_com_a_chave_do_webhook(
    kura_client: AsyncMock,
    twilio_gateway: MagicMock,
    store: PendenciaConfirmacaoStore,
    log_repo: MagicMock,
    ds_whatsapp: str,
) -> None:
    """G2 achado D (Important): independente do formato de `DS_WHATSAPP`
    (E.164, com DDI sem '+', ou nacional sem DDI -- os 3 que coexistem de
    verdade no Oracle, ver comentário em `twilio_client.py`), a chave gravada
    pelo job tem que casar com a chave que `parse_inbound_payload` produz a
    partir do `From` do Twilio (sempre E.164 com DDI)."""
    from src.messaging.twilio_inbound import parse_inbound_payload

    kura_client.buscar_confirmacao_pendente.return_value = [
        _candidato(ds_whatsapp=ds_whatsapp)
    ]
    service = ConfirmacaoD1Service(kura_client, twilio_gateway, store, log_repo)

    with _sem_sleep():
        await service.executar()

    msg = parse_inbound_payload(
        {
            "From": "whatsapp:+5511999999999",
            "Body": "1",
            "MessageSid": "SM9",
            "AccountSid": "AC1",
        }
    )
    pendencia = store.buscar(msg.numero_origem)
    assert pendencia is not None, (
        f"pendência gravada a partir de ds_whatsapp={ds_whatsapp!r} não foi "
        f"encontrada pela chave do webhook {msg.numero_origem!r}"
    )
    assert pendencia.id_agendamento == 1


# ── G0 item 10 — status real antes de marcar enviado ────────────────────────

async def test_status_queued_apos_tentativas_nao_marca_enviado(
    service: ConfirmacaoD1Service, kura_client: AsyncMock, twilio_gateway: MagicMock
) -> None:
    """'201 queued' não é entrega -- se o status nunca sai de queued/accepted
    depois de todas as tentativas, NÃO chama marcar_lembrete_enviado."""
    twilio_gateway.consultar_status.return_value = StatusMensagem(status="queued")

    with _sem_sleep():
        resumo = await service.executar()

    assert resumo.enviadas == 0
    assert resumo.falhas == 1
    kura_client.marcar_lembrete_enviado.assert_not_awaited()


async def test_status_failed_nao_marca_enviado_e_nao_vaza_telefone_no_log(
    service: ConfirmacaoD1Service,
    kura_client: AsyncMock,
    twilio_gateway: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    twilio_gateway.consultar_status.return_value = StatusMensagem(
        status="failed", error_code=63016
    )

    with _sem_sleep(), caplog.at_level("WARNING"):
        resumo = await service.executar()

    assert resumo.falhas == 1
    kura_client.marcar_lembrete_enviado.assert_not_awaited()
    assert "5511999999999" not in caplog.text
    assert "63016" in caplog.text  # código de erro é seguro -- não é PII


async def test_status_eventualmente_sucesso_apos_retentativas_marca_enviado(
    service: ConfirmacaoD1Service, kura_client: AsyncMock, twilio_gateway: MagicMock
) -> None:
    twilio_gateway.consultar_status.side_effect = [
        StatusMensagem(status="queued"),
        StatusMensagem(status="sent"),
    ]

    with _sem_sleep():
        resumo = await service.executar()

    assert resumo.enviadas == 1
    kura_client.marcar_lembrete_enviado.assert_awaited_once()


# ── 2 execuções no mesmo dia (mordida do aceite literal) ────────────────────

async def test_duas_execucoes_mesmo_dia_mandam_so_1_mensagem(
    kura_client: AsyncMock,
    twilio_gateway: MagicMock,
    store: PendenciaConfirmacaoStore,
    log_repo: MagicMock,
) -> None:
    """Mordida do aceite literal: mesmo com o `.NET` devolvendo o MESMO
    candidato nas duas chamadas (pior caso -- simula a exclusão por
    DT_LEMBRETE_CONFIRMACAO ainda não ter se propagado), a defesa local
    (`PendenciaConfirmacaoStore.ja_processado_hoje`, G0 item 11) garante que o
    Twilio só é chamado 1 vez."""
    service = ConfirmacaoD1Service(kura_client, twilio_gateway, store, log_repo)

    with _sem_sleep():
        resumo1 = await service.executar()
        resumo2 = await service.executar()

    assert twilio_gateway.enviar_whatsapp.call_count == 1
    assert kura_client.marcar_lembrete_enviado.await_count == 1
    assert resumo1.enviadas == 1
    assert resumo2.enviadas == 0
    assert resumo2.ja_processadas == 1


# ── resiliência — falha por item não derruba o lote ─────────────────────────

async def test_messaging_error_no_envio_conta_como_falha_sem_derrubar_lote(
    service: ConfirmacaoD1Service,
    kura_client: AsyncMock,
    twilio_gateway: MagicMock,
    log_repo: MagicMock,
) -> None:
    twilio_gateway.enviar_whatsapp.side_effect = MessagingError("boom", codigo="30008")

    with _sem_sleep():
        resumo = await service.executar()

    assert resumo.falhas == 1
    assert resumo.enviadas == 0
    log_repo.registrar.assert_called_once()
    kura_client.marcar_lembrete_enviado.assert_not_awaited()


async def test_kura_api_error_ao_marcar_enviado_conta_como_falha(
    service: ConfirmacaoD1Service, kura_client: AsyncMock
) -> None:
    kura_client.marcar_lembrete_enviado.side_effect = KuraApiError(500, "boom")

    with _sem_sleep():
        resumo = await service.executar()

    assert resumo.falhas == 1
    assert resumo.enviadas == 0


async def test_lote_com_2_candidatos_1_falha_nao_impede_o_outro(
    kura_client: AsyncMock,
    twilio_gateway: MagicMock,
    store: PendenciaConfirmacaoStore,
    log_repo: MagicMock,
) -> None:
    kura_client.buscar_confirmacao_pendente.return_value = [
        _candidato(id_agendamento=1, ds_whatsapp="+5511111111111"),
        _candidato(id_agendamento=2, ds_whatsapp="+5522222222222"),
    ]
    twilio_gateway.enviar_whatsapp.side_effect = [
        MessagingError("boom", codigo="30008"),
        "SMok",
    ]
    service = ConfirmacaoD1Service(kura_client, twilio_gateway, store, log_repo)

    with _sem_sleep():
        resumo = await service.executar()

    assert resumo.total == 2
    assert resumo.falhas == 1
    assert resumo.enviadas == 1
