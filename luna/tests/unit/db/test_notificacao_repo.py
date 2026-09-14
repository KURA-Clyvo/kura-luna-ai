"""Tests for NotificacaoRepository."""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.db.models.notificacao import Notificacao
from src.db.repositories.notificacao_repo import NotificacaoRepository, _SQL_EXISTS


def _make_pool(cursor_mock: MagicMock) -> MagicMock:
    cursor_mock.__enter__ = lambda s: s
    cursor_mock.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = cursor_mock
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.get_connection.return_value.__enter__ = lambda s: mock_conn
    mock_pool.get_connection.return_value.__exit__ = MagicMock(return_value=False)
    return mock_pool


def _sample_notif(**kwargs) -> Notificacao:  # type: ignore[no-untyped-def]
    defaults = dict(
        id_clinica=900,
        id_tutor=1,
        id_pet=2,
        ds_canal="WHATSAPP",
        ds_tipo="LEMBRETE_VACINA",
        ds_titulo="Lembrete V10",
        ds_mensagem="Vacina vencendo",
        st_envio="PENDENTE",
    )
    defaults.update(kwargs)
    return Notificacao(**defaults)


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_criar_retorna_id_gerado(mock_oracledb: MagicMock) -> None:
    out_var = MagicMock()
    # oracledb: RETURNING INTO devolve LISTA em getvalue() -- mesmo para um
    # INSERT de 1 linha (o driver não sabe a priori quantas linhas o DML vai
    # afetar). Mordida real: `getvalue.return_value = 99.0` (escalar, forma
    # antiga deste teste) passava no mock e MESMO ASSIM `int(...)` explodia
    # contra o Oracle real do compose com `TypeError: ... not 'list'` -- só
    # apareceu na prova de mordida contra Oracle de verdade (F6), nunca no
    # mock -- `test_criar_le_getvalue_na_posicao_zero_da_lista` abaixo
    # documenta o achado.
    out_var.getvalue.return_value = [99.0]
    mock_oracledb.NUMBER = MagicMock()

    mock_cursor = MagicMock()
    mock_cursor.var.return_value = out_var

    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)
    result = repo.criar(_sample_notif())

    assert result == 99
    mock_cursor.execute.assert_called_once()


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_criar_le_getvalue_na_posicao_zero_da_lista(mock_oracledb: MagicMock) -> None:
    """Achado real contra Oracle do compose (F6, LU-03): `cursor.var(NUMBER)`
    ligado a RETURNING INTO devolve LISTA em `getvalue()`, não escalar --
    `int(out_id.getvalue())` levantava `TypeError: ... not 'list'` na
    primeira execução real de `run-job`. O mock antigo (`getvalue.
    return_value = 99.0`) nunca provava isso porque um MagicMock devolve
    exatamente o que foi configurado, nunca a semântica do driver real."""
    out_var = MagicMock()
    out_var.getvalue.return_value = [123.0]
    mock_oracledb.NUMBER = MagicMock()

    mock_cursor = MagicMock()
    mock_cursor.var.return_value = out_var

    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)
    result = repo.criar(_sample_notif())

    assert result == 123


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_criar_envia_id_clinica_no_bind(mock_oracledb: MagicMock) -> None:
    """N1 (achado LU-01/LU-02): ID_CLINICA é NOT NULL desde a V9 -- o INSERT
    anterior nunca a enviava e falharia com ORA-01400."""
    out_var = MagicMock()
    out_var.getvalue.return_value = [1.0]
    mock_oracledb.NUMBER = MagicMock()

    mock_cursor = MagicMock()
    mock_cursor.var.return_value = out_var

    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)
    repo.criar(_sample_notif(id_clinica=777))

    args = mock_cursor.execute.call_args
    assert args[0][1]["id_clinica"] == 777


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_criar_trunca_titulo_e_mensagem_por_bytes_utf8(mock_oracledb: MagicMock) -> None:
    """DS_TITULO VARCHAR2(200)/DS_MENSAGEM VARCHAR2(500) são dimensionados em
    BYTES. Usa acentuação (2 bytes/caractere em UTF-8) perto do limite para
    provar que o corte não conta caractere, e não parte multibyte."""
    out_var = MagicMock()
    out_var.getvalue.return_value = [1.0]
    mock_oracledb.NUMBER = MagicMock()

    mock_cursor = MagicMock()
    mock_cursor.var.return_value = out_var

    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)
    titulo_longo = "á" * 250  # 250 chars, 500 bytes em UTF-8 -- excede VARCHAR2(200)
    mensagem_longa = "é" * 400  # 400 chars, 800 bytes -- excede VARCHAR2(500)
    repo.criar(_sample_notif(ds_titulo=titulo_longo, ds_mensagem=mensagem_longa))

    args = mock_cursor.execute.call_args
    titulo_enviado = args[0][1]["ds_titulo"]
    mensagem_enviada = args[0][1]["ds_mensagem"]
    assert len(titulo_enviado.encode("utf-8")) <= 200
    assert len(mensagem_enviada.encode("utf-8")) <= 500
    # nenhum byte inválido -- decodificação sem erro já provou isso, mas
    # reforça que não sobrou meio-caractere:
    titulo_enviado.encode("utf-8").decode("utf-8")
    mensagem_enviada.encode("utf-8").decode("utf-8")


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_marcar_enviada_atualiza_status(mock_oracledb: MagicMock) -> None:
    mock_cursor = MagicMock()
    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)

    dt = datetime(2026, 5, 10, 8, 1)
    repo.marcar_enviada(id_notificacao=42, dt_enviada=dt)

    args = mock_cursor.execute.call_args
    assert args[0][1]["id_notificacao"] == 42
    assert args[0][1]["dt_enviada"] == dt


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_marcar_falha_trunca_erro(mock_oracledb: MagicMock) -> None:
    mock_cursor = MagicMock()
    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)

    repo.marcar_falha(id_notificacao=7, msg_erro="x" * 600)

    args = mock_cursor.execute.call_args
    assert len(args[0][1]["ds_erro"]) == 500


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_marcar_falha_trunca_erro_por_bytes_sem_partir_multibyte(mock_oracledb: MagicMock) -> None:
    mock_cursor = MagicMock()
    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)

    repo.marcar_falha(id_notificacao=7, msg_erro="ç" * 400)  # 800 bytes

    args = mock_cursor.execute.call_args
    erro_enviado = args[0][1]["ds_erro"]
    assert len(erro_enviado.encode("utf-8")) <= 500
    erro_enviado.encode("utf-8").decode("utf-8")  # não quebra


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_existe_pendente_retorna_true_quando_existe(mock_oracledb: MagicMock) -> None:
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1,)
    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)

    result = repo.existe_pendente_para_vacina(id_tutor=1, id_pet=2, nm_vacina="V10")
    assert result is True


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_existe_pendente_retorna_false_quando_nao_existe(mock_oracledb: MagicMock) -> None:
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (0,)
    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)

    result = repo.existe_pendente_para_vacina(id_tutor=1, id_pet=2, nm_vacina="V10")
    assert result is False


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_existe_pendente_bind_variable_titulo(mock_oracledb: MagicMock) -> None:
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (0,)
    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)

    repo.existe_pendente_para_vacina(id_tutor=1, id_pet=2, nm_vacina="Raiva", janela_horas=48)

    args = mock_cursor.execute.call_args
    assert args[0][1]["titulo_like"] == "%Raiva%"
    assert args[0][1]["horas"] == 48


@patch("src.db.repositories.notificacao_repo.oracledb")
def test_existe_pendente_inclui_id_tutor_na_chave(mock_oracledb: MagicMock) -> None:
    """A view faz fan-out por tutor (pet com 2 tutores): sem ID_TUTOR na
    chave, o 2º tutor de um pet compartilhado seria contado como
    já-enviado (achado registrado no lu-03-brief.md)."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (0,)
    pool = _make_pool(mock_cursor)
    repo = NotificacaoRepository(pool=pool)

    repo.existe_pendente_para_vacina(id_tutor=55, id_pet=2, nm_vacina="V10")

    args = mock_cursor.execute.call_args
    assert args[0][1]["id_tutor"] == 55


def test_sql_exists_nao_tem_bind_dentro_de_literal() -> None:
    """N1c: `INTERVAL ':horas' HOUR` nunca substituía o bind (texto literal).
    A versão corrigida usa NUMTODSINTERVAL com bind numérico fora de aspas."""
    assert "INTERVAL ':" not in _SQL_EXISTS
    assert "NUMTODSINTERVAL(:horas" in _SQL_EXISTS
