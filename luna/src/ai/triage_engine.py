"""Motor de triagem por regras para mensagens de tutores."""
import unicodedata
from dataclasses import dataclass, field

from src.ai.triage_rules import (
    SINTOMAS_ALTA_URGENCIA,
    SINTOMAS_BAIXA_URGENCIA,
    SINTOMAS_MEDIA_URGENCIA,
    TRIAGE_RULES_VERSION,
)

_POINTS: dict[str, int] = {"ALTA": 10, "MEDIA": 3, "BAIXA": 1}


def _normalize(text: str) -> str:
    """Lowercase + remove diacritics via NFKD decomposition."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


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
        all_sintomas: list[str] = []
        total_score = 0
        winning_level: str | None = None
        winning_sintomas: list[str] = []

        for level, rules_dict, pts in self._LEVELS:
            level_sintomas: list[str] = []
            for keywords in rules_dict.values():
                for kw in keywords:
                    if _normalize(kw) in normalized_text:
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
