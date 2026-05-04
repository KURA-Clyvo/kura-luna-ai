"""Dataclass espelhando VW_VACINAS_VENCENDO."""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class VacinaVencendo:
    """Linha da view VW_VACINAS_VENCENDO — somente leitura."""

    id_pet: int
    nm_pet: str
    id_tutor: int
    nm_tutor: str
    ds_whatsapp: str
    nm_vacina: str
    dt_proxima_dose: date
    dias_restantes: int
    nm_clinica: str
