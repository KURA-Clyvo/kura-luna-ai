"""Dataclass espelhando VW_VACINAS_VENCENDO (view v2 — V21/LU-02)."""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class VacinaVencendo:
    """Linha da view VW_VACINAS_VENCENDO — somente leitura.

    ``ds_whatsapp`` é opcional porque ``TUTOR.DS_WHATSAPP`` é uma coluna
    nullable: um tutor pode consentir (``ST_CONSENTE_LEMBRETE='S'``) e ainda
    assim não ter WhatsApp cadastrado. Quem consome esta linha nunca deve
    tentar enviar mensagem quando ``ds_whatsapp is None``.
    """

    id_pet: int
    nm_pet: str
    id_tutor: int
    nm_tutor: str
    ds_whatsapp: str | None
    nm_vacina: str
    dt_proxima_dose: date
    dias_restantes: int
    nm_clinica: str
    id_clinica: int
