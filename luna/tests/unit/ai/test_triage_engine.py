"""Tests for TriageEngine — 100% coverage obrigatória."""
import pytest

from src.ai.triage_engine import TriageEngine, TriageResult, _normalize
from src.ai.triage_rules import TRIAGE_RULES_VERSION


@pytest.fixture
def engine() -> TriageEngine:
    return TriageEngine()


# ── normalização ──────────────────────────────────────────────────────────────

def test_normalize_remove_accents() -> None:
    assert _normalize("convulsão") == "convulsao"
    assert _normalize("dúvida") == "duvida"
    assert _normalize("náusea") == "nausea"
    assert _normalize("FEBRE") == "febre"


def test_normalize_acento_equivale_sem_acento(engine: TriageEngine) -> None:
    r_com = engine.classificar("meu cachorro teve convulsão")
    r_sem = engine.classificar("meu cachorro teve convulsao")
    assert r_com.urgencia == r_sem.urgencia == "ALTA"


# ── casos básicos ─────────────────────────────────────────────────────────────

def test_texto_vazio_retorna_baixa_score_zero(engine: TriageEngine) -> None:
    r = engine.classificar("")
    assert r.urgencia == "BAIXA"
    assert r.score == 0
    assert r.sintomas_detectados == []


def test_texto_espaco_retorna_baixa(engine: TriageEngine) -> None:
    r = engine.classificar("   ")
    assert r.urgencia == "BAIXA"
    assert r.score == 0


def test_texto_sem_sintomas_retorna_baixa(engine: TriageEngine) -> None:
    r = engine.classificar("olá boa tarde")
    assert r.urgencia == "BAIXA"
    assert r.score == 0


# ── ALTA urgência ─────────────────────────────────────────────────────────────

def test_convulsionando_retorna_alta(engine: TriageEngine) -> None:
    r = engine.classificar("meu cachorro está convulsionando")
    assert r.urgencia == "ALTA"
    assert r.score >= 10


def test_sangramento_retorna_alta(engine: TriageEngine) -> None:
    r = engine.classificar("ela está sangrando muito")
    assert r.urgencia == "ALTA"


def test_envenenamento_retorna_alta(engine: TriageEngine) -> None:
    r = engine.classificar("acho que meu gato foi envenenado")
    assert r.urgencia == "ALTA"


def test_atropelamento_retorna_alta(engine: TriageEngine) -> None:
    r = engine.classificar("meu pet foi atropelado")
    assert r.urgencia == "ALTA"


def test_dispneia_retorna_alta(engine: TriageEngine) -> None:
    r = engine.classificar("ela está ofegante e não respira bem")
    assert r.urgencia == "ALTA"


# ── MEDIA urgência ────────────────────────────────────────────────────────────

def test_vomitando_retorna_media(engine: TriageEngine) -> None:
    r = engine.classificar("meu cachorro está vomitando")
    assert r.urgencia == "MEDIA"
    assert r.score >= 3


def test_diarreia_retorna_media(engine: TriageEngine) -> None:
    r = engine.classificar("ele está com diarreia")
    assert r.urgencia == "MEDIA"


def test_sem_apetite_retorna_media(engine: TriageEngine) -> None:
    r = engine.classificar("meu pet não quer comer nada")
    assert r.urgencia == "MEDIA"


def test_febre_retorna_media(engine: TriageEngine) -> None:
    r = engine.classificar("acho que ele está com febre")
    assert r.urgencia == "MEDIA"


# ── BAIXA urgência ────────────────────────────────────────────────────────────

def test_duvida_retorna_baixa(engine: TriageEngine) -> None:
    r = engine.classificar("tenho uma dúvida sobre ração")
    assert r.urgencia == "BAIXA"
    assert r.score >= 1


def test_comportamento_retorna_baixa(engine: TriageEngine) -> None:
    r = engine.classificar("meu gato está latindo muito")
    assert r.urgencia == "BAIXA"


# ── hierarquia ────────────────────────────────────────────────────────────────

def test_alta_ganha_sobre_media_mesmo_texto(engine: TriageEngine) -> None:
    r = engine.classificar("está vomitando e convulsionando")
    assert r.urgencia == "ALTA"
    assert r.score >= 13  # 10 (ALTA) + 3 (MEDIA)


def test_media_ganha_sobre_baixa(engine: TriageEngine) -> None:
    r = engine.classificar("tenho uma dúvida mas ele está vomitando")
    assert r.urgencia == "MEDIA"


