"""Recommender — cruza raça detectada com DS_PREDISPOSICAO do Oracle."""
from src.db.repositories.raca_repo import RacaRepository


class RecomendacaoCuidados:
    """Gera recomendação clínica baseada em predisposições da raça."""

    def __init__(self, raca_repo: RacaRepository) -> None:
        self._raca_repo = raca_repo

    def gerar(self, nm_raca: str) -> str | None:
        """Retorna texto de recomendação ou None se raça sem predisposição conhecida.

        Args:
            nm_raca: nome da raça em pt-BR (vindo do BreedClassifier).

        Returns:
            Texto clínico formatado ou None.
        """
        raca = self._raca_repo.buscar_por_nome(nm_raca)

        if raca is None or not raca.ds_predisposicao:
            return None

        return (
            f"Detectamos que seu pet é da raça *{raca.nm_raca}*. "
            f"Raças desta linhagem têm predisposição a: {raca.ds_predisposicao}. "
            f"Recomendamos uma avaliação preventiva com seu veterinário — "
            f"a detecção precoce faz toda a diferença! 🏥"
        )
