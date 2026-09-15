"""Repository para leitura de VW_VACINAS_VENCENDO (view v2 — V21/LU-02)."""
import logging
from datetime import date

from src.db.connection import OracleConnectionPool
from src.db.models.vacina_vencendo import VacinaVencendo

logger = logging.getLogger(__name__)

# Colunas lidas por NOME (não por posição) via cursor.description — LU-03.
# `ST_CONSENTE_LEMBRETE='S'` filtra no próprio SQL (D-L4): a view devolve
# 'N' quando não há tutor vinculado (ramo AGENDAMENTO sem tutor), então essa
# linha nunca atravessa este filtro — elimina de raiz o `int(None)` que
# derrubava o job (achado da revisão do LU-02, lu-02-revisao.md frente 5/7).
_SQL_LISTAR_ELEGIVEIS = (
    "SELECT ID_PET, NM_PET, ID_TUTOR, NM_TUTOR, DS_WHATSAPP, NM_VACINA,"
    " DT_PROXIMA_DOSE, DIAS_RESTANTES, NM_CLINICA, ID_CLINICA"
    " FROM VW_VACINAS_VENCENDO"
    " WHERE DIAS_RESTANTES <= :dias"
    "   AND ST_CONSENTE_LEMBRETE = 'S'"
)

# Contagem separada das linhas SEM consentimento na mesma janela — sem ela o
# resumo não tem como contabilizar `sem_consentimento` (o SQL acima já as
# filtrou fora). Mesma janela de DIAS_RESTANTES do SQL principal.
_SQL_CONTAR_SEM_CONSENTIMENTO = (
    "SELECT COUNT(*) FROM VW_VACINAS_VENCENDO"
    " WHERE DIAS_RESTANTES <= :dias"
    "   AND ST_CONSENTE_LEMBRETE = 'N'"
)


class VacinaRepository:
    """Lê vacinas próximas do vencimento via VW_VACINAS_VENCENDO (v2)."""

    def __init__(self, pool: OracleConnectionPool) -> None:
        self._pool = pool

    def listar_vencendo_em(self, dias: int = 30) -> list[VacinaVencendo]:
        """Retorna vacinas com DIAS_RESTANTES <= dias, só de tutores que consentem."""
        with self._pool.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(_SQL_LISTAR_ELEGIVEIS, {"dias": dias})
                colunas = [c[0] for c in cursor.description]
                linhas = [dict(zip(colunas, row)) for row in cursor.fetchall()]

        resultado: list[VacinaVencendo] = []
        for linha in linhas:
            id_tutor = linha["ID_TUTOR"]
            if id_tutor is None:
                # Defesa em profundidade: com o filtro ST_CONSENTE_LEMBRETE='S'
                # acima, uma linha sem tutor não deveria chegar aqui (a view só
                # devolve 'S' quando existe um ID_TUTOR real casando com
                # CONSENTIMENTO). Se isso mudar no futuro (regressão de view),
                # descartar em vez de `int(None)` — TypeError que derrubava o
                # job inteiro (achado LU-03/lu-02-revisao.md).
                logger.warning(
                    "VacinaRepository.listar_vencendo_em: linha com ID_TUTOR nulo "
                    "apesar do filtro ST_CONSENTE_LEMBRETE='S' -- descartada "
                    "(id_pet=%s)",
                    linha.get("ID_PET"),
                )
                continue

            dt_proxima_dose = linha["DT_PROXIMA_DOSE"]
            ds_whatsapp = linha["DS_WHATSAPP"]

            resultado.append(
                VacinaVencendo(
                    id_pet=int(linha["ID_PET"]),
                    nm_pet=str(linha["NM_PET"]),
                    id_tutor=int(id_tutor),
                    nm_tutor=str(linha["NM_TUTOR"]) if linha["NM_TUTOR"] is not None else "",
                    ds_whatsapp=str(ds_whatsapp) if ds_whatsapp is not None else None,
                    nm_vacina=str(linha["NM_VACINA"]),
                    dt_proxima_dose=(
                        dt_proxima_dose
                        if isinstance(dt_proxima_dose, date)
                        else dt_proxima_dose.date()
                    ),
                    dias_restantes=int(linha["DIAS_RESTANTES"]),
                    nm_clinica=str(linha["NM_CLINICA"]),
                    id_clinica=int(linha["ID_CLINICA"]),
                )
            )
        return resultado

    def contar_sem_consentimento(self, dias: int = 30) -> int:
        """Conta linhas da mesma janela cujo tutor NÃO consente (ST_CONSENTE_LEMBRETE='N')."""
        with self._pool.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(_SQL_CONTAR_SEM_CONSENTIMENTO, {"dias": dias})
                row = cursor.fetchone()
        return int(row[0]) if row else 0
