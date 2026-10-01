"""Tests for InboundMessageService."""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.messaging.twilio_inbound import InboundMessage
from src.services.inbound_message_service import (
    _ORIENTACAO_EMERGENCIA,
    _RESPOSTA_ALTA,
    _RESPOSTA_ALTA_TUTOR_DESCONHECIDO,
    _RESPOSTA_BAIXA,
    _RESPOSTA_FALLBACK,
    _RESPOSTA_MEDIA,
    InboundMessageService,
)


def _make_msg(corpo: str = "oi", numero: str = "5511999999999") -> InboundMessage:
    return InboundMessage(
        numero_origem=numero,
        corpo=corpo,
        message_sid="SMtest",
        account_sid="ACtest",
    )


def _make_tutor(id_tutor: int = 1) -> MagicMock:
    tutor = MagicMock()
    tutor.id_tutor = id_tutor
    return tutor


@pytest.fixture
def kura_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def triage_engine() -> MagicMock:
    return MagicMock()


@pytest.fixture
def twilio_gateway() -> MagicMock:
    return MagicMock()


@pytest.fixture
def log_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(
    kura_client: AsyncMock,
    triage_engine: MagicMock,
    twilio_gateway: MagicMock,
    log_repo: MagicMock,
) -> InboundMessageService:
    return InboundMessageService(kura_client, triage_engine, twilio_gateway, log_repo)


# ── caminho feliz — tutor encontrado, ALTA ────────────────────────────────────

async def test_tutor_encontrado_alta_envia_resposta_urgente(
    service: InboundMessageService,
    kura_client: AsyncMock,
    triage_engine: MagicMock,
    twilio_gateway: MagicMock,
) -> None:
    tutor = _make_tutor(7)
    kura_client.buscar_tutor_por_telefone.return_value = tutor
    kura_client.registrar_interacao.return_value = 42
    kura_client.registrar_triagem.return_value = 99

    triage_result = MagicMock()
    triage_result.urgencia = "ALTA"
    triage_result.sintomas_detectados = ["convulsão"]
    triage_result.score = 10
    triage_result.regras_versao = "1.1"
    triage_engine.classificar.return_value = triage_result

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()) as mock_thread:
        result = await service.processar(_make_msg("convulsionando"))

    assert result.urgencia == "ALTA"
    assert result.resposta_enviada == _RESPOSTA_ALTA
    assert result.id_interacao == 42
    kura_client.registrar_triagem.assert_awaited_once()
    mock_thread.assert_awaited_once()


async def test_tutor_encontrado_media_envia_resposta_media(
    service: InboundMessageService,
    kura_client: AsyncMock,
    triage_engine: MagicMock,
) -> None:
    kura_client.buscar_tutor_por_telefone.return_value = _make_tutor()
    kura_client.registrar_interacao.return_value = 1
    kura_client.registrar_triagem.return_value = 1

    triage_result = MagicMock()
    triage_result.urgencia = "MEDIA"
    triage_result.sintomas_detectados = ["vomitando"]
    triage_result.score = 3
    triage_result.regras_versao = "1.1"
    triage_engine.classificar.return_value = triage_result

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        result = await service.processar(_make_msg("vomitando"))

    assert result.resposta_enviada == _RESPOSTA_MEDIA
    # LU-07: sem regras_versao no mock, a construção do TriageRequestDTO
    # levantava ValidationError silenciosamente engolida pelo try/except de
    # telemetria (regra 6) — o teste passava sem provar que a triagem foi
    # de fato registrada. Trava isso agora.
    kura_client.registrar_triagem.assert_awaited_once()


# ── tutor desconhecido ────────────────────────────────────────────────────────

