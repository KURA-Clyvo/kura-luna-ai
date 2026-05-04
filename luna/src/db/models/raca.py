"""Dataclass espelhando a tabela RACA."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Raca:
    """Representa um registro na tabela RACA."""

    id_raca: int
    nm_raca: str
    id_especie: int
    ds_predisposicao: str | None = None
