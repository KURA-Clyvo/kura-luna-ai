"""ResultadoIdentificacao — DTO do pipeline foto → raça → recomendação.

Extraído de `breed_service.py` (LU-06 — imagem enxuta) pelo mesmo motivo de `src/ai/deteccao.py`:
`breed_service.py` importa `cv2`/`numpy` no nível do módulo, e a CLI (`tests/unit/cli/test_main.py`)
precisa deste DTO só para montar fixtures de `detect` mockado — sem precisar do extra
`requirements-vision.txt` instalado. `breed_service.py` reexporta este tipo para manter
`from src.services.breed_service import ResultadoIdentificacao` funcionando.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.ai.deteccao import Deteccao


@dataclass(frozen=True, slots=True)
class ResultadoIdentificacao:
    """Resultado completo do pipeline foto → raça → recomendação."""

    deteccoes: list["Deteccao"]
    raca_top1: str | None
    confianca: float | None
    recomendacao: str | None
    imagem_anotada_path: str | None
