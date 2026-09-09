"""Demonstração funcional da IA da Luna — Sprint 3.

Roda a cadeia real de decisão da Luna **sem exigir Oracle, Docker, Twilio ou
chave da OpenAI**. Os gateways externos (API .NET e WhatsApp) são substituídos
por dublês que imprimem exatamente o payload que iria para a rede — o resto é
código de produção, sem cópia e sem simplificação.

É a "demonstração funcional simulada" que a rubrica autoriza (p. 19).

Uso:
    cd kura-luna-ai/luna
    PYTHONPATH=. python scripts/demo_sprint3.py            # tudo, com pausas
    PYTHONPATH=. python scripts/demo_sprint3.py --auto     # tudo, sem pausas
    PYTHONPATH=. python scripts/demo_sprint3.py triagem    # só o ato 1
    PYTHONPATH=. python scripts/demo_sprint3.py cadeia     # só o ato 2
    PYTHONPATH=. python scripts/demo_sprint3.py soap       # só o ato 3
    PYTHONPATH=. python scripts/demo_sprint3.py limites    # só o ato 4
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime

from src.ai.triage_engine import TriageEngine
from src.integration.dtos import (
    InteractionRequestDTO,
    PetResumoDTO,
    TriageRequestDTO,
    TutorContextoDTO,
)
from src.messaging.twilio_inbound import InboundMessage
from src.services.inbound_message_service import InboundMessageService
from src.services.transcricao_service import montar_soap_draft

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

LARGURA = 78


def titulo(texto: str) -> None:
    print("\n" + "=" * LARGURA)
    print(f"  {texto}")
    print("=" * LARGURA)


def secao(texto: str) -> None:
    print(f"\n--- {texto} " + "-" * max(0, LARGURA - len(texto) - 6))


def pausa() -> None:
    """Pausa para a narração do vídeo. ENTER continua; --auto pula."""
    if "--auto" not in sys.argv:
        try:
            input("\n   [ENTER para continuar] ")
        except (EOFError, KeyboardInterrupt):
            print()


def _json(payload: dict) -> str:  # type: ignore[type-arg]
    corpo = json.dumps(payload, ensure_ascii=False, indent=6, default=str)
    return "\n".join(f"      {linha}" for linha in corpo.splitlines())


def _quebrar(texto: str, largura: int) -> list[str]:
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        if len(atual) + len(p) + 1 > largura:
            linhas.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}".strip()
    if atual:
        linhas.append(atual)
    return linhas


# ── Dublês dos serviços externos ──────────────────────────────────────────────
# Substituem só o transporte. A decisão continua sendo a de produção.

TUTOR_DEMO = TutorContextoDTO(
    id_tutor=42,
    nm_tutor="Marina Alves",
    ds_whatsapp="5511987654321",
    id_clinica=7,
    pets=[
        PetResumoDTO(id_pet=101, nm_pet="Thor", nm_especie="Canina", nm_raca="Golden Retriever")
    ],
)


class KuraClientDemo:
    """Dublê da API .NET. Imprime o que iria pela rede em vez de chamar."""

    def __init__(self, tutor: TutorContextoDTO | None) -> None:
        self._tutor = tutor
        self._seq = 5000

    async def buscar_tutor_por_telefone(self, numero: str) -> TutorContextoDTO | None:
        achou = "tutor encontrado" if self._tutor else "NAO cadastrado (HTTP 404)"
        print(f"   -> GET  /api/v1/tutores/telefone/(numero)   [{achou}]")
        print("      o numero NAO aparece no log: e PII, e isso e regra dura aqui")
        return self._tutor

    async def registrar_interacao(self, dto: InteractionRequestDTO) -> int:
        self._seq += 1
        print("   -> POST /api/v1/luna/interactions   [201]  grava INTERACAO_CANAL")
        print(_json(dto.model_dump(mode="json")))
        return self._seq

    async def registrar_triagem(self, dto: TriageRequestDTO) -> int:
        self._seq += 1
        print("   -> POST /api/v1/luna/triage         [201]  grava TRIAGEM_LUNA")
        print(_json(dto.model_dump(mode="json")))
        return self._seq

    async def verificar_saude(self) -> bool:
        return True


class TwilioGatewayDemo:
    """Dublê do WhatsApp. Imprime a resposta que o tutor receberia."""

    def enviar_whatsapp(self, numero: str, mensagem: str) -> str:
        print("\n   << WhatsApp entregue ao tutor:")
        for linha in _quebrar(mensagem, LARGURA - 9):
            print(f"      {linha}")
        return "SM_demo_0001"


class LogErroRepoDemo:
    """Dublê da tabela LOG_ERRO."""

    def registrar(self, *args: object, **kwargs: object) -> None:
        print(f"   -> INSERT LOG_ERRO {kwargs or args}")


# ── Ato 1 — o motor de triagem, isolado ───────────────────────────────────────

MENSAGENS_TRIAGEM: list[tuple[str, str]] = [
    (
        "Socorro, meu cachorro esta convulsionando e sangrando muito!",
        "emergencia: dois sintomas de nivel ALTA na mesma frase",
    ),
    (
        "Convulsao agora, ajuda",
        "mesma emergencia, sem acento e em outra grafia — o NFKD normaliza",
    ),
    (
        "Meu gato vomitou tres vezes hoje e esta sem apetite",
        "sinal que merece retorno, mas nao e emergencia",
    ),
    (
        "Queria saber quando vence a vacina antirrabica do Thor",
        "duvida administrativa — nao ocupa a fila clinica",
    ),
    (
        "Bom dia! Tudo bem com voces?",
        "sem sintoma nenhum: o motor nao inventa urgencia",
    ),
]


def ato_1_triagem() -> None:
    titulo("ATO 1 — O motor de triagem classifica a mensagem do tutor")
    print(
        """
  Entrada: o texto livre que o tutor escreveu no WhatsApp.
  Saida:   urgencia + os sintomas que a dispararam + o score.

  Repare que a saida traz SEMPRE o porque da decisao. E isso que um LLM nao
  entrega: ele devolve o rotulo, nao a causa que o produziu.