def test_score_acumula_todos_os_niveis(engine: TriageEngine) -> None:
    r = engine.classificar("convulsionando, vomitando e tenho dúvida")
    assert r.urgencia == "ALTA"
    assert r.score >= 14  # 10 + 3 + 1


# ── metadados do resultado ────────────────────────────────────────────────────

def test_result_contem_versao_regras(engine: TriageEngine) -> None:
    r = engine.classificar("convulsionando")
    assert r.regras_versao == TRIAGE_RULES_VERSION


def test_result_e_frozen(engine: TriageEngine) -> None:
    r = engine.classificar("vomitando")
    with pytest.raises(Exception):
        r.urgencia = "ALTA"  # type: ignore[misc]


def test_sintomas_detectados_nao_vazios_em_alta(engine: TriageEngine) -> None:
    r = engine.classificar("meu pet está sangrando")
    assert len(r.sintomas_detectados) > 0


# ── LU-07 item 1: fronteira de palavra (mordida nominal) ──────────────────────

def test_acidentalmente_nao_casa_acidente_mordida_nominal(engine: TriageEngine) -> None:
    """Mordida nominal do brief LU-07: "acidentalmente derrubei a ração" tem
    que dar BAIXA. No motor de main (v1.0, substring), "acidente" é substring
    de "acidentalmente" e a mensagem virava ALTA (trauma) por engano — ver
    scripts/avaliar_triagem.py e o relatório para a prova contra main."""
    r = engine.classificar("acidentalmente derrubei a ração")
    assert r.urgencia == "BAIXA"


def test_acidente_isolado_continua_casando(engine: TriageEngine) -> None:
    r = engine.classificar("meu pet sofreu um acidente feio")
    assert r.urgencia == "ALTA"


# ── LU-07 item 2: negação com janela curta ─────────────────────────────────────

def test_nao_esta_vomitando_mais_nao_vira_media_mordida_nominal(engine: TriageEngine) -> None:
    """Mordida nominal do brief LU-07: "ele não está vomitando mais" não pode
    dar MEDIA por causa do vômito. No motor de main (sem negação), este texto
    dava MEDIA — ver relatório para a prova contra main."""
    r = engine.classificar("ele não está vomitando mais")
    assert r.urgencia != "MEDIA"


def test_negacao_simples_anula_categoria_media(engine: TriageEngine) -> None:
    r = engine.classificar("ele nao esta com febre")
    assert r.urgencia != "MEDIA"


def test_negacao_nunca_anula_categoria(engine: TriageEngine) -> None:
    r = engine.classificar("ele nunca teve diarreia")
    assert r.urgencia != "MEDIA"


def test_negacao_parou_de_anula_categoria(engine: TriageEngine) -> None:
    r = engine.classificar("ele parou de vomitar")
    assert r.urgencia != "MEDIA"


def test_negacao_fora_da_janela_nao_anula(engine: TriageEngine) -> None:
    """Gatilho de negação longe demais (>3 tokens antes) não anula a categoria."""
    r = engine.classificar("nao sei o que aconteceu ontem mas hoje ele esta vomitando")
    assert r.urgencia == "MEDIA"


def test_nao_respira_continua_alta_estado_grave_negado(engine: TriageEngine) -> None:
    """Mordida nominal do escopo LU-07: "não respira" É a keyword positiva de
    dispneia (estado grave) — ALTA é imune a negação, então continua ALTA."""
    r = engine.classificar("meu cachorro não respira")
    assert r.urgencia == "ALTA"


def test_negacao_nao_anula_alta_mesmo_fora_de_estado_grave_embutido(engine: TriageEngine) -> None:
    """Decisão de projeto (documentada em triage_rules.py): ALTA é imune à
    negação por inteiro, não só nas keywords que já embutem "não" — nunca
    afrouxamos ALTA para ganhar acurácia (regra do ciclo)."""
    r = engine.classificar("felizmente ele nao teve convulsão, só ficou bem quieto")
    assert r.urgencia == "ALTA"


# ── LU-07 fix wave 1, item A2: negação não atravessa oração ────────────────────
# Achado da G2 (lu-07-revisao.md, Frente 3): a janela de 3 tokens ignorava
# fim de oração, então um gatilho de negação numa oração rebaixava MEDIA
# legítima em OUTRA oração da mesma mensagem. Pares mínimos: MESMA oração
# (rebaixa) × OUTRA oração, separada por pontuação/conjunção (não rebaixa).
# Escritos por mim (implementador), não vêm do conjunto cego da revisão.

