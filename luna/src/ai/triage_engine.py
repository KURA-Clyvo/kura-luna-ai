"""Motor de triagem por regras para mensagens de tutores."""
import re
import unicodedata
from dataclasses import dataclass, field

from src.ai.triage_rules import (
    NEGATION_TRIGGERS,
    NEGATION_WINDOW_TOKENS,
    SINTOMAS_ALTA_URGENCIA,
    SINTOMAS_BAIXA_URGENCIA,
    SINTOMAS_MEDIA_URGENCIA,
    TRIAGE_RULES_VERSION,
)

_POINTS: dict[str, int] = {"ALTA": 10, "MEDIA": 3, "BAIXA": 1}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


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


def _preceded_by_negation(tokens: list[str], start_idx: int) -> bool:
    """True se algum NEGATION_TRIGGERS aparecer nos NEGATION_WINDOW_TOKENS
    tokens imediatamente antes de start_idx (janela curta, LU-07 item 2)."""
    window = tokens[max(0, start_idx - NEGATION_WINDOW_TOKENS) : start_idx]
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
        all_sintomas: list[str] = []
        total_score = 0
        winning_level: str | None = None
        winning_sintomas: list[str] = []

        for level, rules_dict, pts in self._LEVELS:
            level_sintomas: list[str] = []
            for keywords in rules_dict.values():
                for kw in keywords:
                    if self._keyword_detectado(kw, tokens, level):
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

    def _keyword_detectado(self, kw: str, tokens: list[str], level: str) -> bool:
        """True se `kw` casa em `tokens` (fronteira de palavra) e, para
        MEDIA/BAIXA, não estiver anulada por negação na janela curta.
        ALTA nunca é anulada por negação (ver triage_rules.py)."""
        kw_tokens = _tokenize(_normalize(kw))
        positions = _find_positions(kw_tokens, tokens)
        if not positions:
            return False
        if level == "ALTA":
            return True
        return any(not _preceded_by_negation(tokens, pos) for pos in positions)
