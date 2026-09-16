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
    """Payload para registrar uma triagem.

    `regras_versao` (LU-07 item 3): versão do `TRIAGE_RULES_VERSION` que
    classificou esta mensagem — consumida pelo `.NET` (LU-08). Confirmado por
    leitura (2026-09-13) que o `.NET` ignora propriedade JSON desconhecida:
    `backend-clinica-dotnet/src/Kura.Api/Program.cs:30` registra
    `AddControllers()` sem nenhum `AddJsonOptions(...)` no arquivo inteiro
    (grep confirmou) — logo vale o default do `System.Text.Json`
    (`JsonSerializerOptions.UnmappedMemberHandling = Skip`), que descarta
    campos não mapeados no DTO de destino (`TriageRequestDto.cs`) em vez de
    rejeitar a requisição. Seguro enviar o campo antes do `LU-08` mapear a
    coluna do lado dele.
    """

    id_interacao: int
    id_tutor: int
    sintomas: list[str]
    ds_urgencia: Literal["BAIXA", "MEDIA", "ALTA"]
    nr_score: int
    ds_recomendacao: str
    regras_versao: str


class TriageResponseDTO(BaseModel):
    """Resposta ao registrar triagem."""

    id_triagem: int
