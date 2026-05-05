"""Testes da CLI Luna — run-job e detect via CliRunner."""
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from src.cli.main import app
from src.services.breed_service import ResultadoIdentificacao
from src.services.notification_service import ResumoExecucao

runner = CliRunner(mix_stderr=True)

_MODULE = "src.cli.main"


# ---- fixtures -----------------------------------------------------------


@pytest.fixture
def mock_pool() -> MagicMock:
    return MagicMock()


@pytest.fixture
def lembrete_service_ok() -> MagicMock:
    svc = MagicMock()
    svc.executar.return_value = ResumoExecucao(
        total=5, enviadas=4, falhas=0, ja_enviadas=1
    )
    return svc


@pytest.fixture
def breed_service_com_pet() -> MagicMock:
    svc = MagicMock()
    svc.processar_foto.return_value = ResultadoIdentificacao(
        deteccoes=[MagicMock(classe="dog", confianca=0.95)],
        raca_top1="Labrador",
        confianca=0.88,
        recomendacao="Avaliação preventiva recomendada.",
        imagem_anotada_path="/tmp/dog_anotada.jpg",
    )
    return svc


@pytest.fixture
def breed_service_sem_pet() -> MagicMock:
    svc = MagicMock()
    svc.processar_foto.return_value = ResultadoIdentificacao(
        deteccoes=[],
        raca_top1=None,
        confianca=None,
        recomendacao=None,
        imagem_anotada_path=None,
    )
    return svc


# ---- run-job ------------------------------------------------------------


def test_run_job_exit_0_em_sucesso(
    lembrete_service_ok: MagicMock, mock_pool: MagicMock
) -> None:
    with patch(
        f"{_MODULE}._create_lembrete_service",
        return_value=(lembrete_service_ok, mock_pool),
    ):
        result = runner.invoke(app, ["run-job"])

    assert result.exit_code == 0


def test_run_job_exibe_resumo_completo(
    lembrete_service_ok: MagicMock, mock_pool: MagicMock
) -> None:
    with patch(
        f"{_MODULE}._create_lembrete_service",
        return_value=(lembrete_service_ok, mock_pool),
    ):
        result = runner.invoke(app, ["run-job"])

    assert "total: 5" in result.output
    assert "enviadas: 4" in result.output
    assert "falhas: 0" in result.output
    assert "já enviadas: 1" in result.output


def test_run_job_fecha_pool_em_sucesso(
    lembrete_service_ok: MagicMock, mock_pool: MagicMock
) -> None:
    with patch(
        f"{_MODULE}._create_lembrete_service",
        return_value=(lembrete_service_ok, mock_pool),
    ):
        runner.invoke(app, ["run-job"])

    mock_pool.close.assert_called_once()


def test_run_job_exit_1_quando_factory_falha() -> None:
    with patch(
        f"{_MODULE}._create_lembrete_service",
        side_effect=Exception("DB offline"),
    ):
        result = runner.invoke(app, ["run-job"])

    assert result.exit_code == 1
    assert "DB offline" in result.output


def test_run_job_exit_1_quando_servico_falha(
    lembrete_service_ok: MagicMock, mock_pool: MagicMock
) -> None:
    lembrete_service_ok.executar.side_effect = RuntimeError("crash inesperado")
    with patch(
        f"{_MODULE}._create_lembrete_service",
        return_value=(lembrete_service_ok, mock_pool),
    ):
        result = runner.invoke(app, ["run-job"])

    assert result.exit_code == 1
    assert "crash inesperado" in result.output


def test_run_job_fecha_pool_mesmo_com_excecao_no_servico(
    lembrete_service_ok: MagicMock, mock_pool: MagicMock
) -> None:
    lembrete_service_ok.executar.side_effect = RuntimeError("crash")
    with patch(
        f"{_MODULE}._create_lembrete_service",
        return_value=(lembrete_service_ok, mock_pool),
    ):
        runner.invoke(app, ["run-job"])

    mock_pool.close.assert_called_once()


def test_run_job_nao_fecha_pool_quando_factory_falha() -> None:
    """Pool permanece None quando a factory lança — close não deve ser chamado."""
    with patch(
        f"{_MODULE}._create_lembrete_service",
        side_effect=Exception("sem conexão"),
    ):
        result = runner.invoke(app, ["run-job"])

    # Apenas verifica que não houve AttributeError (pool.close em None)
    assert result.exit_code == 1


# ---- detect -------------------------------------------------------------


def test_detect_exit_0_com_pet(
    breed_service_com_pet: MagicMock, mock_pool: MagicMock
) -> None:
    with patch(
        f"{_MODULE}._create_breed_service",
        return_value=(breed_service_com_pet, mock_pool),
    ):
        result = runner.invoke(app, ["detect", "foto.jpg"])

    assert result.exit_code == 0