async def test_tutor_nao_encontrado_registra_interacao_sem_tutor(
    service: InboundMessageService,
    kura_client: AsyncMock,
    triage_engine: MagicMock,
    log_repo: MagicMock,
) -> None:
    kura_client.buscar_tutor_por_telefone.return_value = None
    kura_client.registrar_interacao.return_value = 5

    triage_result = MagicMock()
    triage_result.urgencia = "BAIXA"
    triage_result.sintomas_detectados = []
    triage_result.score = 0
    triage_result.regras_versao = "1.1"
    triage_engine.classificar.return_value = triage_result

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        result = await service.processar(_make_msg("oi"))

    call_args = kura_client.registrar_interacao.call_args[0][0]
    assert call_args.id_tutor is None
    # LU-07 item 4: classifica ANTES de saber se o tutor está identificado —
    # tutor desconhecido também é triado. A urgência não tem FK válida em
    # TRIAGEM_LUNA sem tutor, então vai em ds_metadados da própria interação.
    triage_engine.classificar.assert_called_once_with("oi")
    assert call_args.ds_metadados == {"urgencia": "BAIXA", "regras_versao": "1.1"}
    kura_client.registrar_triagem.assert_not_awaited()
    assert result.resposta_enviada == _RESPOSTA_BAIXA
    # TASK-78: desde que registrar_interacao() completa sem levantar (o
    # comportamento do KuraClient real desde a TASK-77 do .NET, que passou a
    # aceitar id_tutor=null com 201 em vez de 422), o `except Exception`
    # genérico de `processar()` nunca é acionado — logo LogErroRepository
    # nunca é chamado para este caminho. Neste teste de unidade
    # `kura_client` é um AsyncMock genérico (não exercita a conversão
    # HTTP->exceção do KuraClient real); a prova ponta a ponta de que o
    # cliente real de fato não levanta mais está em
    # tests/integration/test_inbound_e2e.py::test_cenario_tutor_desconhecido.
    log_repo.registrar.assert_not_called()


async def test_tutor_nao_encontrado_alta_envia_resposta_emergencia_generica(
    service: InboundMessageService,
    kura_client: AsyncMock,
    triage_engine: MagicMock,
    twilio_gateway: MagicMock,
    log_repo: MagicMock,
) -> None:
    """LU-07 item 4 — tutor desconhecido + sintoma ALTA: resposta de
    emergência GENÉRICA (sem nome de clínica, não sabemos qual é),
    registrar_triagem NUNCA chamado (sem FK válida), urgência gravada em
    ds_metadados da interação."""
    kura_client.buscar_tutor_por_telefone.return_value = None
    kura_client.registrar_interacao.return_value = 9

    triage_result = MagicMock()
    triage_result.urgencia = "ALTA"
    triage_result.sintomas_detectados = ["convulsão"]
    triage_result.score = 10
    triage_result.regras_versao = "1.1"
    triage_engine.classificar.return_value = triage_result

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()) as mock_thread:
        result = await service.processar(_make_msg("meu cachorro está convulsionando"))

    call_args = kura_client.registrar_interacao.call_args[0][0]
    assert call_args.id_tutor is None
    assert call_args.ds_metadados == {"urgencia": "ALTA", "regras_versao": "1.1"}
    kura_client.registrar_triagem.assert_not_awaited()
    assert result.urgencia == "ALTA"
    assert "imediato" in result.resposta_enviada.lower() or "pronto atendimento" in result.resposta_enviada.lower()
    assert "clínica" not in result.resposta_enviada.lower() and "clinica" not in result.resposta_enviada.lower()
    mock_thread.assert_awaited_once()
    log_repo.registrar.assert_not_called()


# ── falhas de rede ────────────────────────────────────────────────────────────

async def test_timeout_em_busca_envia_fallback(
    service: InboundMessageService,
    kura_client: AsyncMock,
    log_repo: MagicMock,
) -> None:
    from src.integration.exceptions import KuraTimeoutError

    kura_client.buscar_tutor_por_telefone.side_effect = KuraTimeoutError()

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        result = await service.processar(_make_msg())

    assert result.resposta_enviada == _RESPOSTA_FALLBACK
    log_repo.registrar.assert_called()


# ── LU-07 fix wave 1, item A6: ALTA com .NET fora do ar ────────────────────────
# Achado da G2 (lu-07-revisao.md, Frente 7): a urgência já classificada era
# descartada quando `buscar_tutor_por_telefone`/`registrar_interacao` falhavam
# depois da classificação — o tutor recebia o fallback genérico mesmo numa
# ALTA. Regra 6 do backlog: em ALTA, sempre orienta atendimento imediato.

