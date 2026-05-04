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
        except Exception:
            logger.exception(
                "LogErroRepository falhou ao gravar em LOG_ERRO — "
                "procedure=%s codigo=%d mensagem=%s",
                nm_procedure,
                codigo,
                mensagem,
            )

    @classmethod
    def from_exception(
        cls,
        repo: "LogErroRepository",
        nm_procedure: str,
        exc: BaseException,
        parametros: str | None = None,
    ) -> None:
        """Helper: registra uma exceção com stack trace completo."""
        repo.registrar(
            nm_procedure=nm_procedure,
            codigo=getattr(exc, "errno", -1) or -1,
            mensagem=str(exc),
            parametros=parametros,
            stack_trace=traceback.format_exc(),
        )