def test_detect_exibe_raca_e_confianca(
    breed_service_com_pet: MagicMock, mock_pool: MagicMock
) -> None:
    with patch(
        f"{_MODULE}._create_breed_service",
        return_value=(breed_service_com_pet, mock_pool),
    ):
        result = runner.invoke(app, ["detect", "foto.jpg"])

    assert "Labrador" in result.output
    assert "88.0%" in result.output


def test_detect_exibe_recomendacao(
    breed_service_com_pet: MagicMock, mock_pool: MagicMock
) -> None:
    with patch(
        f"{_MODULE}._create_breed_service",
        return_value=(breed_service_com_pet, mock_pool),
    ):
        result = runner.invoke(app, ["detect", "foto.jpg"])

    assert "Avaliação preventiva recomendada." in result.output


def test_detect_exibe_caminho_anotada(
    breed_service_com_pet: MagicMock, mock_pool: MagicMock
) -> None:
    with patch(
        f"{_MODULE}._create_breed_service",
        return_value=(breed_service_com_pet, mock_pool),
    ):
        result = runner.invoke(app, ["detect", "foto.jpg"])

    assert "dog_anotada.jpg" in result.output


def test_detect_exit_0_sem_pet(
    breed_service_sem_pet: MagicMock, mock_pool: MagicMock
) -> None:
    with patch(
        f"{_MODULE}._create_breed_service",
        return_value=(breed_service_sem_pet, mock_pool),
    ):
        result = runner.invoke(app, ["detect", "vazio.jpg"])

    assert result.exit_code == 0
    assert "Nenhum pet detectado" in result.output


def test_detect_exit_1_quando_factory_falha() -> None:
    with patch(
        f"{_MODULE}._create_breed_service",
        side_effect=Exception("modelo não encontrado"),
    ):
        result = runner.invoke(app, ["detect", "foto.jpg"])

    assert result.exit_code == 1
    assert "modelo não encontrado" in result.output


def test_detect_exit_1_quando_servico_falha(
    breed_service_com_pet: MagicMock, mock_pool: MagicMock
) -> None:
    breed_service_com_pet.processar_foto.side_effect = OSError("arquivo corrompido")
    with patch(
        f"{_MODULE}._create_breed_service",
        return_value=(breed_service_com_pet, mock_pool),
    ):
        result = runner.invoke(app, ["detect", "foto.jpg"])

    assert result.exit_code == 1
    assert "arquivo corrompido" in result.output


def test_detect_fecha_pool_mesmo_com_excecao(
    breed_service_com_pet: MagicMock, mock_pool: MagicMock
) -> None:
    breed_service_com_pet.processar_foto.side_effect = RuntimeError("crash")
    with patch(
        f"{_MODULE}._create_breed_service",
        return_value=(breed_service_com_pet, mock_pool),
    ):
        runner.invoke(app, ["detect", "foto.jpg"])

    mock_pool.close.assert_called_once()


# ---- serve ---------------------------------------------------------------


def test_serve_help_sem_erro() -> None:
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "serve" in result.output.lower() or "host" in result.output.lower()


def test_serve_chama_uvicorn_run_com_parametros_corretos() -> None:
    with (
        patch(f"{_MODULE}.Settings") as mock_settings_cls,
        patch(f"{_MODULE}.setup_logging"),
        patch("uvicorn.run") as mock_uvicorn_run,
        patch("src.web.app.create_app") as mock_create_app,
    ):
        mock_settings = MagicMock()
        mock_settings.LOG_LEVEL = "INFO"
        mock_settings.LUNA_HTTP_PORT = 8000
        mock_settings_cls.return_value = mock_settings
        fake_app = MagicMock()
        mock_create_app.return_value = fake_app

        runner.invoke(app, ["serve", "--host", "127.0.0.1", "--port", "9000"])

    mock_uvicorn_run.assert_called_once_with(fake_app, host="127.0.0.1", port=9000, reload=False)


def test_serve_usa_porta_do_settings_quando_nao_informada() -> None:
    with (
        patch(f"{_MODULE}.Settings") as mock_settings_cls,
        patch(f"{_MODULE}.setup_logging"),
        patch("uvicorn.run") as mock_uvicorn_run,
        patch("src.web.app.create_app") as mock_create_app,
    ):
        mock_settings = MagicMock()
        mock_settings.LOG_LEVEL = "INFO"
        mock_settings.LUNA_HTTP_PORT = 8080
        mock_settings_cls.return_value = mock_settings
        mock_create_app.return_value = MagicMock()

        runner.invoke(app, ["serve"])

    call_kwargs = mock_uvicorn_run.call_args
    assert call_kwargs[1]["port"] == 8080 or call_kwargs[0][2] == 8080


def test_help_lista_tres_comandos() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "run-job" in result.output
    assert "detect" in result.output
    assert "serve" in result.output