async def test_a6_timeout_na_busca_com_alta_envia_resposta_de_emergencia(
    service: InboundMessageService,
    kura_client: AsyncMock,
    triage_engine: MagicMock,
    log_repo: MagicMock,
) -> None:
    from src.integration.exceptions import KuraTimeoutError

    triage_result = MagicMock()
    triage_result.urgencia = "ALTA"
    triage_result.sintomas_detectados = ["convulsão"]
    triage_result.score = 10
    triage_result.regras_versao = "1.1"
    triage_engine.classificar.return_value = triage_result

    kura_client.buscar_tutor_por_telefone.side_effect = KuraTimeoutError()

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()) as mock_thread:
        result = await service.processar(_make_msg("socorro meu cachorro está convulsionando"))

    assert result.urgencia == "ALTA"
    assert result.resposta_enviada == _RESPOSTA_ALTA_TUTOR_DESCONHECIDO
    assert result.resposta_enviada != _RESPOSTA_FALLBACK
    mock_thread.assert_awaited_once()
    log_repo.registrar.assert_called()


async def test_a6_falha_em_registrar_interacao_com_alta_envia_resposta_de_emergencia(
    service: InboundMessageService,
    kura_client: AsyncMock,
    triage_engine: MagicMock,
) -> None:
    """Mesma classe do teste acima, mas a falha é DEPOIS de já ter tutor
    identificado (buscar_tutor_por_telefone OK, registrar_interacao falha) —
    prova que a urgência sobrevive a qualquer ponto de falha de rede após a
    classificação, não só ao primeiro."""
    triage_result = MagicMock()
    triage_result.urgencia = "ALTA"
    triage_result.sintomas_detectados = ["convulsão"]
    triage_result.score = 10
    triage_result.regras_versao = "1.1"
    triage_engine.classificar.return_value = triage_result

    kura_client.buscar_tutor_por_telefone.return_value = _make_tutor()
    kura_client.registrar_interacao.side_effect = RuntimeError("timeout no .NET")

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        result = await service.processar(_make_msg("convulsionando"))

    assert result.urgencia == "ALTA"
    assert result.resposta_enviada == _RESPOSTA_ALTA_TUTOR_DESCONHECIDO


# ── LGPD — telefone nunca chega ao LOG_ERRO ───────────────────────────────────

async def test_excecao_generica_nao_grava_telefone_em_log_erro(
    service: InboundMessageService,
    kura_client: AsyncMock,
    log_repo: MagicMock,
) -> None:
    """TASK-35: parametros=msg.numero_origem violava LGPD (telefone cru em
    LOG_ERRO.DS_PARAMETROS). Confirma que o telefone completo nunca é
    passado ao LogErroRepository — inspeciona os argumentos da chamada
    mockada, não apenas o texto de log."""
    numero = "5511988887777"
    kura_client.buscar_tutor_por_telefone.side_effect = RuntimeError("crash")

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        await service.processar(_make_msg(numero=numero))

    log_repo.registrar.assert_called_once()
    _, kwargs = log_repo.registrar.call_args
    parametros = kwargs.get("parametros")

    assert parametros is not None
    assert numero not in parametros
    assert parametros == "message_sid=SMtest"


async def test_falha_em_registrar_triagem_nao_impede_resposta(
    service: InboundMessageService,
    kura_client: AsyncMock,
    triage_engine: MagicMock,
) -> None:
    kura_client.buscar_tutor_por_telefone.return_value = _make_tutor()
    kura_client.registrar_interacao.return_value = 1
    kura_client.registrar_triagem.side_effect = Exception("DB error")

    triage_result = MagicMock()
    triage_result.urgencia = "MEDIA"
    triage_result.sintomas_detectados = []
    triage_result.score = 3
    triage_engine.classificar.return_value = triage_result

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        result = await service.processar(_make_msg("vomitando"))

    assert result.urgencia == "MEDIA"
    assert result.resposta_enviada == _RESPOSTA_MEDIA


# ── fallback final ────────────────────────────────────────────────────────────

async def test_excecao_generica_retorna_fallback(
    service: InboundMessageService,
    kura_client: AsyncMock,
) -> None:
    kura_client.buscar_tutor_por_telefone.side_effect = RuntimeError("crash")

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        result = await service.processar(_make_msg())

    assert result.resposta_enviada == _RESPOSTA_FALLBACK
    assert result.id_interacao is None


