"""Motor de triagem por regras para mensagens de tutores."""
import re
import unicodedata
from dataclasses import dataclass, field

from src.ai.triage_rules import (
    CLAUSE_BOUNDARY_CHARS,
    CLAUSE_COORDINATING_CONJUNCTIONS,
    NEGATION_TRIGGERS,
    NEGATION_WINDOW_TOKENS,
    SINTOMAS_ALTA_URGENCIA,
    SINTOMAS_BAIXA_URGENCIA,
    SINTOMAS_MEDIA_URGENCIA,
    TRIAGE_RULES_VERSION,
)

_POINTS: dict[str, int] = {"ALTA": 10, "MEDIA": 3, "BAIXA": 1}

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# LU-07 fix wave 1 (A2): mesma varredura de _TOKEN_RE, mas também casando os
# caracteres de fim de oração — usado só para calcular limite de oração
# (_clause_ids), nunca para casar keyword (que continua exigindo fronteira
# de palavra sobre tokens só-alfanuméricos, sem regressão do item 1).
_CLAUSE_TOKEN_RE = re.compile(r"[a-z0-9]+|[" + re.escape(CLAUSE_BOUNDARY_CHARS) + "]")
_CLAUSE_BOUNDARY_SET = set(CLAUSE_BOUNDARY_CHARS)
_CLAUSE_CONJUNCTIONS_SET = set(CLAUSE_COORDINATING_CONJUNCTIONS)


def _normalize(text: str) -> str:
    """Lowercase + remove diacritics via NFKD decomposition."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _tokenize(normalized_text: str) -> list[str]:
    """Quebra o texto normalizado em tokens alfanuméricos (LU-07 item 1).

    Pontuação, emoji e espaços não viram token — é isso que dá a fronteira
    de palavra: "acidentalmente" é UM token, nunca casa a keyword "acidente".
    """
    return _TOKEN_RE.findall(normalized_text)


def _find_positions(kw_tokens: list[str], tokens: list[str]) -> list[int]:
    """Índices de início onde a sequência kw_tokens aparece em tokens (contígua)."""
    n = len(kw_tokens)
    if n == 0 or n > len(tokens):
        return []
    return [i for i in range(len(tokens) - n + 1) if tokens[i : i + n] == kw_tokens]


def _clause_ids(normalized_text: str) -> list[int]:
    """Para cada token de PALAVRA, na mesma ordem/contagem de _tokenize(),
    devolve o índice da oração a que ele pertence (LU-07 fix wave 1, A2).

    A oração muda ao cruzar um caractere de CLAUSE_BOUNDARY_CHARS (não vira
    token de palavra, só incrementa o contador) ou uma palavra de
    CLAUSE_COORDINATING_CONJUNCTIONS (a própria conjunção fica na oração
    ANTERIOR — ela não é sintoma, então isso é indiferente para casamento de
    keyword; só a oração dela importa para o próximo token).
    """
    ids: list[int] = []
    clause = 0
    for match in _CLAUSE_TOKEN_RE.finditer(normalized_text):
        tok = match.group()
        if tok in _CLAUSE_BOUNDARY_SET:
            clause += 1
            continue
        ids.append(clause)
        if tok in _CLAUSE_CONJUNCTIONS_SET:
            clause += 1
    return ids


def _preceded_by_negation(
    tokens: list[str], clause_ids: list[int], start_idx: int
) -> bool:
    """True se algum NEGATION_TRIGGERS aparecer nos NEGATION_WINDOW_TOKENS
    tokens imediatamente antes de start_idx (janela curta, LU-07 item 2) —
    restrita à MESMA oração de start_idx (LU-07 fix wave 1, A2): a janela
    nunca inclui token de outra oração, mesmo dentro da distância de 3."""
    current_clause = clause_ids[start_idx]
    lo = max(0, start_idx - NEGATION_WINDOW_TOKENS)
    while lo < start_idx and clause_ids[lo] != current_clause:
        lo += 1
    window = tokens[lo:start_idx]
    for trigger in NEGATION_TRIGGERS:
        trigger_tokens = _tokenize(_normalize(trigger))
        if _find_positions(trigger_tokens, window):
            return True
    return False


@dataclass(frozen=True)
class TriageResult:
    """Resultado da classificação de triagem."""

    urgencia: str
    sintomas_detectados: list[str]
    score: int
    regras_versao: str = field(default=TRIAGE_RULES_VERSION)


class TriageEngine:
    """Classifica textos de tutores em níveis de urgência usando regras léxicas.

    Hierarquia: ALTA > MEDIA > BAIXA.
    O score acumula pontos de todos os níveis detectados para ordenação futura.

    v1.1 (LU-07): casamento por token (fronteira de palavra) em vez de
    substring, e negação com janela curta que anula MEDIA/BAIXA. ALTA é
    imune à negação — nunca afrouxamos ALTA para ganhar acurácia.
    """

    _LEVELS: list[tuple[str, dict[str, list[str]], int]] = [
        ("ALTA", SINTOMAS_ALTA_URGENCIA, _POINTS["ALTA"]),
        ("MEDIA", SINTOMAS_MEDIA_URGENCIA, _POINTS["MEDIA"]),
        ("BAIXA", SINTOMAS_BAIXA_URGENCIA, _POINTS["BAIXA"]),
    ]

    def classificar(self, texto: str) -> TriageResult:
        """Classifica o texto e retorna TriageResult com urgência, sintomas e score."""
        if not texto.strip():
            return TriageResult(
                urgencia="BAIXA",
                sintomas_detectados=[],
                score=0,
            )

        normalized_text = _normalize(texto)
        tokens = _tokenize(normalized_text)
        clause_ids = _clause_ids(normalized_text)
        all_sintomas: list[str] = []
        total_score = 0
        winning_level: str | None = None
        winning_sintomas: list[str] = []

        for level, rules_dict, pts in self._LEVELS:
            level_sintomas: list[str] = []
            for keywords in rules_dict.values():
                for kw in keywords:
                    if self._keyword_detectado(kw, tokens, clause_ids, level):
                        level_sintomas.append(kw)
                        total_score += pts
                        break  # conta cada categoria uma vez por nível

            if level_sintomas:
                all_sintomas.extend(level_sintomas)
                if winning_level is None:
                    winning_level = level
                    winning_sintomas = level_sintomas

        return TriageResult(
            urgencia=winning_level or "BAIXA",
            sintomas_detectados=winning_sintomas if winning_sintomas else all_sintomas,
            score=total_score,
        )

    def _keyword_detectado(
        self, kw: str, tokens: list[str], clause_ids: list[int], level: str
    ) -> bool:
        """True se `kw` casa em `tokens` (fronteira de palavra) e, para
        MEDIA/BAIXA, não estiver anulada por negação na janela curta (que não
        atravessa oração, LU-07 fix wave 1 A2).
        ALTA nunca é anulada por negação (ver triage_rules.py)."""
        kw_tokens = _tokenize(_normalize(kw))
        positions = _find_positions(kw_tokens, tokens)
        if not positions:
            return False
        if level == "ALTA":
            return True
        return any(
            not _preceded_by_negation(tokens, clause_ids, pos) for pos in positions
        )
