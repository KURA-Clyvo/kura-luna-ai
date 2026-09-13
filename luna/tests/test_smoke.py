"""Smoke test: all modules importable without errors."""
import importlib

import pytest

# Módulos do núcleo — sempre importáveis, sem o extra requirements-vision.txt.
CORE_MODULES = [
    "src.config.settings",
    "src.config.logging_config",
    "src.db.connection",
    "src.db.models.vacina_vencendo",
    "src.db.models.notificacao",
    "src.db.models.raca",
    "src.db.repositories.vacina_repo",
    "src.db.repositories.notificacao_repo",
    "src.db.repositories.raca_repo",
    "src.db.repositories.log_erro_repo",
    "src.messaging.twilio_client",
    "src.messaging.templates",
    "src.ai.recommender",
    "src.ai.breed_labels_ptbr",
    "src.ai.deteccao",
    "src.services.notification_service",
    "src.services.resultado_identificacao",
    "src.jobs.lembrete_vacina_job",
    # LU-06: src.cli.main é núcleo — importa breed_service/breed_classifier/breed_detector de
    # forma preguiçosa (só dentro de _create_breed_service), então coleta e importa sem visão.
    "src.cli.main",
]

# Módulos que exigem o extra requirements-vision.txt (torch/ultralytics/opencv) — LU-06: visão
# computacional é opcional, não faz parte da instalação/imagem padrão.
VISION_MODULES = [
    "src.ai.breed_detector",
    "src.ai.breed_classifier",
    "src.services.breed_service",
]


def _vision_disponivel() -> bool:
    try:
        import cv2  # noqa: F401
        import torch  # noqa: F401
        import ultralytics  # noqa: F401
    except ImportError:
        return False
    return True


def test_all_modules_importable() -> None:
    for mod in CORE_MODULES:
        importlib.import_module(mod)


def test_vision_modules_importable_quando_extra_instalado() -> None:
    # Declarado, não silenciado (LU-06): sem requirements-vision.txt, este teste registra o skip
    # com motivo explícito em vez de sumir da suíte ou falhar por ModuleNotFoundError.
    if not _vision_disponivel():
        pytest.skip(
            "requirements-vision.txt não instalado (LU-06: visão computacional é extra "
            "opcional) — módulos de visão não verificados de importabilidade nesta suíte."
        )
    for mod in VISION_MODULES:
        importlib.import_module(mod)
