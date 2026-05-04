"""Smoke test: all modules importable without errors."""
import importlib


MODULES = [
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
    "src.ai.breed_detector",
    "src.ai.breed_classifier",
    "src.ai.recommender",
    "src.ai.breed_labels_ptbr",
    "src.services.notification_service",
    "src.services.breed_service",
    "src.jobs.lembrete_vacina_job",
    "src.cli.main",
]


def test_all_modules_importable() -> None:
    for mod in MODULES:
        importlib.import_module(mod)
