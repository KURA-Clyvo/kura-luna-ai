"""Teste E2E do fluxo inbound WhatsApp.

IO real: TriageEngine (Python puro).
IO mockado: Oracle (log_repo), Twilio outbound (gateway), API .NET (respx).
"""
import time

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

_KURA_BASE = "http://kura-e2e.local"

_FORM_ALTA = {
    "From": "whatsapp:+5511999000001",
    "Body": "socorro meu cachorro está convulsionando",
    "MessageSid": "SM_alta_001",
    "AccountSid": "ACtest",
}

_FORM_DESCONHECIDO = {
    "From": "whatsapp:+5511999000002",
    "Body": "boa tarde queria uma informação",
    "MessageSid": "SM_desc_001",
    "AccountSid": "ACtest",
}

_FORM_NET_DOWN = {
    "From": "whatsapp:+5511999000003",
    "Body": "meu pet não está bem",
    "MessageSid": "SM_down_001",
    "AccountSid": "ACtest",
}

_TUTOR_PAYLOAD = {
    "id_tutor": 42,
    "nm_tutor": "Carlos",
    "ds_whatsapp": "+5511999000001",
    "id_clinica": 1,
    "pets": [{"id_pet": 7, "nm_pet": "Rex", "nm_especie": "Cão", "nm_raca": "Pastor"}],
}


# ── Cenário 1: tutor encontrado, mensagem de ALTA urgência ───────────────────

@respx.mock
def test_cenario_alta_urgencia(
    e2e_client: TestClient,
    mock_twilio_gateway,
    mock_log_repo_e2e,
) -> None:
    """
    DADO tutor cadastrado enviando mensagem de convulsão,
    QUANDO POST /webhook/twilio/whatsapp,
    ENTÃO: interação enviada, triagem ALTA enviada, Twilio recebe texto de urgência.
    """
    # Mocks da API .NET
    respx.get(f"{_KURA_BASE}/api/v1/tutores/telefone/5511999000001").mock(
        return_value=httpx.Response(200, json=_TUTOR_PAYLOAD)
    )
    interaction_route = respx.post(f"{_KURA_BASE}/api/v1/luna/interactions").mock(
        return_value=httpx.Response(201, json={"id_interacao": 100})
    )
    triage_route = respx.post(f"{_KURA_BASE}/api/v1/luna/triage").mock(
        return_value=httpx.Response(201, json={"id_triagem": 200})
    )

    resp = e2e_client.post("/webhook/twilio/whatsapp", data=_FORM_ALTA)

    assert resp.status_code == 200
    assert "<Response>" in resp.text or resp.text == "<Response></Response>"

    # Interação registrada com tutor correto
    assert interaction_route.called
    interaction_body = interaction_route.calls[0].request.read()
    assert b'"id_tutor": 42' in interaction_body or b'"id_tutor":42' in interaction_body

    # Triagem registrada com urgência ALTA
    assert triage_route.called
    triage_body = triage_route.calls[0].request.read()
    assert b"ALTA" in triage_body

    # Twilio recebe texto de urgência
    mock_twilio_gateway.enviar_whatsapp.assert_called_once()
    _, mensagem = mock_twilio_gateway.enviar_whatsapp.call_args[0]
    assert "urgente" in mensagem.lower() or "veterinário" in mensagem.lower()


# ── Cenário 2: tutor desconhecido (404 no .NET) ───────────────────────────────

@respx.mock
def test_cenario_tutor_desconhecido(
    e2e_client: TestClient,
    mock_twilio_gateway,
    mock_log_repo_e2e,
) -> None:
    """
    DADO número não cadastrado (404 na API .NET),
    QUANDO POST /webhook/twilio/whatsapp,
    ENTÃO: interação com id_tutor=None, SEM chamada a /triage, fallback Twilio,
    e (TASK-78) SEM gravar em LOG_ERRO — o /interactions responde 201 (não mais
    422) para id_tutor=null desde a TASK-77 (.NET, INTERACAO_CANAL.ID_CLINICA
    nullable via V16), então o handler genérico de `processar()` nunca é
    acionado neste caminho.

    Antes da TASK-77, esta mesma sequência (404 -> POST /interactions com
    id_tutor=null) recebia 422 do .NET, `_processar_interno` propagava
    `KuraApiError`, o `except Exception` de `processar()` capturava e chamava
    `LogErroRepository.from_exception` — um erro FALSO em LOG_ERRO para um
    caso que não é erro (tutor desconhecido é esperado). Ver
    `test_cenario_tutor_desconhecido_regressao_pre_task77_grava_log_erro`
    logo abaixo: mesma sequência, só trocando a resposta mockada de
    /interactions para 422, reproduz esse sintoma antigo E prova que a
    asserção `assert_not_called()` abaixo não é vácua — ela morde se o
    contrato regredir.
    """
    respx.get(f"{_KURA_BASE}/api/v1/tutores/telefone/5511999000002").mock(
        return_value=httpx.Response(404)
    )
    interaction_route = respx.post(f"{_KURA_BASE}/api/v1/luna/interactions").mock(
        return_value=httpx.Response(201, json={"id_interacao": 101})
    )
    triage_route = respx.post(f"{_KURA_BASE}/api/v1/luna/triage").mock(
        return_value=httpx.Response(201, json={"id_triagem": 999})
    )

    resp = e2e_client.post("/webhook/twilio/whatsapp", data=_FORM_DESCONHECIDO)

    assert resp.status_code == 200

    # Interação registrada com id_tutor null
    assert interaction_route.called
    interaction_body = interaction_route.calls[0].request.read()
    assert b'"id_tutor": null' in interaction_body or b'"id_tutor":null' in interaction_body

    # Sem chamada a /triage
    assert not triage_route.called

    # TASK-78: sem gravação em LOG_ERRO — o caminho completo (404 -> 201 com
    # id_tutor null) não passa pelo `except Exception` genérico de
    # `processar()`, que é o único chamador de `LogErroRepository` nesta rota.
    mock_log_repo_e2e.registrar.assert_not_called()

    # Twilio recebe fallback educado
    mock_twilio_gateway.enviar_whatsapp.assert_called_once()
    _, mensagem = mock_twilio_gateway.enviar_whatsapp.call_args[0]
    assert "retornaremos" in mensagem.lower() or "recebemos" in mensagem.lower()


