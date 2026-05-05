"""Tests for integration DTOs and exceptions."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.integration.dtos import (
    InteractionRequestDTO,
    PetResumoDTO,
    TriageRequestDTO,
    TutorContextoDTO,
)
from src.integration.exceptions import KuraApiError, KuraAuthError, KuraNotFoundError, KuraTimeoutError


# ── DTOs ──────────────────────────────────────────────────────────────────────

class TestTutorContextoDTO:
    def test_round_trip(self) -> None:
        data = {
            "id_tutor": 1,
            "nm_tutor": "Maria",
            "ds_whatsapp": "+5511999999999",
            "id_clinica": 10,
            "pets": [{"id_pet": 5, "nm_pet": "Rex", "nm_especie": "Cão", "nm_raca": "Pastor"}],
        }
        dto = TutorContextoDTO.model_validate(data)
        assert dto.id_tutor == 1
        assert dto.pets[0].nm_raca == "Pastor"
        assert dto.model_dump()["nm_tutor"] == "Maria"

    def test_pets_default_empty(self) -> None:
        dto = TutorContextoDTO(id_tutor=1, nm_tutor="X", ds_whatsapp="+55", id_clinica=1)
        assert dto.pets == []

    def test_missing_required_raises(self) -> None:
        with pytest.raises(ValidationError):
            TutorContextoDTO.model_validate({"nm_tutor": "X"})

    def test_pet_sem_raca(self) -> None:
        pet = PetResumoDTO(id_pet=1, nm_pet="Mimi", nm_especie="Gato")
        assert pet.nm_raca is None


class TestInteractionRequestDTO:
    def test_valid_canal_whatsapp(self) -> None:
        dto = InteractionRequestDTO(
            id_tutor=1,
            ds_canal="WHATSAPP",
            ds_direcao="INBOUND",
            ds_conteudo="olá",
            dt_recebimento=datetime.now(tz=timezone.utc),
        )
        assert dto.ds_canal == "WHATSAPP"

    def test_literal_canal_invalido(self) -> None:
        with pytest.raises(ValidationError):
            InteractionRequestDTO(
                id_tutor=1,
                ds_canal="TELEGRAM",  # type: ignore[arg-type]
                ds_direcao="INBOUND",
                ds_conteudo="x",
                dt_recebimento=datetime.now(tz=timezone.utc),
            )

    def test_literal_direcao_invalida(self) -> None:
        with pytest.raises(ValidationError):
            InteractionRequestDTO(
                id_tutor=None,
                ds_canal="SMS",
                ds_direcao="LATERAL",  # type: ignore[arg-type]
                ds_conteudo="x",
                dt_recebimento=datetime.now(tz=timezone.utc),
            )

    def test_id_tutor_none_aceito(self) -> None:
        dto = InteractionRequestDTO(
            id_tutor=None,
            ds_canal="WHATSAPP",
            ds_direcao="INBOUND",
            ds_conteudo="x",
            dt_recebimento=datetime.now(tz=timezone.utc),
        )
        assert dto.id_tutor is None


class TestTriageRequestDTO:
    def test_urgencia_invalida(self) -> None:
        with pytest.raises(ValidationError):
            TriageRequestDTO(
                id_interacao=1,
                id_tutor=2,
                sintomas=[],
                ds_urgencia="CRITICA",  # type: ignore[arg-type]
                nr_score=0,
                ds_recomendacao="x",
            )

    def test_urgencias_validas(self) -> None:
        for nivel in ("BAIXA", "MEDIA", "ALTA"):
            dto = TriageRequestDTO(
                id_interacao=1,
                id_tutor=2,
                sintomas=["tosse"],
                ds_urgencia=nivel,  # type: ignore[arg-type]
                nr_score=3,
                ds_recomendacao="ok",
            )
            assert dto.ds_urgencia == nivel


# ── Exceptions ────────────────────────────────────────────────────────────────

class TestExceptions:
    def test_kura_api_error_attrs(self) -> None:
        exc = KuraApiError(500, "Internal error")
        assert exc.status_code == 500
        assert exc.body == "Internal error"
        assert "500" in str(exc)

    def test_kura_timeout_error_is_exception(self) -> None:
        exc = KuraTimeoutError("timeout")
        assert isinstance(exc, Exception)

    def test_kura_not_found_error(self) -> None:
        assert issubclass(KuraNotFoundError, Exception)

    def test_kura_auth_error(self) -> None:
        assert issubclass(KuraAuthError, Exception)
