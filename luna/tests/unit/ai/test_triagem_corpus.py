"""LU-07 item 7 (critério de aceite): teste parametrizado sobre o corpus
inteiro (`tests/fixtures/triagem_corpus_v1.jsonl`) + mordidas nominais,
rodando contra o `TriageEngine` local (v1.1) deste worktree.

Corpus escrito pelo time (implementador sonnet), NÃO validado por
veterinário — ver cabeçalho de `scripts/avaliar_triagem.py` e
`lu-07-report.md` para a matriz v1.0 × v1.1 completa.
"""
from pathlib import Path

import pytest

from scripts.avaliar_triagem import _RANK, carregar_corpus
from src.ai.triage_engine import TriageEngine

_CORPUS_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "triagem_corpus_v1.jsonl"
_CORPUS = carregar_corpus(_CORPUS_PATH)

# LU-07 fix wave 1, item 3 (achado A5 da G2): a linha do sangramento
# resolvido ("já estancou") tinha `urgencia_esperada` ajustado à REGRA do
# motor (ALTA, "porque o item 2 diz"), não ao julgamento clínico. Corrigida
# para o rótulo clínico (MEDIA — sangramento já resolvido não é mais
# emergência ativa); o motor CONTINUA classificando ALTA por desenho (ALTA
# imune a negação, nunca afrouxamos), e isso é supertriagem aceita, não
# subtriagem — documentada explicitamente abaixo em vez de "corrigir" o
# rótulo para bater com a regra de novo.
_SUPERTRIAGEM_ACEITA_POR_DESENHO = "supertriagem_aceita_por_desenho"


@pytest.fixture(scope="module")
def engine() -> TriageEngine:
    return TriageEngine()


@pytest.mark.parametrize(
    "item",
    _CORPUS,
    ids=[f"{i:03d}-{item['urgencia_esperada']}" for i, item in enumerate(_CORPUS)],
)
def test_corpus_classificacao_esperada(item: dict, engine: TriageEngine) -> None:
    resultado = engine.classificar(item["mensagem"])
    if item.get("classe") == _SUPERTRIAGEM_ACEITA_POR_DESENHO:
        # Rótulo é o clínico, o motor erra por desenho (supertriagem aceita,
        # nunca subtriagem) — ver comentário no topo do arquivo (achado A5).
        assert _RANK[resultado.urgencia] >= _RANK[item["urgencia_esperada"]], (
            f"mensagem={item['mensagem']!r} — supertriagem esperada, mas o motor "
            f"classificou ABAIXO do rótulo clínico: {resultado.urgencia}"
        )
        return
    assert resultado.urgencia == item["urgencia_esperada"], (
        f"mensagem={item['mensagem']!r} justificativa={item['justificativa']!r} "
        f"esperado={item['urgencia_esperada']} previsto={resultado.urgencia}"
    )


def test_corpus_sem_subtriagem_de_alta(engine: TriageEngine) -> None:
    """Critério de aceite: subtriagem de ALTA = 0 no corpus inteiro (v1.1)."""
    falhas = []
    for item in _CORPUS:
        if item["urgencia_esperada"] != "ALTA":
            continue
        resultado = engine.classificar(item["mensagem"])
        if resultado.urgencia != "ALTA":
            falhas.append((item["mensagem"], resultado.urgencia))
    assert not falhas, f"subtriagem de ALTA encontrada: {falhas}"


class TestMordidasNominais:
    """Mordidas nominais — cada uma comprovadamente falha contra o motor de
    `main` (`e67137a`, `TRIAGE_RULES_VERSION = "1.0"`); a demonstração
    literal (`avaliar_triagem.py --src <clone v1.0>`) está em
    `lu-07-report.md`."""

    def test_negacao_nao_esta_vomitando_mais(self, engine: TriageEngine) -> None:
        """Mordida nominal do brief. Medido contra v1.0: MEDIA (falha — sem
        negação, 'vomitando' sempre conta). v1.1: BAIXA."""
        resultado = engine.classificar("ele não está vomitando mais")
        assert resultado.urgencia == "BAIXA"

    def test_acidentalmente_derrubei_a_racao(self, engine: TriageEngine) -> None:
        """Exemplo literal do brief. DESVIO MEDIDO: não falha contra v1.0 —
        'acidente' não é substring de 'acidentalmente' (verificado com
        `'acidente' in 'acidentalmente'` → False), logo v1.0 já classificava
        BAIXA para esta frase. Mantido como caso de regressão (continua
        BAIXA em v1.1), não como mordida — ver 'O que NÃO foi verificado'
        e o achado registrado no relatório."""
        resultado = engine.classificar("acidentalmente derrubei a ração dele")
        assert resultado.urgencia == "BAIXA"

    def test_falso_positivo_sanguessuga_nao_e_sangue(self, engine: TriageEngine) -> None:
        """Mordida real de fronteira de palavra (substituta medida do
        exemplo do brief, que não reproduzia — ver teste acima). 'sanguessuga'
        contém 'sangue' como substring mas não como token. v1.0: ALTA (falso
        positivo). v1.1: BAIXA."""
        resultado = engine.classificar("vi uma sanguessuga gigante no jardim, nada demais")
        assert resultado.urgencia == "BAIXA"

    def test_falso_positivo_afebril_nao_e_febril(self, engine: TriageEngine) -> None:
        """Segunda mordida de fronteira de palavra. 'afebril' contém
        'febril' como substring mas não como token. v1.0: MEDIA (falso
        positivo). v1.1: BAIXA."""
        resultado = engine.classificar("o veterinário disse que ele está afebril, tudo bem")
        assert resultado.urgencia == "BAIXA"

    def test_subtriagem_fix_pontuacao_quebra_substring_em_v10(self, engine: TriageEngine) -> None:
        """Mordida de subtriagem real: reticências entre 'não' e 'respira'
        quebram o substring exato que v1.0 exige. v1.0: BAIXA (falha —
        subtriagem de ALTA). v1.1 tokeniza ignorando a pontuação: ALTA."""
        resultado = engine.classificar("meu cachorro não... respira direito, muito mal")
        assert resultado.urgencia == "ALTA"

    def test_subtriagem_fix_virgula_quebra_substring_em_v10(self, engine: TriageEngine) -> None:
        """Mesma classe, keyword diferente ('bateu a cabeça' partido por
        vírgula). v1.0: BAIXA (falha). v1.1: ALTA."""
        resultado = engine.classificar("ele bateu, a cabeça na parede")
        assert resultado.urgencia == "ALTA"

    def test_alta_imune_a_negacao(self, engine: TriageEngine) -> None:
        """Item 2: ALTA nunca é anulada por negação (nunca afrouxar ALTA
        para ganhar acurácia) — 'sangrando' negado continua ALTA por
        desenho, mesmo custando supertriagem."""
        resultado = engine.classificar("ele não está mais sangrando, já estancou, mas fiquei com medo")
        assert resultado.urgencia == "ALTA"

    def test_nao_respira_e_estado_grave_imune(self, engine: TriageEngine) -> None:
        """'não respira'/'nao respira' É a própria keyword de dispneia —
        continua ALTA mesmo contendo um gatilho de negação (item 2)."""
        resultado = engine.classificar("meu coelho não respira direito, super mal")
        assert resultado.urgencia == "ALTA"
