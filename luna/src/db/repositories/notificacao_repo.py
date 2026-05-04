"""Repository para INSERT/UPDATE na tabela NOTIFICACAO."""
from datetime import datetime

import oracledb

from src.db.connection import OracleConnectionPool
from src.db.models.notificacao import Notificacao

_SQL_INSERT = """
INSERT INTO NOTIFICACAO (
    ID_NOTIFICACAO, ID_TUTOR, ID_PET, ID_EVENTO,
    DS_CANAL, DS_TIPO, DS_TITULO, DS_MENSAGEM,
    DT_AGENDADA, ST_STATUS
) VALUES (
    SEQ_NOTIFICACAO.NEXTVAL, :id_tutor, :id_pet, :id_evento,
    :ds_canal, :ds_tipo, :ds_titulo, :ds_mensagem,
    :dt_agendada, :st_status
) RETURNING ID_NOTIFICACAO INTO :out_id
"""

_SQL_MARK_SENT = """
UPDATE NOTIFICACAO
   SET ST_STATUS = 'ENVIADA', DT_ENVIADA = :dt_enviada
 WHERE ID_NOTIFICACAO = :id_notificacao
"""

_SQL_MARK_FAIL = """
UPDATE NOTIFICACAO
   SET ST_STATUS = 'FALHA', DS_ERRO_ENVIO = :ds_erro
 WHERE ID_NOTIFICACAO = :id_notificacao
"""

_SQL_EXISTS = """
SELECT COUNT(*)
  FROM NOTIFICACAO
 WHERE ID_TUTOR   = :id_tutor
   AND ID_PET     = :id_pet
   AND DS_TIPO    = 'LEMBRETE_VACINA'
   AND DS_TITULO  LIKE :titulo_like
   AND ST_STATUS  IN ('PENDENTE', 'ENVIADA')
   AND DT_AGENDADA >= (SYSTIMESTAMP - INTERVAL ':horas' HOUR)
"""

_SQL_EXISTS_SAFE = (
    "SELECT COUNT(*) FROM NOTIFICACAO"
    " WHERE ID_TUTOR = :id_tutor"
    "   AND ID_PET   = :id_pet"
    "   AND DS_TIPO  = 'LEMBRETE_VACINA'"
    "   AND DS_TITULO LIKE :titulo_like"
    "   AND ST_STATUS IN ('PENDENTE', 'ENVIADA')"
    "   AND DT_AGENDADA >= SYSTIMESTAMP - :horas / 24"
)


class NotificacaoRepository:
    """Persiste e atualiza notificações na tabela NOTIFICACAO."""

    def __init__(self, pool: OracleConnectionPool) -> None:
        self._pool = pool

    def criar(self, notif: Notificacao) -> int:
        """Insere uma nova notificação e retorna o ID gerado pela sequence."""
        with self._pool.get_connection() as conn:
            with conn.cursor() as cursor:
                out_id = cursor.var(oracledb.NUMBER)
                cursor.execute(
                    _SQL_INSERT,
                    {
                        "id_tutor": notif.id_tutor,
                        "id_pet": notif.id_pet,
                        "id_evento": notif.id_evento,
                        "ds_canal": notif.ds_canal,
                        "ds_tipo": notif.ds_tipo,
                        "ds_titulo": notif.ds_titulo,
                        "ds_mensagem": notif.ds_mensagem,
                        "dt_agendada": notif.dt_agendada,
                        "st_status": notif.st_status,
                        "out_id": out_id,
                    },
                )
                conn.commit()
                return int(out_id.getvalue())

    def marcar_enviada(self, id_notificacao: int, dt_enviada: datetime) -> None:
        """Atualiza status para ENVIADA e registra timestamp de envio."""
        with self._pool.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    _SQL_MARK_SENT,
                    {"dt_enviada": dt_enviada, "id_notificacao": id_notificacao},
                )
                conn.commit()

    def marcar_falha(self, id_notificacao: int, msg_erro: str) -> None:
        """Atualiza status para FALHA e registra a mensagem de erro."""
        with self._pool.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    _SQL_MARK_FAIL,
                    {"ds_erro": msg_erro[:500], "id_notificacao": id_notificacao},
                )
                conn.commit()

    def existe_pendente_para_vacina(
        self,
        id_tutor: int,
        id_pet: int,
        nm_vacina: str,
        janela_horas: int = 24,
    ) -> bool:
        """Retorna True se já existe notificação enviada/pendente na janela indicada (idempotência)."""
        with self._pool.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    _SQL_EXISTS_SAFE,
                    {
                        "id_tutor": id_tutor,
                        "id_pet": id_pet,
                        "titulo_like": f"%{nm_vacina}%",
                        "horas": janela_horas,
                    },
                )
                row = cursor.fetchone()
                return bool(row and row[0] > 0)
