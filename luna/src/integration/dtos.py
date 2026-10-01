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


class ConfirmacaoPendenteItemDTO(BaseModel):
    """Item de GET /api/v1/luna/agendamentos/confirmacao-pendente (REC-16/REC-15).

    Espelha `ConfirmacaoPendenteItemDto.cs` — shape snake_case via `[JsonPropertyName]`
    explícito do lado .NET, confirmado por leitura da fonte antes de montar este DTO.
    """

    id_agendamento: int
    id_clinica: int
    id_tutor: int
    ds_whatsapp: str
    nm_tutor: str
    nm_pet: str | None = None
    dt_agendamento: datetime
    ds_servico: str | None = None


class LembreteEnviadoResponseDTO(BaseModel):
    """Resposta de POST .../lembrete-enviado (REC-16/REC-15)."""

    id_agendamento: int
    dt_lembrete_confirmacao: datetime


class RespostaConfirmacaoRequestDTO(BaseModel):
    """Payload de POST .../resposta-confirmacao (REC-16/REC-15)."""

    id_tutor: int
    resposta: Literal["SIM", "CANCELAR", "REMARCAR"]


class RespostaConfirmacaoResponseDTO(BaseModel):
    """Resposta de POST .../resposta-confirmacao (REC-16/REC-15)."""

    id_agendamento: int
    ds_status: str
    ds_resposta_confirmacao: str | None = None
