"""Repository para leitura da tabela RACA."""
from src.db.connection import OracleConnectionPool
from src.db.models.raca import Raca

_SQL = (
    "SELECT ID_RACA, NM_RACA, DS_PREDISPOSICAO, ID_ESPECIE"
    "  FROM RACA"
    " WHERE UPPER(NM_RACA) = UPPER(:nm)"
)


class RacaRepository:
    """Busca raças pelo nome (case-insensitive)."""

    def __init__(self, pool: OracleConnectionPool) -> None:
        self._pool = pool

    def buscar_por_nome(self, nm_raca: str) -> Raca | None:
        """Retorna a Raca correspondente ao nome ou None se não encontrada."""
        with self._pool.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(_SQL, {"nm": nm_raca})
                row = cursor.fetchone()

        if row is None:
            return None

        return Raca(
            id_raca=int(row[0]),
            nm_raca=str(row[1]),
            ds_predisposicao=str(row[2]) if row[2] is not None else None,
            id_especie=int(row[3]),
        )
