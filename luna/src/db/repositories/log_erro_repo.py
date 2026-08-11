"""Repository fail-safe para INSERT em LOG_ERRO."""
import logging
import traceback

from src.db.connection import OracleConnectionPool

logger = logging.getLogger(__name__)

_SQL = """
INSERT INTO LOG_ERRO (
    ID_LOG, NM_PROCEDURE, NM_USUARIO, NR_CODIGO_ERRO,
    DS_MENSAGEM_ERRO, DS_PARAMETROS, DS_STACK_TRACE
) VALUES (
    SEQ_LOG_ERRO.NEXTVAL, :nm_procedure, :nm_usuario, :nr_codigo,
    :ds_mensagem, :ds_parametros, :ds_stack_trace
)
"""


class LogErroRepository:
    """Persiste erros em LOG_ERRO. Nunca propaga exceções — é fail-safe."""

    def __init__(self, pool: OracleConnectionPool, nm_usuario: str = "LUNA") -> None:
        self._pool = pool
        self._nm_usuario = nm_usuario

    def registrar(
        self,
        nm_procedure: str,
        codigo: int,
        mensagem: str,
        parametros: str | None = None,
        stack_trace: str | None = None,
    ) -> None:
        """Insere um registro em LOG_ERRO. Em caso de falha, loga e retorna silenciosamente."""
        try:
            with self._pool.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        _SQL,
                        {
                            "nm_procedure": nm_procedure[:120],
                            "nm_usuario": self._nm_usuario[:60],
                            "nr_codigo": codigo,
                            "ds_mensagem": mensagem[:2000],
                            "ds_parametros": parametros[:2000] if parametros else None,
                            "ds_stack_trace": stack_trace,
                        },
                    )
                    conn.commit()
        except Exception as falha_insert:
            # TASK-85 rodada de fix 1 (Important 1 da revisão G2): este é o
            # fail-safe do PRÓPRIO sink — dispara quando o INSERT em LOG_ERRO
            # falha (Oracle fora do ar, pool esgotado). `registrar()` é
            # chamado, via `from_exception`, de DENTRO de um `except` ativo em
            # produção (ex.: `InboundMessageService.processar`) — então a
            # exceção de falha do INSERT nasce com `__context__` apontando
            # para a cadeia que motivou a chamada, PII inclusa (o mesmo
            # mecanismo de `__context__` implícito que o docstring de
            # `from_exception`, acima, descreve). `logger.exception(...)`
            # (chain=True implícito via `exc_info=True`) reimprimiria essa
            # cadeia inteira para `luna.log`, exatamente a classe de bug que
            # esta task existe para fechar — só que no sink, não na origem.
            #
            # Fix: NÃO usar `logger.exception`/`exc_info=True` aqui, e NÃO
            # relogar `mensagem` (parâmetro do chamador — pode já carregar
            # PII embutida diretamente por f-string em algum chamador futuro,
            # mesma classe do achado 5b da revisão). Em vez disso,
            # `traceback.format_exception_only(type, value)` devolve só o
            # TIPO e a MENSAGEM da falha do INSERT em si (ex.: "DPY-4011:
            # ..." / "ORA-12541: ..."), sem recursar em `__cause__`/
            # `__context__` e sem os frames do traceback — preserva o
            # diagnóstico útil (por que o INSERT falhou) sem depender de
            # nenhum chamador, presente ou futuro, ter lembrado `from None`.
            detalhe_falha_insert = "".join(
                traceback.format_exception_only(type(falha_insert), falha_insert)
            ).strip()
            logger.error(
                "LogErroRepository falhou ao gravar em LOG_ERRO — "
                "procedure=%s codigo=%d causa_falha_insert=%s",
                nm_procedure,
                codigo,
                detalhe_falha_insert,
            )

    @classmethod
    def from_exception(
        cls,
        repo: "LogErroRepository",
        nm_procedure: str,
        exc: BaseException,
        parametros: str | None = None,
    ) -> None:
        """Helper: registra uma exceção com stack trace completo.

        TASK-85 (LGPD): `chain=False` é deliberado, não um detalhe de
        formatação. `traceback.format_exc()` (chain=True, o default) reimprime
        a cadeia de causa inteira — `__cause__`/`__context__` — incluindo a
        mensagem de qualquer exceção original que tenha sido encadeada com
        `raise ... from exc` (em vez de `from None`) em algum ponto acima
        deste helper. Essa é exatamente a armadilha documentada no CLAUDE.md
        do projeto: um `from exc` esquecido em QUALQUER chamador, presente ou
        futuro, faz o texto sensível (ex.: telefone do tutor embutido pelo SDK
        do Twilio ou pela URL de uma exceção HTTP) reaparecer aqui, mesmo que
        a exceção "de fora" já esteja com a mensagem sanitizada — porque quem
        reimprime a cadeia é a formatação do traceback, não `str(exc)`.

        Este repository é o sink que grava em LOG_ERRO (tabela Oracle
        compartilhada) e é fail-safe por design — não pode depender de todo
        chamador, presente ou futuro, lembrar de usar `from None`. Cortar a
        cadeia aqui (`chain=False`) é defesa em profundidade: mantém a
        rastreabilidade do frame que efetivamente falhou (tipo, mensagem e
        stack da exceção recebida), sem herdar o que uma causa encadeada
        possa carregar. Ver `tests/unit/db/test_log_erro_repo.py::
        test_from_exception_nao_reimprime_cadeia_de_causa_com_telefone` para
        a prova de mordida (falha com `chain=True`, passa com `chain=False`).
        """
        repo.registrar(
            nm_procedure=nm_procedure,
            codigo=getattr(exc, "errno", -1) or -1,
            mensagem=str(exc),
            parametros=parametros,
            stack_trace=traceback.format_exc(chain=False),
        )
