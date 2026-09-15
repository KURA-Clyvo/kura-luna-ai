"""Avalia o TriageEngine contra um corpus rotulado (LU-07 item 7).

Calcula matriz de confusão 3x3 (esperado x previsto), acurácia, taxa de
subtriagem de ALTA (esperado ALTA, previsto MEDIA/BAIXA) e taxa de
supertriagem (esperado BAIXA/MEDIA, previsto nível mais alto que o
esperado). Saída em markdown, pronta para colar em `IA_DEFINICAO.md`.

Uso:
    cd kura-luna-ai/luna
    PYTHONPATH=. python scripts/avaliar_triagem.py
    PYTHONPATH=. python scripts/avaliar_triagem.py --src /caminho/outro/luna --rotulo v1.0
    PYTHONPATH=. python scripts/avaliar_triagem.py --corpus outro_corpus.jsonl

`--src` insere a raiz de OUTRO clone (contendo `src/ai/triage_engine.py`) na
frente de `sys.path`, antes de importar — assim dá para medir o motor de um
clone diferente (ex.: linha de base v1.0) sem sair do worktree onde este
script vive. O corpus é sempre lido do caminho local, salvo se `--corpus`
apontar para outro lugar.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

_NIVEIS = ["ALTA", "MEDIA", "BAIXA"]
_RANK = {"BAIXA": 0, "MEDIA": 1, "ALTA": 2}


def carregar_corpus(caminho: Path) -> list[dict[str, Any]]:
    """Lê o corpus JSONL, validando campos obrigatórios linha a linha."""
    itens: list[dict[str, Any]] = []
    with caminho.open(encoding="utf-8") as f:
        for numero_linha, linha in enumerate(f, start=1):
            linha = linha.strip()
            if not linha:
                continue
            try:
                obj = json.loads(linha)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{caminho}:{numero_linha}: JSON inválido — {exc}") from exc
            for campo in ("mensagem", "urgencia_esperada", "justificativa"):
                if campo not in obj:
                    raise ValueError(f"{caminho}:{numero_linha}: campo obrigatório ausente: {campo}")
            if obj["urgencia_esperada"] not in _NIVEIS:
                raise ValueError(
                    f"{caminho}:{numero_linha}: urgencia_esperada inválida: {obj['urgencia_esperada']!r}"
                )
            itens.append(obj)
    if not itens:
        raise ValueError(f"{caminho}: corpus vazio")
    return itens


def avaliar(engine: Any, corpus: list[dict[str, Any]]) -> dict[str, Any]:
    """Roda o engine sobre o corpus inteiro e monta a matriz de confusão + taxas."""
    matriz = {esperado: {previsto: 0 for previsto in _NIVEIS} for esperado in _NIVEIS}
    detalhes = []

    for item in corpus:
        resultado = engine.classificar(item["mensagem"])
        esperado = item["urgencia_esperada"]
        previsto = resultado.urgencia
        matriz[esperado][previsto] += 1
        detalhes.append({**item, "previsto": previsto, "acertou": previsto == esperado})

    total = len(corpus)
    corretos = sum(matriz[nivel][nivel] for nivel in _NIVEIS)
    acuracia = corretos / total if total else 0.0

    total_alta = sum(matriz["ALTA"].values())
    subtriagem_alta_n = matriz["ALTA"]["MEDIA"] + matriz["ALTA"]["BAIXA"]
    taxa_subtriagem_alta = subtriagem_alta_n / total_alta if total_alta else 0.0

    supertriagem_n = 0
    supertriagem_total = 0
    for esperado in ("BAIXA", "MEDIA"):
        supertriagem_total += sum(matriz[esperado].values())
        for previsto in _NIVEIS:
            if _RANK[previsto] > _RANK[esperado]:
                supertriagem_n += matriz[esperado][previsto]
    taxa_supertriagem = supertriagem_n / supertriagem_total if supertriagem_total else 0.0

    return {
        "total": total,
        "matriz": matriz,
        "corretos": corretos,
        "acuracia": acuracia,
        "subtriagem_alta_n": subtriagem_alta_n,
        "subtriagem_alta_total": total_alta,
        "taxa_subtriagem_alta": taxa_subtriagem_alta,
        "supertriagem_n": supertriagem_n,
        "supertriagem_total": supertriagem_total,
        "taxa_supertriagem": taxa_supertriagem,
        "detalhes": detalhes,
    }


def formatar_markdown(stats: dict[str, Any], versao_regras: str, rotulo: str) -> str:
    linhas = [f"### Avaliação — {rotulo} (`TRIAGE_RULES_VERSION = \"{versao_regras}\"`)", ""]
    linhas.append(f"- Corpus: **{stats['total']}** mensagens")
    linhas.append(f"- Acurácia: **{stats['acuracia']:.1%}** ({stats['corretos']}/{stats['total']})")
    linhas.append(
        f"- **Subtriagem de ALTA:** **{stats['taxa_subtriagem_alta']:.1%}** "
        f"({stats['subtriagem_alta_n']}/{stats['subtriagem_alta_total']})"
    )
    linhas.append(
        f"- Supertriagem (BAIXA/MEDIA classificado acima do esperado): **{stats['taxa_supertriagem']:.1%}** "
        f"({stats['supertriagem_n']}/{stats['supertriagem_total']})"
    )
    linhas.append("")
    linhas.append("| Esperado \\ Previsto | ALTA | MEDIA | BAIXA |")
    linhas.append("|---|---|---|---|")
    for esperado in _NIVEIS:
        linha_matriz = stats["matriz"][esperado]
        linhas.append(
            f"| **{esperado}** | {linha_matriz['ALTA']} | {linha_matriz['MEDIA']} | {linha_matriz['BAIXA']} |"
        )
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--src",
        type=Path,
        default=None,
        help="raiz de outro clone (contendo src/ai/triage_engine.py) — inserida no início de sys.path",
    )
    parser.add_argument("--corpus", type=Path, default=None, help="caminho do corpus JSONL (padrão: tests/fixtures/triagem_corpus_v1.jsonl deste worktree)")
    parser.add_argument("--rotulo", type=str, default=None, help="rótulo do relatório (padrão: TRIAGE_RULES_VERSION do motor carregado)")
    args = parser.parse_args(argv)

    if args.src is not None:
        sys.path.insert(0, str(args.src.resolve()))

    # Import adiado de propósito: só depois de manipular sys.path é que
    # decidimos de qual "src" o motor vem.
    from src.ai.triage_engine import TriageEngine
    from src.ai.triage_rules import TRIAGE_RULES_VERSION

    corpus_path = args.corpus or (Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "triagem_corpus_v1.jsonl")
    corpus = carregar_corpus(corpus_path)

    engine = TriageEngine()
    stats = avaliar(engine, corpus)
    rotulo = args.rotulo or TRIAGE_RULES_VERSION
    print(formatar_markdown(stats, TRIAGE_RULES_VERSION, rotulo))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