"""
    )
    engine = TriageEngine()
    for texto, nota in MENSAGENS_TRIAGEM:
        r = engine.classificar(texto)
        secao(nota)
        print(f'   Tutor    : "{texto}"')
        print(f"   Urgencia : {r.urgencia}")
        print(f"   Sintomas : {r.sintomas_detectados or '(nenhum reconhecido)'}")
        print(f"   Score    : {r.score}      Base de regras: v{r.regras_versao}")

    print(
        """
  Score e urgencia respondem perguntas diferentes, e isso e de proposito:

    urgencia = EM QUE FILA isso entra   (ALTA > MEDIA > BAIXA, hierarquia estrita)
    score    = DENTRO da fila, o que vem primeiro (10 / 3 / 1 por categoria)

  Por isso as duas primeiras sao ALTA, mas a primeira pontua 20 e a segunda 10:
  duas categorias de emergencia contra uma.
"""
    )


# ── Ato 2 — a cadeia completa ─────────────────────────────────────────────────


async def _rodar_cadeia(corpo: str, tutor: TutorContextoDTO | None) -> None:
    servico = InboundMessageService(
        kura_client=KuraClientDemo(tutor),  # type: ignore[arg-type]
        triage_engine=TriageEngine(),
        twilio_gateway=TwilioGatewayDemo(),  # type: ignore[arg-type]
        log_repo=LogErroRepoDemo(),  # type: ignore[arg-type]
    )
    msg = InboundMessage(
        numero_origem="5511987654321" if tutor else "5511000000000",
        corpo=corpo,
        message_sid="SM" + datetime.now(tz=UTC).strftime("%H%M%S%f"),
        account_sid="ACdemo",
    )
    print(f'\n   >> WhatsApp recebido: "{corpo}"')
    resultado = await servico.processar(msg)
    print(
        f"\n   Resultado: id_interacao={resultado.id_interacao} urgencia={resultado.urgencia}"
    )


def ato_2_cadeia() -> None:
    titulo("ATO 2 — A cadeia inteira: WhatsApp -> IA -> API .NET -> Oracle")
    print(
        """
  Agora nao e mais so o motor. E o InboundMessageService de producao, o mesmo
  que o webhook do Twilio chama. So os dois gateways de SAIDA sao dubles: em
  vez de fazer a chamada HTTP, imprimem o payload exato que iria pela rede.

  Preste atencao na ORDEM: a interacao e registrada ANTES da triagem. Se a
  classificacao falhar, a mensagem do tutor nao se perde.
