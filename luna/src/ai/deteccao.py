"""Deteccao — DTO de uma detecção YOLOv8.

Extraído de `breed_detector.py` (LU-06 — imagem enxuta) para que consumidores que só precisam do
*formato* do resultado de detecção — a CLI, seus testes, o serviço de identificação de raça —
possam importar este tipo sem carregar `ultralytics`/`torch`. `breed_detector.py` continua sendo o
dono da lógica real (e continua importando `ultralytics` no nível do módulo); este módulo reexporta
`Deteccao` a partir de lá para manter `from src.ai.breed_detector import Deteccao` funcionando.
"""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Deteccao:
    """Resultado de uma detecção YOLOv8."""

    classe: str
    confianca: float
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
