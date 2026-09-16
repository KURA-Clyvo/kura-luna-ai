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
#
# F4-2 (lu-03-revisao.md / LU-04): 'FALHA' entrou no IN além de 'PENDENTE' e
# 'ENVIADA'. Sem isso, uma falha PERMANENTE (número inválido, credencial
# Twilio rejeitada) era reenviada E reinserida em NOTIFICACAO a cada
# execução — medido: 2º run-job no mesmo dia gerava +2 chamadas ao Twilio e
# +2 linhas para o mesmo tutor×pet×vacina, e o app do tutor mostrava
# lembretes duplicados nunca entregues (GET /tutor/notificacoes). Decisão:
# reaproveitar a JANELA (mesma de 'ENVIADA'/'PENDENTE') em vez de reaproveitar
# a LINHA (UPDATE) ou contar tentativas — é a mudança mínima que satisfaz o
# aceite ("2º disparo em FALHA ⇒ 0 linhas novas, 0 chamadas ao gateway") sem
# introduzir uma tabela/coluna de contagem de tentativas.
#
# LU-04 fix wave 1 (ruling do Felipe, 15/09): a janela que o chamador de
# produção passa (`notification_service._JANELA_IDEMPOTENCIA_HORAS`) deixou
# de ser 24h fixo e virou o período INTEIRO de antecedência do lembrete
# (168h = 7 dias) -- ver comentário em `notification_service.py`. Isso muda a
# consequência deste parágrafo: **decisão explícita -- FALHA continua elegível
# a nova tentativa (permanece no IN), mas agora só depois que os 7 dias de
# antecedência expiram** (ou seja, na prática, só na próxima vez que a mesma
# vacina entrar na janela de aviso de um novo ciclo, não no dia seguinte).
# Consequência para o tutor: uma falha PERMANENTE (número inválido) nunca é
# retentada dentro do mesmo ciclo de aviso -- consistente com "um lembrete por
# vacina" (uma tentativa, não uma entrega garantida). Uma falha TRANSIENTE
# (Twilio fora do ar por alguns minutos) também não é retentada nesse ciclo --
# é o trade-off aceito pela ruling: menos duplicata custa mais que uma
# segunda chance para uma falha rara e temporária. O parâmetro
# `janela_horas` desta função continua com default 24h só para não quebrar
# chamadores/testes que não passam o argumento explicitamente -- produção
# SEMPRE passa o valor derivado da antecedência (nunca o default).
_SQL_EXISTS = """
SELECT COUNT(*)
  FROM NOTIFICACAO
 WHERE ID_TUTOR   = :id_tutor
   AND ID_PET     = :id_pet
   AND DS_TIPO    = 'LEMBRETE_VACINA'
   AND DS_TITULO  LIKE :titulo_like
   AND ST_ENVIO   IN ('PENDENTE', 'ENVIADA', 'FALHA')
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
                # oracledb: uma variavel de bind ligada a RETURNING INTO
                # devolve LISTA em getvalue() (o DML pode, em geral, afetar
                # mais de uma linha) -- mesmo para este INSERT de 1 linha.
                # Achado real (LU-03, run-job contra Oracle do compose):
                # `int(out_id.getvalue())` levantava `TypeError: ... not
                # 'list'`; o teste unitario antigo nunca pegou porque o mock
                # de cursor.var() sempre devolvia um escalar (`getvalue.
                # return_value = 99.0`), nunca a semantica real do driver.
                return int(out_id.getvalue()[0])

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
        """Retorna True se já existe notificação enviada/pendente/falha na janela indicada (idempotência).

        F4-2: inclui `ST_ENVIO='FALHA'` de propósito — evita reenviar/reinserir
        uma falha permanente a cada execução dentro da mesma janela.

        `janela_horas` tem default 24h só para chamadores que não o
        especificam (ex.: testes deste arquivo). O chamador de produção
        (`LembreteVacinaService.executar`, LU-04 fix wave 1) SEMPRE passa o
        período inteiro de antecedência do lembrete (168h), nunca o default
        — ver comentário acima do `_SQL_EXISTS` e em `notification_service.py`.
        """
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
