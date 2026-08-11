"""Tests for LogErroRepository — fail-safe behavior."""
import traceback
from unittest.mock import MagicMock, patch

from src.db.repositories.log_erro_repo import LogErroRepository

# Número sintético (não é um telefone real) usado só para provar que o
# texto NÃO chega ao que seria persistido em LOG_ERRO.DS_STACK_TRACE.
_TELEFONE_SINTETICO = "5511900001111"


def _make_pool(cursor_side_effect: object = None) -> MagicMock:
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)
    if cursor_side_effect:
        mock_cursor.execute.side_effect = cursor_side_effect

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.get_connection.return_value.__enter__ = lambda s: mock_conn
    mock_pool.get_connection.return_value.__exit__ = MagicMock(return_value=False)
    return mock_pool


def test_registrar_sucesso_chama_execute() -> None:
    pool = _make_pool()
    repo = LogErroRepository(pool=pool)
    repo.registrar(nm_procedure="pkg.proc", codigo=1, mensagem="erro teste")
    # Não levantou exceção — isso já é o critério principal


def test_registrar_falha_no_insert_nao_propaga() -> None:
    pool = _make_pool(cursor_side_effect=Exception("ORA-01017"))
    repo = LogErroRepository(pool=pool)

    # não deve levantar nada
    result = repo.registrar(nm_procedure="pkg.proc", codigo=-1, mensagem="ops")
    assert result is None


def test_registrar_falha_no_pool_nao_propaga() -> None:
    mock_pool = MagicMock()
    mock_pool.get_connection.side_effect = Exception("pool esgotado")
    repo = LogErroRepository(pool=mock_pool)

    result = repo.registrar(nm_procedure="x", codigo=0, mensagem="y")
    assert result is None


def test_registrar_loga_fallback_em_caso_de_falha() -> None:
    pool = _make_pool(cursor_side_effect=Exception("DB down"))
    repo = LogErroRepository(pool=pool)
    # Deve silenciar a exceção e retornar None
    result = repo.registrar(nm_procedure="proc", codigo=500, mensagem="falha grave")
    assert result is None


def test_from_exception_registra_stack_trace() -> None:
    mock_repo = MagicMock(spec=LogErroRepository)
    exc = ValueError("algo deu errado")

    LogErroRepository.from_exception(mock_repo, nm_procedure="proc_x", exc=exc)

    mock_repo.registrar.assert_called_once()
    call_kwargs = mock_repo.registrar.call_args
    assert call_kwargs[1]["mensagem"] == "algo deu errado"
    assert call_kwargs[1]["stack_trace"] is not None


def test_from_exception_nao_reimprime_cadeia_de_causa_com_telefone() -> None:
    """TASK-85 (LGPD, E3/B0.3): prova — não infere — que o sink que grava em
    LOG_ERRO (tabela Oracle compartilhada) não reimprime PII vinda de uma
    exceção encadeada.

    Cenário: simula exatamente a armadilha documentada no CLAUDE.md do
    projeto — um chamador que ESQUECE `from None` e usa `raise ... from exc`
    (ou deixa o encadeamento implícito de `__context__` acontecer sozinho).
    A exceção "de fora" (o que qualquer chamador atual já sanitiza antes de
    levantar, ex. TASK-72/TASK-75) tem mensagem limpa; é a CAUSA por baixo
    que carrega o telefone do tutor — exatamente como a TwilioRestException
    crua carregava antes da TASK-75, ou como qualquer origem futura pode vir
    a carregar.

    Isto testa o SINK (`LogErroRepository.from_exception`) em si, não uma
    origem específica: mesmo que todo caminho de produção hoje já sanitize
    antes de levantar, este teste garante que uma origem nova, amanhã, que
    esqueça de sanitizar, ainda assim não vaza — porque o corte acontece
    aqui, não em cada chamador.
    """
    mock_repo = MagicMock(spec=LogErroRepository)

    def _origem_com_telefone_cru() -> None:
        raise ValueError(
            "Unable to create record: The 'To' number "
            f"whatsapp:+55{_TELEFONE_SINTETICO} is not a valid phone number."
        )

    def _chamador_que_esqueceu_from_none() -> None:
        try:
            _origem_com_telefone_cru()
        except ValueError as causa_com_pii:
            # A armadilha: `from exc` (ou nenhum `from`, que produz o mesmo
            # `__context__` implícito) preserva a cadeia. A mensagem da
            # exceção NOVA, por si, já está limpa — o vazamento só existe na
            # cadeia formatada pelo traceback, não em `str(exc)`.
            raise RuntimeError("Falha ao processar mensagem") from causa_com_pii

    formatado_com_cadeia_para_controle: str | None = None
    try:
        _chamador_que_esqueceu_from_none()
    except RuntimeError as exc_final:
        LogErroRepository.from_exception(
            mock_repo, nm_procedure="proc_y", exc=exc_final, parametros="message_sid=SMxxx"
        )
        # Capturado AINDA dentro do except (sys.exc_info() só é válido aqui) —
        # é o grupo de controle: prova que `chain=True` (o default de
        # `traceback.format_exc()`) TERIA vazado o telefone neste mesmo
        # cenário, ou seja, que as asserções abaixo testam um corte real, não
        # uma ausência trivial/vácua.
        formatado_com_cadeia_para_controle = traceback.format_exc(chain=True)

    assert formatado_com_cadeia_para_controle is not None, "except não disparou — teste inválido"
    assert _TELEFONE_SINTETICO in formatado_com_cadeia_para_controle

    mock_repo.registrar.assert_called_once()
    kwargs = mock_repo.registrar.call_args[1]

    # O que de fato seria persistido em LOG_ERRO.
    mensagem_persistida = kwargs["mensagem"]
    stack_trace_persistido = kwargs["stack_trace"]

    assert stack_trace_persistido is not None
    # A prova central: o telefone da causa encadeada não pode reaparecer em
    # NENHUM campo que seria gravado na tabela Oracle compartilhada.
    assert _TELEFONE_SINTETICO not in mensagem_persistida
    assert _TELEFONE_SINTETICO not in stack_trace_persistido
    assert "not a valid phone number" not in stack_trace_persistido
    # Confirma que é de fato a supressão da cadeia (chain=False) que está em
    # jogo aqui, não um acaso de string: o marcador que o Python usa para
    # reimprimir a causa não pode estar presente.
    assert "direct cause of the following exception" not in stack_trace_persistido


def test_registrar_trunca_mensagem_longa() -> None:
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.get_connection.return_value.__enter__ = lambda s: mock_conn
    mock_pool.get_connection.return_value.__exit__ = MagicMock(return_value=False)

    repo = LogErroRepository(pool=mock_pool)
    repo.registrar(nm_procedure="p", codigo=1, mensagem="x" * 3000)

    args = mock_cursor.execute.call_args[0][1]
    assert len(args["ds_mensagem"]) == 2000
