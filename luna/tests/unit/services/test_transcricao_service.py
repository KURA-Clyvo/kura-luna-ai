"""Testes unitários para WhisperGateway e montar_soap_draft.

Cobre: transcrição via Whisper (sucesso, sem API key, erro HTTP, resposta vazia)
e a heurística de classificação SOAP por palavras-chave.
"""
import httpx
import pytest
import respx

from src.services.transcricao_service import (
    TranscricaoError,
    WhisperGateway,
    montar_soap_draft,
)

_WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"


# ── WhisperGateway ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_whisper_gateway_transcrever_sucesso() -> None:
    async with httpx.AsyncClient() as client:
        gw = WhisperGateway(api_key="sk-test", http_client=client)
        with respx.mock:
            respx.post(_WHISPER_URL).mock(
                return_value=httpx.Response(200, json={"text": "Paciente apresenta febre."})
            )
            texto = await gw.transcrever(b"audio-bytes", "consulta.mp3", "audio/mpeg")

    assert texto == "Paciente apresenta febre."


@pytest.mark.asyncio
async def test_whisper_gateway_sem_api_key_levanta_erro_sem_chamar_http() -> None:
    async with httpx.AsyncClient() as client:
        gw = WhisperGateway(api_key="", http_client=client)
        with respx.mock:
            rota = respx.post(_WHISPER_URL).mock(return_value=httpx.Response(200, json={"text": "x"}))
            with pytest.raises(TranscricaoError):
                await gw.transcrever(b"audio-bytes", "consulta.mp3", "audio/mpeg")
            assert rota.call_count == 0


@pytest.mark.asyncio
async def test_whisper_gateway_erro_http_levanta_transcricao_error() -> None:
    async with httpx.AsyncClient() as client:
        gw = WhisperGateway(api_key="sk-test", http_client=client)
        with respx.mock:
            respx.post(_WHISPER_URL).mock(
                return_value=httpx.Response(401, json={"error": "invalid_api_key"})
            )
            with pytest.raises(TranscricaoError):
                await gw.transcrever(b"audio-bytes", "consulta.mp3", "audio/mpeg")


@pytest.mark.asyncio
async def test_whisper_gateway_resposta_vazia_levanta_erro() -> None:
    async with httpx.AsyncClient() as client:
        gw = WhisperGateway(api_key="sk-test", http_client=client)
        with respx.mock:
            respx.post(_WHISPER_URL).mock(return_value=httpx.Response(200, json={"text": ""}))
            with pytest.raises(TranscricaoError):
                await gw.transcrever(b"audio-bytes", "consulta.mp3", "audio/mpeg")


# ── montar_soap_draft ─────────────────────────────────────────────────────────

def test_montar_soap_draft_classifica_plano() -> None:
    soap = montar_soap_draft("Vou prescrever amoxicilina 250mg por 7 dias.")
    assert "amoxicilina" in soap.p
    assert soap.s == ""


def test_montar_soap_draft_classifica_avaliacao() -> None:
    soap = montar_soap_draft("Suspeita de otite externa bilateral.")
    assert "otite" in soap.a


def test_montar_soap_draft_classifica_objetivo() -> None:
    soap = montar_soap_draft("Temperatura de 39.5 graus na aferição.")
    assert "39.5" in soap.o


def test_montar_soap_draft_default_subjetivo_para_frase_sem_keyword() -> None:
    soap = montar_soap_draft("Tutor relata que o animal está mais quieto que o normal.")
    assert "quieto" in soap.s
    assert soap.o == ""
    assert soap.a == ""
    assert soap.p == ""


def test_montar_soap_draft_multiplas_frases_distribuidas() -> None:
    texto = (
        "Tutor relata apatia há dois dias. "
        "Temperatura de 39.8 graus, mucosas normocoradas. "
        "Suspeita de piometra. "
        "Encaminhar para ultrassom e prescrever antibiótico."
    )
    soap = montar_soap_draft(texto)
    assert "apatia" in soap.s
    assert "39.8" in soap.o
    assert "piometra" in soap.a
    assert "ultrassom" in soap.p


def test_montar_soap_draft_texto_vazio_retorna_buckets_vazios() -> None:
    soap = montar_soap_draft("")
    assert soap.s == soap.o == soap.a == soap.p == ""