async def test_fallback_twilio_falha_nao_propaga(
    service: InboundMessageService,
    kura_client: AsyncMock,
) -> None:
    kura_client.buscar_tutor_por_telefone.side_effect = RuntimeError("crash")

    async def twilio_erro(*_a, **_kw) -> None:
        raise OSError("Twilio offline")

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock(side_effect=twilio_erro)):
        result = await service.processar(_make_msg())

    assert result.resposta_enviada == _RESPOSTA_FALLBACK


async def test_fallback_twilio_falha_nao_loga_telefone_cru(
    kura_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """TASK-46 (versão original, SUBSTITUÍDA na TASK-75): `_enviar_fallback`
    logava o telefone cru via logger.error do log padrão da aplicação
    (destino diferente do LOG_ERRO/Oracle já corrigido na TASK-35, mesmo
    problema de LGPD).

    A versão original deste teste injetava `OSError("Twilio offline")` —
    uma string sem telefone nenhum — então `numero not in
    record.getMessage()` era vacuamente verdadeiro e nunca exercitou o
    caminho real (achado da auditoria da TASK-75). Este teste substitui o
    double genérico por uma `TwilioGateway` DE VERDADE (só
    `twilio.rest.Client`, a camada HTTP, é mockada) disparando
    `TwilioRestException` no formato real da API do Twilio para o código
    21211 ("Invalid 'To' Phone Number"), que embute o telefone completo
    em `.msg` (ver `src/messaging/twilio_client.py:47-68` e
    `tests/unit/messaging/test_twilio_client.py` para a evidência do
    formato do SDK).

    `inbound_message_service.py:139` (`logger.error("Falha ao enviar
    fallback message_sid=%s: %s", msg.message_sid, exc)`) loga o objeto
    `exc` inteiro com `%s` — a defesa contra vazamento tem que vir de
    `TwilioGateway` nunca produzir um `exc` com o telefone dentro, não
    deste logger.error. Prova de mordida: falha contra o
    `twilio_client.py` anterior à TASK-75, passa depois."""
    from twilio.base.exceptions import TwilioRestException

    from src.messaging.twilio_client import TwilioGateway

    numero = "5511988887777"
    kura_client.buscar_tutor_por_telefone.side_effect = RuntimeError("crash")

    with patch("src.messaging.twilio_client.Client") as mock_client_cls:
        mock_client_cls.return_value.messages.create.side_effect = TwilioRestException(
            status=400,
            uri="/2010-04-01/Accounts/ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/Messages.json",
            msg=(
                "Unable to create record: The 'To' number whatsapp:+55"
                f"{numero} is not a valid phone number."
            ),
            code=21211,
            method="POST",
        )
        gateway = TwilioGateway(account_sid="AC1", auth_token="tok", from_number="+14155238886")
        real_service = InboundMessageService(
            kura_client=kura_client,
            triage_engine=MagicMock(),
            twilio_gateway=gateway,
            log_repo=MagicMock(),
        )

        with caplog.at_level(logging.ERROR):
            result = await real_service.processar(_make_msg(numero=numero))

    assert result.resposta_enviada == _RESPOSTA_FALLBACK
    assert numero not in caplog.text
    assert "not a valid phone number" not in caplog.text
    fallback_records = [
        record for record in caplog.records if "Falha ao enviar fallback" in record.getMessage()
    ]
    assert fallback_records, "esperava um log de falha ao enviar fallback"
    assert "message_sid=SMtest" in fallback_records[0].getMessage()


# ── LU-07 fix wave 2, item 1: rede de segurança na resposta ───────────────────
# Ruling do Felipe (15/09): o classificador só prioriza a fila da clínica —
# TODA resposta não-ALTA carrega a orientação fixa de emergência, ALTA não
# muda e não duplica. Ver _ORIENTACAO_EMERGENCIA em inbound_message_service.py.

class TestRedeDeSeguranca:
    async def test_media_contem_orientacao(
        self,
        service: InboundMessageService,
        kura_client: AsyncMock,
        triage_engine: MagicMock,
    ) -> None:
        kura_client.buscar_tutor_por_telefone.return_value = _make_tutor()
        kura_client.registrar_interacao.return_value = 1
        kura_client.registrar_triagem.return_value = 1
        triage_result = MagicMock()
        triage_result.urgencia = "MEDIA"
        triage_result.sintomas_detectados = ["vomitando"]
        triage_result.score = 3
        triage_result.regras_versao = "1.3"
        triage_engine.classificar.return_value = triage_result

        with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
            result = await service.processar(_make_msg("vomitando"))

        assert _ORIENTACAO_EMERGENCIA in result.resposta_enviada

    async def test_baixa_contem_orientacao(
        self,
        service: InboundMessageService,
        kura_client: AsyncMock,
        triage_engine: MagicMock,
    ) -> None:
        kura_client.buscar_tutor_por_telefone.return_value = _make_tutor()
        kura_client.registrar_interacao.return_value = 1
        kura_client.registrar_triagem.return_value = 1
        triage_result = MagicMock()
        triage_result.urgencia = "BAIXA"
        triage_result.sintomas_detectados = []
        triage_result.score = 0
        triage_result.regras_versao = "1.3"
        triage_engine.classificar.return_value = triage_result

        with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
            result = await service.processar(_make_msg("oi"))

        assert _ORIENTACAO_EMERGENCIA in result.resposta_enviada

    async def test_fallback_de_rede_contem_orientacao(
        self,
        service: InboundMessageService,
        kura_client: AsyncMock,
    ) -> None:
        """Fallback de rede (urgência desconhecida, urgencia=None) também
        carrega a orientação — não é ALTA, então entra na regra geral."""
        kura_client.buscar_tutor_por_telefone.side_effect = RuntimeError("crash")

        with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
            result = await service.processar(_make_msg())

        assert result.resposta_enviada == _RESPOSTA_FALLBACK
        assert _ORIENTACAO_EMERGENCIA in result.resposta_enviada

    async def test_tutor_desconhecido_baixa_contem_orientacao(
        self,
        service: InboundMessageService,
        kura_client: AsyncMock,
        triage_engine: MagicMock,
    ) -> None:
        kura_client.buscar_tutor_por_telefone.return_value = None
        kura_client.registrar_interacao.return_value = 5
        triage_result = MagicMock()
        triage_result.urgencia = "BAIXA"
        triage_result.sintomas_detectados = []
        triage_result.score = 0
        triage_result.regras_versao = "1.3"
        triage_engine.classificar.return_value = triage_result

        with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
            result = await service.processar(_make_msg("oi"))

        assert result.resposta_enviada == _RESPOSTA_BAIXA
        assert _ORIENTACAO_EMERGENCIA in result.resposta_enviada

    async def test_alta_tutor_conhecido_nao_duplica_orientacao(
        self,
        service: InboundMessageService,
        kura_client: AsyncMock,
        triage_engine: MagicMock,
    ) -> None:
        kura_client.buscar_tutor_por_telefone.return_value = _make_tutor(7)
        kura_client.registrar_interacao.return_value = 42
        kura_client.registrar_triagem.return_value = 99
        triage_result = MagicMock()
        triage_result.urgencia = "ALTA"
        triage_result.sintomas_detectados = ["convulsão"]
        triage_result.score = 10
        triage_result.regras_versao = "1.3"
        triage_engine.classificar.return_value = triage_result

        with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
            result = await service.processar(_make_msg("convulsionando"))

        assert result.resposta_enviada == _RESPOSTA_ALTA
        assert _ORIENTACAO_EMERGENCIA not in result.resposta_enviada

    async def test_alta_tutor_desconhecido_nao_duplica_orientacao(
        self,
        service: InboundMessageService,
        kura_client: AsyncMock,
        triage_engine: MagicMock,
    ) -> None:
        kura_client.buscar_tutor_por_telefone.return_value = None
        kura_client.registrar_interacao.return_value = 9
        triage_result = MagicMock()
        triage_result.urgencia = "ALTA"
        triage_result.sintomas_detectados = ["convulsão"]
        triage_result.score = 10
        triage_result.regras_versao = "1.3"
        triage_engine.classificar.return_value = triage_result

        with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
            result = await service.processar(_make_msg("meu cachorro está convulsionando"))

        assert result.resposta_enviada == _RESPOSTA_ALTA_TUTOR_DESCONHECIDO
        assert _ORIENTACAO_EMERGENCIA not in result.resposta_enviada

    async def test_orientacao_dentro_do_limite_de_320_chars(self) -> None:
        assert len(_ORIENTACAO_EMERGENCIA) <= 320

    async def test_mensagem_final_bem_abaixo_do_limite_twilio_1600(self) -> None:
        assert len(_RESPOSTA_BAIXA) < 1600
        assert len(_RESPOSTA_MEDIA) < 1600
        assert len(_RESPOSTA_FALLBACK) < 1600


# ── REC-16 — interceptação de confirmação D-1 (A-10/a, G0 item 11) ─────────
#
# Testes isolados nesta seção porque exigem o 5º argumento opcional
# (pendencia_store) que os fixtures `service`/`kura_client`/... acima não
# passam (eles continuam cobrindo o comportamento pré-REC-16 sem o store,
# provando que o parâmetro é opcional de verdade).

from src.services.pendencia_confirmacao_store import (  # noqa: E402
    PendenciaConfirmacao,
    PendenciaConfirmacaoStore,
)


def _store_com_pendencia(
    telefone: str = "5511999999999", id_agendamento: int = 10, id_tutor: int = 7
) -> PendenciaConfirmacaoStore:
    import datetime as dt

    store = PendenciaConfirmacaoStore()
    store.registrar(
        telefone,
        PendenciaConfirmacao(
            id_agendamento=id_agendamento,
            id_tutor=id_tutor,
            expira_em=dt.datetime.now(tz=dt.UTC) + dt.timedelta(hours=1),
        ),
    )
    return store


@pytest.fixture
def service_com_store(
    kura_client: AsyncMock,
    triage_engine: MagicMock,
    twilio_gateway: MagicMock,
    log_repo: MagicMock,
) -> tuple[InboundMessageService, PendenciaConfirmacaoStore]:
    store = _store_com_pendencia()
    service = InboundMessageService(
        kura_client, triage_engine, twilio_gateway, log_repo, pendencia_store=store
    )
    return service, store


async def test_resposta_ambigua_com_pendencia_vai_para_triagem_e_recebe_emergencia(
    service_com_store: tuple[InboundMessageService, PendenciaConfirmacaoStore],
    kura_client: AsyncMock,
    triage_engine: MagicMock,
) -> None:
    """Mordida do aceite literal: 'sim, mas ele está vomitando' de um telefone
    COM lembrete pendente -- ambígua (A-10/a) -- vai para a triagem normal e
    recebe a orientação de emergência adequada à urgência classificada. NÃO é
    tratada como confirmação (nunca chama registrar_resposta_confirmacao)."""
    service, store = service_com_store
    kura_client.buscar_tutor_por_telefone.return_value = None
    kura_client.registrar_interacao.return_value = 1
    triage_result = MagicMock()
    triage_result.urgencia = "MEDIA"
    triage_result.sintomas_detectados = ["vômito"]
    triage_result.score = 3
    triage_result.regras_versao = "1.1"
    triage_engine.classificar.return_value = triage_result

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        result = await service.processar(
            _make_msg("sim, mas ele está vomitando", numero="5511999999999")
        )

    kura_client.registrar_resposta_confirmacao.assert_not_awaited()
    assert result.resposta_enviada == _RESPOSTA_MEDIA
    assert _ORIENTACAO_EMERGENCIA in result.resposta_enviada
    # ambígua -- a pendência NÃO é removida (o tutor pode responder de novo)
    assert store.buscar("5511999999999") is not None


async def test_resposta_curta_sem_pendencia_vai_para_triagem_normal(
    kura_client: AsyncMock,
    triage_engine: MagicMock,
    twilio_gateway: MagicMock,
    log_repo: MagicMock,
) -> None:
    """Mordida do aceite literal: '1' de um telefone SEM lembrete pendente vai
    para a triagem normal -- o store vazio nunca intercepta nada."""
    store = PendenciaConfirmacaoStore()
    service = InboundMessageService(
        kura_client, triage_engine, twilio_gateway, log_repo, pendencia_store=store
    )
    kura_client.buscar_tutor_por_telefone.return_value = None
    kura_client.registrar_interacao.return_value = 2
    triage_result = MagicMock()
    triage_result.urgencia = "BAIXA"
    triage_result.sintomas_detectados = []
    triage_result.score = 0
    triage_result.regras_versao = "1.1"
    triage_engine.classificar.return_value = triage_result

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        result = await service.processar(_make_msg("1", numero="5511888888888"))

    kura_client.registrar_resposta_confirmacao.assert_not_awaited()
    triage_engine.classificar.assert_called_once_with("1")
    assert result.resposta_enviada == _RESPOSTA_BAIXA


async def test_resposta_sim_reconhecida_confirma_e_nao_passa_pela_triagem(
    service_com_store: tuple[InboundMessageService, PendenciaConfirmacaoStore],
    kura_client: AsyncMock,
    triage_engine: MagicMock,
) -> None:
    service, store = service_com_store
    kura_client.registrar_resposta_confirmacao.return_value = MagicMock(
        id_agendamento=10, ds_status="CONFIRMADO", ds_resposta_confirmacao="SIM"
    )

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        result = await service.processar(_make_msg("1", numero="5511999999999"))

    kura_client.registrar_resposta_confirmacao.assert_awaited_once_with(
        id_agendamento=10, id_tutor=7, resposta="SIM"
    )
    triage_engine.classificar.assert_not_called()
    assert store.buscar("5511999999999") is None  # pendência consumida
    assert "confirmada" in result.resposta_enviada.lower()


async def test_resposta_cancelar_reconhecida_remove_pendencia(
    service_com_store: tuple[InboundMessageService, PendenciaConfirmacaoStore],
    kura_client: AsyncMock,
    triage_engine: MagicMock,
) -> None:
    service, store = service_com_store
    kura_client.registrar_resposta_confirmacao.return_value = MagicMock(
        id_agendamento=10, ds_status="CANCELADO", ds_resposta_confirmacao="CANCELAR"
    )

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        result = await service.processar(_make_msg("cancelar", numero="5511999999999"))

    kura_client.registrar_resposta_confirmacao.assert_awaited_once_with(
        id_agendamento=10, id_tutor=7, resposta="CANCELAR"
    )
    triage_engine.classificar.assert_not_called()
    assert store.buscar("5511999999999") is None
    assert "cancelado" in result.resposta_enviada.lower()


async def test_falha_ao_registrar_resposta_remove_pendencia_e_responde_generico(
    service_com_store: tuple[InboundMessageService, PendenciaConfirmacaoStore],
    kura_client: AsyncMock,
    log_repo: MagicMock,
) -> None:
    """Resposta RECONHECIDA mas o .NET rejeita (ex.: 422 -- status mudou) --
    não trava o tutor num loop: remove a pendência e responde com mensagem
    genérica, nunca o motivo técnico."""
    service, store = service_com_store
    kura_client.registrar_resposta_confirmacao.side_effect = RuntimeError("422 rejeitado")

    with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
        result = await service.processar(_make_msg("sim", numero="5511999999999"))

    assert store.buscar("5511999999999") is None
    log_repo.registrar.assert_called_once()
    assert "não conseguimos" in result.resposta_enviada.lower()


# ── G2 achado B — _tentar_confirmacao_d1 não pode escapar de processar() ───

async def test_falha_ao_enviar_confirmacao_de_sucesso_nao_escapa_e_vai_para_log_erro(
    service_com_store: tuple[InboundMessageService, PendenciaConfirmacaoStore],
    kura_client: AsyncMock,
    log_repo: MagicMock,
) -> None:
    """G2 achado B (Important): tutor manda 'sim' -> o `.NET` processa com
    sucesso (ex.: CONFIRMADO) -> o envio da mensagem de confirmação AO TUTOR
    falha (MessagingError, ex.: 63016). Antes do fix, essa exceção escapava de
    `processar()` sem log nem LOG_ERRO (achado B da G2, com controle
    positivo: o mesmo erro no fluxo normal é absorvido). Depois do fix, nunca
    propaga, e a pendência PERMANECE removida -- a ação já foi aplicada no
    `.NET`, só o aviso ao tutor falhou."""
    service, store = service_com_store
    kura_client.registrar_resposta_confirmacao.return_value = MagicMock(
        id_agendamento=10, ds_status="CONFIRMADO", ds_resposta_confirmacao="SIM"
    )

    from src.messaging.twilio_client import MessagingError

    with patch(
        "src.services.inbound_message_service.asyncio.to_thread",
        new=AsyncMock(side_effect=MessagingError("boom", codigo=63016)),
    ):
        result = await service.processar(_make_msg("sim", numero="5511999999999"))

    # não levantou -- se chegou aqui, já não escapou.
    kura_client.registrar_resposta_confirmacao.assert_awaited_once()
    log_repo.registrar.assert_called_once()
    assert store.buscar("5511999999999") is None
    assert result is not None


async def test_falha_dupla_registrar_e_notificar_falha_nao_escapa(
    service_com_store: tuple[InboundMessageService, PendenciaConfirmacaoStore],
    kura_client: AsyncMock,
    log_repo: MagicMock,
) -> None:
    """G2 achado B -- o OUTRO ramo: o `.NET` REJEITA a resposta (ex.: 422) E o
    envio da mensagem de erro genérica também falha. As duas falhas são
    logadas (uma pelo except interno de `_tentar_confirmacao_d1`, outra pelo
    except externo de `processar`), e nada escapa."""
    service, store = service_com_store
    kura_client.registrar_resposta_confirmacao.side_effect = RuntimeError("422 rejeitado")

    from src.messaging.twilio_client import MessagingError

    with patch(
        "src.services.inbound_message_service.asyncio.to_thread",
        new=AsyncMock(side_effect=MessagingError("boom", codigo="30008")),
    ):
        result = await service.processar(_make_msg("sim", numero="5511999999999"))

    assert result is not None
    assert store.buscar("5511999999999") is None
    assert log_repo.registrar.call_count >= 2


# ── LGPD — telefone nunca cru em log nem em LOG_ERRO (REC-16) ──────────────

async def test_falha_ao_registrar_resposta_nao_vaza_telefone_no_log(
    kura_client: AsyncMock,
    triage_engine: MagicMock,
    twilio_gateway: MagicMock,
    log_repo: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Controle positivo incluído: um `logger.warning` SIBLING que embute o
    telefone de propósito (`_marcador_controle_positivo`, fora do código de
    produção) prova que `caplog`/`log_repo.registrar` ENXERGARIAM o telefone
    se ele vazasse -- sem esse controle, "telefone ausente" seria
    indistinguível de "caplog não captura nada daqui"."""
    numero = "5511977776666"
    store = _store_com_pendencia(telefone=numero, id_agendamento=20, id_tutor=9)
    service = InboundMessageService(
        kura_client, triage_engine, twilio_gateway, log_repo, pendencia_store=store
    )
    kura_client.registrar_resposta_confirmacao.side_effect = RuntimeError(
        "falha simulada sem telefone"
    )

    with caplog.at_level("WARNING"):
        # controle positivo: prova que caplog ENXERGARIA o número se um
        # chamador (presente ou futuro) o embutisse num log -- sem isto, um
        # `assert numero not in caplog.text` que desse certo por caplog estar
        # vazio por outro motivo passaria despercebido.
        logging.getLogger("tests.controle_positivo_rec16").warning(
            "sonda de controle positivo com telefone %s", numero
        )
        assert numero in caplog.text, "controle positivo falhou -- caplog não captura texto"
        caplog.clear()

        with patch("src.services.inbound_message_service.asyncio.to_thread", new=AsyncMock()):
            await service.processar(_make_msg("cancelar", numero=numero))

    assert numero not in caplog.text, f"telefone vazou no log: {caplog.text!r}"
    for chamada in log_repo.registrar.call_args_list:
        _, kwargs = chamada
        texto_registrado = str(kwargs)
        assert numero not in texto_registrado, (
            f"telefone vazou em LOG_ERRO: {texto_registrado!r}"
        )
