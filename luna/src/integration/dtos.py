"""Pydantic DTOs para os contratos REST Luna ↔ API .NET Kura."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PetResumoDTO(BaseModel):
    """Resumo de um pet vinculado a um tutor."""

    id_pet: int
    nm_pet: str
    nm_especie: str
    nm_raca: str | None = None


class TutorContextoDTO(BaseModel):
    """Contexto completo do tutor retornado pela API Kura."""

    id_tutor: int
    nm_tutor: str
    ds_whatsapp: str
    id_clinica: int
    pets: list[PetResumoDTO] = []


class InteractionRequestDTO(BaseModel):
    """Payload para registrar uma interação de canal."""

    id_tutor: int | None
    ds_canal: Literal["WHATSAPP", "EMAIL", "SMS"]
    ds_direcao: Literal["INBOUND", "OUTBOUND"]
    ds_conteudo: str
    dt_recebimento: datetime
    ds_metadados: dict | None = None  # type: ignore[type-arg]


class InteractionResponseDTO(BaseModel):
    """Resposta ao registrar interação."""

    id_interacao: int


class TriageRequestDTO(BaseModel):
    """Payload para registrar uma triagem."""

    id_interacao: int
    id_tutor: int
    sintomas: list[str]
    ds_urgencia: Literal["BAIXA", "MEDIA", "ALTA"]
    nr_score: int
    ds_recomendacao: str


class TriageResponseDTO(BaseModel):
    """Resposta ao registrar triagem."""

    id_triagem: int
