"""Repository para leitura de VW_VACINAS_VENCENDO."""
from datetime import date

from src.db.connection import OracleConnectionPool
from src.db.models.vacina_vencendo import VacinaVencendo

_SQL = "SELECT ID_PET, NM_PET, ID_TUTOR, NM_TUTOR, DS_WHATSAPP, NM_VACINA, DT_PROXIMA_DOSE, DIAS_RESTANTES, NM_CLINICA FROM VW_VACINAS_VENCENDO WHERE DIAS_RESTANTES <= :dias"


class VacinaRepository:
    """Lê vacinas próximas do vencimento via VW_VACINAS_VENCENDO."""

    def __init__(self, pool: OracleConnectionPool) -> None:
        self._pool = pool

    def listar_vencendo_em(self, dias: int = 30) -> list[VacinaVencendo]:
        """Retorna vacinas com DIAS_RESTANTES <= dias."""
        with self._pool.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(_SQL, {"dias": dias})
                rows = cursor.fetchall()

        return [
            VacinaVencendo(
                id_pet=int(row[0]),
                nm_pet=str(row[1]),
                id_tutor=int(row[2]),
                nm_tutor=str(row[3]),
                ds_whatsapp=str(row[4]),
                nm_vacina=str(row[5]),
                dt_proxima_dose=row[6] if isinstance(row[6], date) else row[6].date(),
                dias_restantes=int(row[7]),
                nm_clinica=str(row[8]),
            )
            for row in rows
        ]
