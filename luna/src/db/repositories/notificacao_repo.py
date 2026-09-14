"""Repository para INSERT/UPDATE na tabela NOTIFICACAO (V9 + colunas V21/LU-02).

LU-03: os 5 SQLs anteriores usavam colunas que nunca existiram
(``ST_STATUS``, ``DT_ENVIADA``, ``DT_AGENDADA``, ``ID_EVENTO``) e omitiam
``ID_CLINICA`` (NOT NULL desde a V9) — achado N1 (`ORA-00904`/`ORA-01400`,
ver `lu-02-revisao.md` frente 5). Reescritos contra o schema real.
"""
from datetime import datetime

import oracledb

from src.db.connection import OracleConnectionPool
from src.db.models.notificacao import Notificacao
from src.utils.texto import truncar_por_bytes_utf8

_TITULO_MAX_BYTES = 200
_MENSAGEM_MAX_BYTES = 500
_ERRO_MAX_BYTES = 500

# ID_NOTIFICACAO tem DEFAULT SEQ_NOTIFICACAO.NEXTVAL desde a V12 — omitido da
# lista de colunas para não sobrescrever a sequence.
_SQL_INSERT = """
INSERT INTO NOTIFICACAO (
    ID_CLINICA, ID_TUTOR, ID_PET, DS_TITULO, DS_MENSAGEM,
    DS_CANAL, DS_TIPO, ST_ENVIO
) VALUES (
    :id_clinica, :id_tutor, :id_pet, :ds_titulo, :ds_mensagem,
    :ds_canal, :ds_tipo, :st_status
) RETURNING ID_NOTIFICACAO INTO :out_id
"""

_SQL_MARK_SENT = """
UPDATE NOTIFICACAO
   SET ST_ENVIO = 'ENVIADA', DT_ENVIO = :dt_enviada
 WHERE ID_NOTIFICACAO = :id_notificacao
"""

_SQL_MARK_FAIL = """
UPDATE NOTIFICACAO
   SET ST_ENVIO = 'FALHA', DS_ERRO_ENVIO = :ds_erro
 WHERE ID_NOTIFICACAO = :id_notificacao
"""

# Idempotência (N1c): o intervalo usa NUMTODSINTERVAL com bind NUMÉRICO, não
# um bind dentro de literal de INTERVAL (a versão antiga, `INTERVAL ':horas'
# HOUR`, nunca substituía `:horas` — ficava um literal de texto inválido,
# ORA-01867). Chave de idempotência inclui ID_TUTOR (a view faz fan-out por
# tutor — sem ID_TUTOR o 2º tutor de um pet compartilhado seria contado como
# já enviado, ver lu-03-brief.md).
_SQL_EXISTS = """
SELECT COUNT(*)
  FROM NOTIFICACAO
 WHERE ID_TUTOR   = :id_tutor
   AND ID_PET     = :id_pet
   AND DS_TIPO    = 'LEMBRETE_VACINA'
   AND DS_TITULO  LIKE :titulo_like
   AND ST_ENVIO   IN ('PENDENTE', 'ENVIADA')
   AND DT_CRIACAO >= SYSTIMESTAMP - NUMTODSINTERVAL(:horas, 'HOUR')
"""


class NotificacaoRepository:
    """Persiste e atualiza notificações na tabela NOTIFICACAO."""

    def __init__(self, pool: OracleConnectionPool) -> None:
        self._pool = pool

    def criar(self, notif: Notificacao) -> int:
        """Insere uma nova notificação e retorna o ID gerado pela sequence.

        ``DS_TITULO``/``DS_MENSAGEM`` são truncados por BYTES UTF-8 (colunas
        Oracle dimensionadas em bytes) sem partir caractere multibyte.
        """
        ds_titulo = truncar_por_bytes_utf8(notif.ds_titulo, _TITULO_MAX_BYTES)
        ds_mensagem = truncar_por_bytes_utf8(notif.ds_mensagem, _MENSAGEM_MAX_BYTES)

        with self._pool.get_connection() as conn:
            with conn.cursor() as cursor:
                out_id = cursor.var(oracledb.NUMBER)
                cursor.execute(
                    _SQL_INSERT,
                    {
                        "id_clinica": notif.id_clinica,
                        "id_tutor": notif.id_tutor,
                        "id_pet": notif.id_pet,
                        "ds_canal": notif.ds_canal,
                        "ds_tipo": notif.ds_tipo,
                        "ds_titulo": ds_titulo,
                        "ds_mensagem": ds_mensagem,
                        "st_status": notif.st_envio,
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
        """Atualiza status para FALHA e registra a mensagem de erro (já sanitizada pelo chamador)."""
        with self._pool.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    _SQL_MARK_FAIL,
                    {
                        "ds_erro": truncar_por_bytes_utf8(msg_erro, _ERRO_MAX_BYTES),
                        "id_notificacao": id_notificacao,
                    },
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
                    _SQL_EXISTS,
                    {
                        "id_tutor": id_tutor,
                        "id_pet": id_pet,
                        "titulo_like": f"%{nm_vacina}%",
                        "horas": janela_horas,
                    },
                )
                row = cursor.fetchone()
                return bool(row and row[0] > 0)
