"""Testes do AsyncIOScheduler no lifespan (LU-04).

`LUNA_SCHEDULER_ENABLED=true` -> 1 job registrado (`app.state.scheduler`
não-None, com 1 job). `false` (default) -> nenhum scheduler criado.
Mordida: inverter a checagem da flag (`if not settings.LUNA_SCHEDULER_ENABLED`)
faz este teste falhar nominalmente (0 jobs quando deveria haver 1, e
vice-versa).
"""
from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.web.app import create_app


def _settings(
    scheduler_enabled: bool, confirmacao_d1_enabled: bool = False
) -> Settings:
    return Settings(
        ORACLE_DSN="test:1521/TEST",
        ORACLE_USER="test",
        ORACLE_PASSWORD="test",
        TWILIO_SID="ACtest",
        TWILIO_TOKEN="test_token",
        TWILIO_FROM_NUMBER="+14155238886",
        YOLO_WEIGHTS_PATH="test.pt",
        BREED_CLASSIFIER_WEIGHTS_PATH="test.pth",
        KURA_API_BASE_URL="http://kura-test.local",
        KURA_API_KEY="test-key",
        WEBHOOK_PUBLIC_URL="https://test.ngrok.io/webhook/twilio/whatsapp",
        LUNA_SCHEDULER_ENABLED=scheduler_enabled,
        LUNA_SCHEDULER_HORA=9,
        LEMBRETE_CONFIRMACAO_HABILITADO=confirmacao_d1_enabled,
        LEMBRETE_CONFIRMACAO_HORA=10,
        _env_file=None,  # type: ignore[call-arg]
    )


def test_scheduler_desligado_por_padrao_nao_registra_job() -> None:
    settings = _settings(scheduler_enabled=False)
    app = create_app(settings)

    with TestClient(app, raise_server_exceptions=False):
        assert app.state.scheduler is None


def test_scheduler_ligado_registra_exatamente_1_job() -> None:
    settings = _settings(scheduler_enabled=True)
    app = create_app(settings)

    with TestClient(app, raise_server_exceptions=False):
        assert app.state.scheduler is not None
        jobs = app.state.scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "lembrete_vacina"
        # cron configurado com LUNA_SCHEDULER_HORA (9 aqui, não o default 8)
        assert "hour='9'" in str(jobs[0].trigger)


def test_scheduler_encerra_no_shutdown_do_lifespan() -> None:
    settings = _settings(scheduler_enabled=True)
    app = create_app(settings)

    with TestClient(app, raise_server_exceptions=False):
        scheduler = app.state.scheduler
        assert scheduler.running is True

    assert scheduler.running is False


def test_lock_lembrete_sempre_existe_mesmo_com_scheduler_desligado() -> None:
    """O gatilho manual (POST /jobs/lembrete-vacina/executar) precisa do lock
    mesmo com o scheduler desligado -- ele é criado incondicionalmente."""
    settings = _settings(scheduler_enabled=False)
    app = create_app(settings)

    with TestClient(app, raise_server_exceptions=False):
        assert hasattr(app.state, "lembrete_lock")
        assert app.state.lembrete_lock.locked() is False


# ── REC-16 — scheduler de confirmação D-1 ───────────────────────────────────

def test_confirmacao_d1_desligado_por_padrao_nao_registra_job() -> None:
    settings = _settings(scheduler_enabled=False, confirmacao_d1_enabled=False)
    app = create_app(settings)

    with TestClient(app, raise_server_exceptions=False):
        assert app.state.scheduler is None


def test_confirmacao_d1_ligado_registra_exatamente_1_job() -> None:
    settings = _settings(scheduler_enabled=False, confirmacao_d1_enabled=True)
    app = create_app(settings)

    with TestClient(app, raise_server_exceptions=False):
        assert app.state.scheduler is not None
        jobs = app.state.scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "confirmacao_d1"
        assert "hour='10'" in str(jobs[0].trigger)


def test_confirmacao_d1_e_vacina_juntos_registram_2_jobs_independentes() -> None:
    settings = _settings(scheduler_enabled=True, confirmacao_d1_enabled=True)
    app = create_app(settings)

    with TestClient(app, raise_server_exceptions=False):
        jobs = {job.id for job in app.state.scheduler.get_jobs()}
        assert jobs == {"lembrete_vacina", "confirmacao_d1"}


def test_store_de_pendencias_sempre_existe_mesmo_com_flag_desligada() -> None:
    """G0 item 11 -- o PendenciaConfirmacaoStore é criado SEMPRE (igual ao
    lembrete_lock), independente da flag. Com a flag desligada ele apenas
    nunca é populado (o job nunca roda)."""
    from src.services.pendencia_confirmacao_store import PendenciaConfirmacaoStore

    settings = _settings(scheduler_enabled=False, confirmacao_d1_enabled=False)
    app = create_app(settings)

    with TestClient(app, raise_server_exceptions=False):
        assert hasattr(app.state, "confirmacao_pendentes")
        assert isinstance(app.state.confirmacao_pendentes, PendenciaConfirmacaoStore)
        assert hasattr(app.state, "confirmacao_d1_lock")
        assert app.state.confirmacao_d1_lock.locked() is False