"""
    )
    pausa()

    secao("2.1 — Tutor cadastrado, emergencia")
    asyncio.run(
        _rodar_cadeia("Socorro, meu cachorro esta convulsionando e sangrando muito!", TUTOR_DEMO)
    )
    pausa()

    secao("2.2 — Mesmo tutor, duvida simples: a resposta MUDA")
    asyncio.run(_rodar_cadeia("Queria saber quando vence a vacina antirrabica do Thor", TUTOR_DEMO))
    pausa()

    secao("2.3 — Numero NAO cadastrado: registra, mas nao tria")
    print(
        """
   Decisao de produto declarada: preferimos guardar o registro de auditoria a
   descartar o sinal. A interacao e gravada com ID_CLINICA nulo — e por isso
   ela e invisivel a qualquer consulta escopada por clinica. O ganho e
   auditoria, nao visibilidade na tela. Esta na lista de evolucao.
"""
    )
    asyncio.run(_rodar_cadeia("Socorro, meu cachorro esta convulsionando!", None))


# ── Ato 3 — NLP clínico ───────────────────────────────────────────────────────

DITADO_VET = (
    "A tutora relata que o Thor esta comendo menos ha tres dias. "
    "Ela diz que ele tambem vomitou ontem a noite. "
    "Ao exame fisico, temperatura de 39.8 graus e mucosas normocoradas. "
    "Ausculta cardiaca sem alteracoes. "
    "Suspeita de gastrite aguda. "
    "Vou prescrever omeprazol por sete dias e solicito exame de sangue. "
    "Retorno em uma semana."
)


def ato_3_soap() -> None:
    titulo("ATO 3 — NLP clinico: o audio da consulta vira rascunho SOAP")
    print(
        """
  No sistema real o veterinario grava o audio pelo app. O .NET repassa para a
  Luna, que chama a API Whisper (rede neural, de terceiro) e recebe o texto.

  O que roda aqui e o ESTAGIO 2 — a estruturacao, que e nossa e nao precisa de
  chave nenhuma. Entramos com o texto que o Whisper devolveria.
"""
    )
    print("   Texto transcrito (entrada):\n")
    for linha in _quebrar(DITADO_VET, LARGURA - 6):
        print(f"      {linha}")
    pausa()

    draft = montar_soap_draft(DITADO_VET)
    campos = [
        ("S", "Subjetivo", "o que foi relatado", draft.s),
        ("O", "Objetivo", "o que foi medido", draft.o),
        ("A", "Avaliacao", "o que o vet concluiu", draft.a),
        ("P", "Plano", "o que sera feito", draft.p),
    ]
    print("\n   Rascunho SOAP (saida):\n")
    for sigla, nome, glosa, valor in campos:
        print(f"   [{sigla}] {nome} — {glosa}")
        for linha in _quebrar(valor or "(vazio)", LARGURA - 9):
            print(f"       {linha}")
        print()

    print(
        """  Duas decisoes de desenho que valem ser ditas em voz alta:

    1. O bucket padrao e S. Frase que o sistema nao reconhece vai para "relato
       do tutor", que e o campo mais inofensivo dos quatro. A mesma frase
       caindo em P seria uma CONDUTA que ninguem prescreveu.

    2. Nada disso e persistido. O endpoint devolve o rascunho; salvar e acao do
       veterinario, na tela dele. A Luna sugere, o veterinario decide.