@pytest.mark.parametrize(
    "texto",
    [
        "ele nao esta vomitando",
        "ele parou de vomitar",
        "sem vomitar",
        "ele nunca teve febre",
    ],
)
def test_a2_negacao_mesma_oracao_rebaixa(engine: TriageEngine, texto: str) -> None:
    r = engine.classificar(texto)
    assert r.urgencia == "BAIXA"


@pytest.mark.parametrize(
    "texto",
    [
        "sem febre. vomitando",
        "está sem comer e vomitando",
        "não come, fraco demais",
        "não sei, febre",
        "sem apetite, mas vomitando o dia todo",
        "não está com febre; está vomitando muito",
    ],
)
def test_a2_negacao_em_outra_oracao_nao_rebaixa(engine: TriageEngine, texto: str) -> None:
    """Gatilho de negação numa oração não pode anular sintoma de OUTRA
    oração, mesmo dentro dos 3 tokens de distância — a oração termina em
    pontuação (.,;!?) ou conjunção coordenativa (e, mas, porém, ou)."""
    r = engine.classificar(texto)
    assert r.urgencia == "MEDIA"


def test_a2_mordida_volte_janela_antiga_e_negacao_cruza_oracao(
    engine: TriageEngine,
) -> None:
    """Mordida nominal A2: se a janela voltar a ignorar fim de oração (regra
    antiga: olhar só os 3 tokens crus antes da keyword), esta mensagem seria
    incorretamente anulada, porque "sem" está a 3 tokens de "vomitando" só
    que numa oração diferente, separada por ponto final."""
    r = engine.classificar("sem febre. vomitando")
    assert r.urgencia == "MEDIA"


# ── LU-07 fix wave 1, item 2: vocabulário ALTA por categoria clínica ───────────
# Achado da G2 (lu-07-revisao.md, Frente 2): o corpus original só cobria
# vocabulário que o próprio time escreveu — mensagens reais com sinônimos
# informais de sinais de emergência (dispneia, inconsciência, intoxicação,
# trauma, retenção urinária, parto complicado, picada peçonhenta, abdome
# distendido, hipertermia) não eram reconhecidas. Casos abaixo cobrem cada
# categoria nova/expandida, escritos por mim a partir das categorias do
# brief — não são as mensagens do conjunto cego da revisão.

@pytest.mark.parametrize(
    "texto",
    [
        "meu cachorro não consegue respirar",
        "ela ta respirando de boca aberta",
        "notei a gengiva roxa dele",
        "esta com a lingua azulada",
        "ele não acorda de jeito nenhum",
        "ela desmaiou do nada",
        "ta caido sem reagir",
        "meu cachorro comeu chocolate",
        "ele comeu uva sem querer",
        "acho que ele comeu uma pilha",
        "meu gato sem fazer xixi ha 2 dias",
        "ela ta fazendo forca sem sair nada",
        "gata em trabalho de parto ha horas",
        "o filhote preso não nasce",
        "foi picada de cobra",
        "a barriga inchada e dura, sem melhora",
        "ele ta com golpe de calor",
        "meu cachorro foi mordido por outro animal",
    ],
)
def test_a_item2_vocabulario_categoria_clinica_retorna_alta(
    engine: TriageEngine, texto: str
) -> None:
    r = engine.classificar(texto)
    assert r.urgencia == "ALTA"


def test_item2_negacao_nunca_rebaixa_nova_keyword_alta(engine: TriageEngine) -> None:
    """"não consegue respirar" tem que ser ALTA — é a keyword positiva do
    estado grave (dispneia), não uma negação de sintoma a ser anulada."""
    r = engine.classificar("meu cachorro não consegue respirar")
    assert r.urgencia == "ALTA"


def test_item2_fronteira_de_palavra_sem_regressao_sanguessuga(
    engine: TriageEngine,
) -> None:
    """Vocabulário novo não pode reabrir falso positivo de substring —
    "sanguessuga" continua BAIXA (não casa a keyword "sangue" por token)."""
    r = engine.classificar("achei uma sanguessuga no quintal")
    assert r.urgencia == "BAIXA"


def test_item2_fronteira_de_palavra_sem_regressao_afebril(engine: TriageEngine) -> None:
    r = engine.classificar("ele esta afebril hoje")
    assert r.urgencia == "BAIXA"


# ── LU-07 item 3: versão das regras ────────────────────────────────────────────

def test_versao_regras_e_1_2() -> None:
    """LU-07 fix wave 1, item 3: versão sobe para 1.2 (≤ 10 bytes)."""
    assert TRIAGE_RULES_VERSION == "1.2"
    assert len(TRIAGE_RULES_VERSION.encode("utf-8")) <= 10
