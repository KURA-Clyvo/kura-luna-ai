"""
Teste de integração E2E — moca APENAS Oracle e Twilio.
Código real: VacinaRepository, NotificacaoRepository, LogErroRepository,
             TwilioGateway, LembreteVacinaService.

Cenário: 3 vacinas, 2 enviadas com sucesso, 1 falha no Twilio.
Meta: < 2 segundos de execução.
"""
import time
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from twilio.base.exceptions import TwilioRestException

from src.db.connection import OracleConnectionPool
from src.db.repositories.log_erro_repo import LogErroRepository
from src.db.repositories.notificacao_repo import NotificacaoRepository
from src.db.repositories.vacina_repo import VacinaRepository
from src.messaging.twilio_client import TwilioGateway
from src.services.notification_service import LembreteVacinaService

# ---- helpers ------------------------------------------------------------


def _vacina_row(
    id_pet: int,
    nm_pet: str,
    id_tutor: int,
    nm_tutor: str,
    whatsapp: str,
    nm_vacina: str,
    dias: int,
) -> tuple:
    return (id_pet, nm_pet, id_tutor, nm_tutor, whatsapp, nm_vacina, date(2026, 6, 1), dias, "Clínica Kura")


def _make_var(id_val: int) -> MagicMock:
    var = MagicMock()
    var.getvalue.return_value = id_val
    return var


# ---- fixtures -----------------------------------------------------------


@pytest.fixture
def mock_cursor() -> MagicMock:
    """Cursor Oracle pré-configurado para o cenário de 3 vacinas."""
    cursor = MagicMock()

    # 1 × listar_vencendo_em → fetchall → 3 vacinas
    cursor.fetchall.return_value = [
        _vacina_row(1, "Rex",  10, "João",  "11987650001", "Antirrábica", 5),
        _vacina_row(2, "Mel",  20, "Maria", "11987650002", "V10",          3),
        _vacina_row(3, "Thor", 30, "Pedro", "11987650003", "Gripe",        1),
    ]

    # 3 × existe_pendente_para_vacina → fetchone → (0,) = nenhuma pendente
    cursor.fetchone.side_effect = [(0,), (0,), (0,)]

    # 3 × criar → cursor.var(NUMBER) → IDs sequenciais
    cursor.var.side_effect = [_make_var(101), _make_var(102), _make_var(103)]

    return cursor


@pytest.fixture
def mock_oracle_pool(mock_cursor: MagicMock) -> MagicMock:
    """Pool Oracle com conexão e cursor pré-configurados."""
    pool = MagicMock()
    conn = MagicMock()
    pool.acquire.return_value = conn
    conn.cursor.return_value.__enter__.return_value = mock_cursor
    return pool


@pytest.fixture
def mock_twilio_client() -> MagicMock:
    """Cliente Twilio: 2 envios ok, 3º levanta TwilioRestException."""
    msg1, msg2 = MagicMock(), MagicMock()
    msg1.sid = "SM001"
    msg2.sid = "SM002"
    exc = TwilioRestException(status=500, uri="/messages", msg="Network error", code=60001)

    client = MagicMock()
    client.messages.create.side_effect = [msg1, msg2, exc]
    return client


@pytest.fixture
def e2e(mock_oracle_pool: MagicMock, mock_cursor: MagicMock, mock_twilio_client: MagicMock):
    """Retorna (service, mock_cursor, mock_twilio_client) com código real entre os mocks."""
    with patch("oracledb.create_pool", return_value=mock_oracle_pool):
        pool = OracleConnectionPool(dsn="fake_dsn", user="fake_user", password="fake_pwd")

    with patch("src.messaging.twilio_client.Client", return_value=mock_twilio_client):
        gateway = TwilioGateway(
            account_sid="ACtest123",
            auth_token="authtoken",
            from_number="14155238886",
        )

    service = LembreteVacinaService(
        vacina_repo=VacinaRepository(pool),
        notificacao_repo=NotificacaoRepository(pool),
        twilio_gateway=gateway,
        log_repo=LogErroRepository(pool),
    )
    return service, mock_cursor, mock_twilio_client


# ---- testes -------------------------------------------------------------


def test_resumo_total_correto(e2e) -> None:
    service, _, _ = e2e
    resumo = service.executar()
    assert resumo.total == 3


def test_resumo_enviadas_correto(e2e) -> None:
    service, _, _ = e2e
    resumo = service.executar()
    assert resumo.enviadas == 2


def test_resumo_falhas_correto(e2e) -> None:
    service, _, _ = e2e
    resumo = service.executar()
    assert resumo.falhas == 1


def test_resumo_ja_enviadas_zero(e2e) -> None:
    service, _, _ = e2e
    resumo = service.executar()
    assert resumo.ja_enviadas == 0


def test_falha_no_twilio_nao_propaga_excecao(e2e) -> None:
    """Falha no 3º item não deve derrubar o lote."""
    service, _, _ = e2e
    try:
        service.executar()
    except Exception as exc:
        pytest.fail(f"Exceção inesperada propagou fora do serviço: {exc}")


def test_twilio_chamado_3_vezes(e2e) -> None:
    service, _, mock_twilio = e2e
    service.executar()
    assert mock_twilio.messages.create.call_count == 3


def test_marcar_enviada_chamado_2_vezes(e2e) -> None:
    service, mock_cur, _ = e2e
    service.executar()

    # _SQL_MARK_SENT contém "ST_STATUS = 'ENVIADA'" (com =)
    # _SQL_EXISTS_SAFE contém "ST_STATUS IN ('PENDENTE', 'ENVIADA')" — não casa com esse padrão
    enviada_calls = [
        c for c in mock_cur.execute.call_args_list
        if "ST_STATUS = 'ENVIADA'" in str(c)
    ]
    assert len(enviada_calls) == 2


def test_marcar_falha_chamado_1_vez(e2e) -> None:
    service, mock_cur, _ = e2e
    service.executar()

    falha_calls = [
        c for c in mock_cur.execute.call_args_list
        if "ST_STATUS = 'FALHA'" in str(c)
    ]
    assert len(falha_calls) == 1


def test_log_erro_inserido_para_falha_twilio(e2e) -> None:
    service, mock_cur, _ = e2e
    service.executar()

    log_calls = [
        c for c in mock_cur.execute.call_args_list
        if "LOG_ERRO" in str(c)
    ]
    assert len(log_calls) == 1


def test_notificacoes_criadas_para_todos_os_itens(e2e) -> None:
    """INSERT em NOTIFICACAO deve ocorrer 3 vezes (uma por vacina)."""
    service, mock_cur, _ = e2e
    service.executar()

    insert_calls = [
        c for c in mock_cur.execute.call_args_list
        if "SEQ_NOTIFICACAO" in str(c)
    ]
    assert len(insert_calls) == 3


def test_whatsapp_formato_correto(e2e) -> None:
    """Número enviado ao Twilio deve ter prefixo 'whatsapp:+55'."""
    service, _, mock_twilio = e2e
    service.executar()

    for call in mock_twilio.messages.create.call_args_list:
        to_arg = call.kwargs.get("to")
        if to_arg is None and len(call.args) > 2:
            to_arg = call.args[2]
        if to_arg:
            assert to_arg.startswith("whatsapp:+55"), f"Formato inválido: {to_arg}"


def test_roda_em_menos_de_2_segundos(e2e) -> None:
    service, _, _ = e2e
    inicio = time.monotonic()
    service.executar()
    elapsed = time.monotonic() - inicio
    assert elapsed < 2.0, f"Pipeline levou {elapsed:.3f}s — acima do limite de 2s"