"""
    )


# ── Ato 4 — os limites, ditos por nós ─────────────────────────────────────────

LIMITES: list[tuple[str, str, str]] = [
    (
        "Nao trata negacao",
        "Ele nao esta vomitando, so quieto",
        "erra para o lado SEGURO: escala o que nao precisava, e um humano descarta",
    ),
    (
        "Nao tem nocao de tempo",
        "Ele engasgou ontem mas ja passou",
        "erra para o lado SEGURO: mesma logica",
    ),
    (
        "Nao entende o contexto da palavra",
        "Ele esta com o pelo fraco e sem brilho",
        "'fraco' e sintoma de letargia na base; aqui a frase fala do pelo",
    ),
    (
        "Nao conhece sinonimo fora da base",
        "Ele regurgitou depois de comer",
        "ESTE e o que importa: sintoma real classificado como BAIXA",
    ),
    (
        "Nem termo tecnico, se nao estiver cadastrado",
        "Ele esta com dispneia",
        "a CATEGORIA se chama dispneia; a palavra nao e uma das keywords dela",
    ),
]


def ato_4_limites() -> None:
    titulo("ATO 4 — Os limites, ditos por nos antes de alguem perguntar")
    print(
        """
  Um motor de regras acerta o que esta na base e erra o que nao esta. Abaixo,
  cinco casos reais rodando no motor de verdade. Tres erram para o lado seguro.
  Dois nao — e sao esses que definem a proxima versao da base de regras.
"""
    )
    engine = TriageEngine()
    for limite, texto, consequencia in LIMITES:
        r = engine.classificar(texto)
        secao(limite)
        print(f'   Tutor      : "{texto}"')
        print(f"   Classificou: {r.urgencia} (score {r.score}, sintomas {r.sintomas_detectados})")
        print(f"   Leitura    : {consequencia}")

    print(
        """
  E por isso que TRIAGE_RULES_VERSION existe. A base de sintomas e um artefato
  vivo, revisado com o veterinario e versionado como codigo — nao um modelo
  opaco que ninguem sabe corrigir.

  Correcao a documentacao anterior deste projeto: o exemplo de falso positivo
  por substring que estava escrito nos nossos documentos era "acidente" dentro
  de "acidentalmente". Isso NAO acontece — "acidentalmente" nao contem
  "acidente". Medimos, e o exemplo estava errado. Os cinco casos acima sao os
  que reproduzem de verdade.
"""
    )


# ── Encerramento ──────────────────────────────────────────────────────────────


def encerramento() -> None:
    titulo("O que voce acabou de ver rodar")
    print(
        """
    Ato 1  TriageEngine            src/ai/triage_engine.py + triage_rules.py
    Ato 2  InboundMessageService   src/services/inbound_message_service.py
    Ato 3  montar_soap_draft       src/services/transcricao_service.py
    Ato 4  os limites do Ato 1     medidos, nao estimados

  Codigo de producao nos quatro. Os unicos dubles sao os dois gateways de
  saida (API .NET e WhatsApp), e eles imprimem o payload que iria pela rede.

  O que NAO roda aqui — e a honestidade vale mais que a demo:
    - a chamada real ao Whisper          (precisa de OPENAI_API_KEY)
    - a escrita real no Oracle           (precisa do compose no ar)
    - o envio real pelo WhatsApp         (precisa do Twilio Sandbox)
    - a visao computacional              (o checkpoint nao esta no repo)
"""
    )


ATOS = {
    "triagem": ato_1_triagem,
    "cadeia": ato_2_cadeia,
    "soap": ato_3_soap,
    "limites": ato_4_limites,
}


def main() -> None:
    escolhidos = [a for a in sys.argv[1:] if not a.startswith("-")]
    if escolhidos:
        for nome in escolhidos:
            if nome not in ATOS:
                print(f"Ato desconhecido: {nome}. Disponiveis: {', '.join(ATOS)}")
                raise SystemExit(2)
            ATOS[nome]()
        return

    titulo("LUNA — demonstracao funcional da IA · KURA / Clyvo Vet · Sprint 3")
    print(
        """
  Quatro atos, na ordem em que a IA age no mundo real:

    1. o motor de triagem, isolado
    2. a cadeia inteira ate o banco
    3. o NLP clinico da consulta
    4. os limites, ditos por nos

  Sem Docker, sem Oracle, sem Twilio, sem chave de API.
"""
    )
    pausa()
    for ato in ATOS.values():
        ato()
        pausa()
    encerramento()


if __name__ == "__main__":
    main()