@respx.mock
def test_cenario_tutor_desconhecido_regressao_pre_task77_grava_log_erro(
    e2e_client: TestClient,
    mock_twilio_gateway,
    mock_log_repo_e2e,
) -> None:
    """TASK-78 — prova de mordida (não teste vácuo): reproduz o comportamento
    do `.NET` ANTES da TASK-77 (422 para `POST /luna/interactions` com
    `id_tutor=null`) para provar que o teste acima teria detectado a
    regressão que a TASK-78 fecha, em vez de passar por acidente.

    Sequência idêntica ao cenário 2 (mesmo 404 em /tutores/telefone, mesmo
    fluxo), só o mock de /interactions muda de 201 para 422. Resultado
    esperado — e que ERA o sintoma real, documentado em
    `luna/docs/api_contracts.md` antes desta task —: `_processar_interno`
    propaga a exceção HTTP, o `except Exception` genérico de `processar()`
    a captura, chama `LogErroRepository.from_exception` (grava em LOG_ERRO
    um erro que não é erro de verdade) e ainda assim envia o fallback ao
    tutor (nunca crasha — regra 6, resiliência).

    Este teste FICA no repo como cinto-de-segurança: se o `.NET` voltar a
    rejeitar `id_tutor=null`, é este teste (e não o cenário 2) que documenta
    por que isso é uma regressão grave (perda silenciosa de registro +
    entrada falsa em LOG_ERRO), e o cenário 2 é quem realmente falharia
    contra um `.NET` real que regredisse.
    """
    respx.get(f"{_KURA_BASE}/api/v1/tutores/telefone/5511999000002").mock(
        return_value=httpx.Response(404)
    )
    respx.post(f"{_KURA_BASE}/api/v1/luna/interactions").mock(
        return_value=httpx.Response(
            422,
            json={
                "title": "id_tutor é obrigatório para derivar id_clinica",
                "status": 422,
            },
        )
    )

    resp = e2e_client.post("/webhook/twilio/whatsapp", data=_FORM_DESCONHECIDO)

    # Nunca crasha para o Twilio — regra 6.
    assert resp.status_code == 200

    # É EXATAMENTE o sintoma que a TASK-78 fecha: erro falso gravado.
    mock_log_repo_e2e.registrar.assert_called_once()

    # Mesmo assim, fallback é enviado ao tutor.
    mock_twilio_gateway.enviar_whatsapp.assert_called_once()
    _, mensagem = mock_twilio_gateway.enviar_whatsapp.call_args[0]
    assert "retornaremos" in mensagem.lower() or "recebemos" in mensagem.lower()


# ── Cenário 3: .NET fora do ar (503) ─────────────────────────────────────────

@respx.mock
def test_cenario_net_fora_do_ar(
    e2e_client: TestClient,
    mock_twilio_gateway,
    mock_log_repo_e2e,
) -> None:
    """
    DADO API .NET retornando 503,
    QUANDO POST /webhook/twilio/whatsapp,
    ENTÃO: TwiML 200 imediato, LOG_ERRO registrado, fallback Twilio enviado.
    """
    respx.get(f"{_KURA_BASE}/api/v1/tutores/telefone/5511999000003").mock(
        return_value=httpx.Response(503, text="Service Unavailable")
    )

    resp = e2e_client.post("/webhook/twilio/whatsapp", data=_FORM_NET_DOWN)

    # TwiML respondido imediatamente
    assert resp.status_code == 200
    assert "<Response>" in resp.text or resp.text == "<Response></Response>"

    # Erro registrado no LOG_ERRO (fail-safe)
    mock_log_repo_e2e.registrar.assert_called()

    # Fallback enviado ao tutor
    mock_twilio_gateway.enviar_whatsapp.assert_called_once()
    _, mensagem = mock_twilio_gateway.enviar_whatsapp.call_args[0]
    assert "retornaremos" in mensagem.lower() or "recebemos" in mensagem.lower()


# ── Tempo total < 3s ──────────────────────────────────────────────────────────

@respx.mock
def test_tres_cenarios_em_menos_de_3s(
    e2e_client: TestClient,
    mock_twilio_gateway,
    mock_log_repo_e2e,
) -> None:
    """Verifica que todos os cenários completam em tempo aceitável."""
    # Setup mocks genéricos
    respx.get(url__regex=r"/api/v1/tutores/.*").mock(return_value=httpx.Response(200, json=_TUTOR_PAYLOAD))
    respx.post(f"{_KURA_BASE}/api/v1/luna/interactions").mock(
        return_value=httpx.Response(201, json={"id_interacao": 1})
    )
    respx.post(f"{_KURA_BASE}/api/v1/luna/triage").mock(
        return_value=httpx.Response(201, json={"id_triagem": 1})
    )

    start = time.perf_counter()
    for form in [_FORM_ALTA, _FORM_DESCONHECIDO]:
        e2e_client.post("/webhook/twilio/whatsapp", data=form)
    elapsed = time.perf_counter() - start

    assert elapsed < 3.0, f"Cenários levaram {elapsed:.2f}s (máximo: 3s)"
