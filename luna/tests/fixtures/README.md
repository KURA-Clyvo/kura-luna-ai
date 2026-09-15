# Corpus de triagem — `triagem_corpus_v1.jsonl`

⚠️ **Corpus escrito pelo time de desenvolvimento, não validado por veterinário.
Mede aderência às regras, não segurança clínica.**

Cada linha é uma mensagem de tutor rotulada com `urgencia_esperada`
(`ALTA`/`MEDIA`/`BAIXA`), `justificativa` e `classe` (tag de cobertura —
abreviação, erro de digitação, emoji, negação, espécie, falso positivo,
vocabulário por categoria clínica, etc.).

Os rótulos são julgamento do implementador (LU-07, e a fix wave 1 que o
ampliou), **não de profissional de saúde animal**. Um número de acurácia ou
de taxa de subtriagem calculado sobre este corpus (`scripts/avaliar_triagem.py`)
mede **o quanto o motor acerta o que o próprio time escreveu**, não o quanto
o motor é seguro contra vocabulário real de tutores fora dessa lista — ver
`lu-07-revisao.md` (achado A1, conjunto cego independente) para a diferença
entre os dois números.

Não apresentar nenhum número deste corpus (acurácia, subtriagem,
supertriagem) em slide, documento público ou `IA_DEFINICAO.md` sem repetir
esta ressalva ao lado (`KURA_BACKLOG_LUNA_AI.md` §8).

Algumas linhas (`classe: "supertriagem_aceita_por_desenho"`) têm
`urgencia_esperada` no rótulo CLÍNICO, mesmo quando o motor por desenho
classifica um nível acima (ALTA nunca é anulada por negação — nunca
afrouxamos ALTA para ganhar acurácia). Essas linhas medem supertriagem
aceita, documentada de propósito, não erro de rotulagem — ver
`tests/unit/ai/test_triagem_corpus.py`.
