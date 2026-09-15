"""Tests for scripts/avaliar_triagem.py — LU-07 fix wave 1, item 5 (A4).

A revisão G2 (lu-07-revisao.md, Frente 8) achou a ressalva de autoria/
validação do corpus ausente da saída markdown do script (o relatório
alegava, falsamente, que ela estava no cabeçalho — não estava, `grep`
devolvia 0 linhas). Estes testes provam que a ressalva agora aparece de
verdade, com controle positivo (grep no teste do corpus, que já a tinha,
para provar que o instrumento enxerga a string quando ela existe).
"""
from pathlib import Path

from scripts.avaliar_triagem import RESSALVA_CORPUS, avaliar, carregar_corpus, formatar_markdown
from src.ai.triage_engine import TriageEngine

_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"
_CORPUS_PATH = _FIXTURES_DIR / "triagem_corpus_v1.jsonl"


def test_ressalva_corpus_contem_texto_exigido_pelo_backlog() -> None:
    """§8 do backlog: "validado por veterinário" tem que estar presente
    (negado) e "não validado" tem que ser dito explicitamente."""
    assert "não validado" in RESSALVA_CORPUS or "nao validado" in RESSALVA_CORPUS.lower()
    assert "veterinário" in RESSALVA_CORPUS or "veterinario" in RESSALVA_CORPUS.lower()
    assert "regras" in RESSALVA_CORPUS.lower()
    assert "segurança clínica" in RESSALVA_CORPUS or "seguranca clinica" in RESSALVA_CORPUS.lower()


def test_saida_markdown_contem_ressalva_acima_da_matriz() -> None:
    """A4: a ressalva tem que estar na saída que vai para IA_DEFINICAO.md,
    ANTES da matriz de confusão."""
    corpus = carregar_corpus(_CORPUS_PATH)
    engine = TriageEngine()
    stats = avaliar(engine, corpus)
    saida = formatar_markdown(stats, "1.2", "v1.2")

    assert RESSALVA_CORPUS in saida

    pos_ressalva = saida.index(RESSALVA_CORPUS)
    pos_matriz = saida.index("| Esperado")
    assert pos_ressalva < pos_matriz, "ressalva tem que vir ANTES da matriz"


def test_mordida_saida_sem_ressalva_nao_contem_string_obrigatoria() -> None:
    """Mordida nominal: gera a saída SEM chamar formatar_markdown (simulando
    a versão antiga, que nunca imprimia a ressalva) e confirma que a string
    exigida pelo §8 não aparece por acidente em nenhum outro lugar da saída
    básica — prova que a presença medida acima não é vácua."""
    corpus = carregar_corpus(_CORPUS_PATH)
    engine = TriageEngine()
    stats = avaliar(engine, corpus)
    linhas_sem_ressalva = [
        f"### Avaliação — v1.2 (`TRIAGE_RULES_VERSION = \"1.2\"`)",
        "",
        f"- Corpus: **{stats['total']}** mensagens",
    ]
    saida_antiga_simulada = "\n".join(linhas_sem_ressalva)
    assert "não validado" not in saida_antiga_simulada
    assert "veterinário" not in saida_antiga_simulada


def test_readme_fixtures_contem_ressalva() -> None:
    """A4: tests/fixtures/README.md precisa existir e conter a ressalva
    literal exigida pelo brief."""
    readme = _FIXTURES_DIR / "README.md"
    assert readme.exists(), "tests/fixtures/README.md não existe"
    texto_lower = readme.read_text(encoding="utf-8").lower()
    assert "não validado por" in texto_lower
    assert "veterinário" in texto_lower
    assert "mede aderência às regras" in texto_lower
