"""Composition root e CLI da Luna — comandos Typer."""
import logging
from typing import Optional

import typer

from src.config.logging_config import setup_logging
from src.config.settings import Settings
from src.db.connection import OracleConnectionPool

logger = logging.getLogger(__name__)

app = typer.Typer(name="luna", help="Luna — IA proativa para clínicas veterinárias Kura.")


def _create_lembrete_service() -> tuple["LembreteVacinaService", OracleConnectionPool]:
    """Composition root para o serviço de lembretes de vacinas."""
    from src.db.repositories.log_erro_repo import LogErroRepository
    from src.db.repositories.notificacao_repo import NotificacaoRepository
    from src.db.repositories.vacina_repo import VacinaRepository
    from src.messaging.twilio_client import TwilioGateway
    from src.services.notification_service import LembreteVacinaService

    settings = Settings()
    setup_logging(settings.LOG_LEVEL)
    pool = OracleConnectionPool(
        dsn=settings.ORACLE_DSN,
        user=settings.ORACLE_USER,
        password=settings.ORACLE_PASSWORD,
    )
    vacina_repo = VacinaRepository(pool)
    notificacao_repo = NotificacaoRepository(pool)
    log_repo = LogErroRepository(pool)
    gateway = TwilioGateway(
        account_sid=settings.TWILIO_SID,
        auth_token=settings.TWILIO_TOKEN,
        from_number=settings.TWILIO_FROM_NUMBER,
    )
    service = LembreteVacinaService(vacina_repo, notificacao_repo, gateway, log_repo)
    return service, pool


def _create_breed_service() -> tuple["IdentificacaoRacaService", OracleConnectionPool]:
    """Composition root para o serviço de identificação de raça."""
    from src.ai.breed_classifier import BreedClassifier
    from src.ai.breed_detector import PetDetector
    from src.ai.recommender import RecomendacaoCuidados
    from src.db.repositories.raca_repo import RacaRepository
    from src.services.breed_service import IdentificacaoRacaService

    settings = Settings()
    setup_logging(settings.LOG_LEVEL)
    pool = OracleConnectionPool(
        dsn=settings.ORACLE_DSN,
        user=settings.ORACLE_USER,
        password=settings.ORACLE_PASSWORD,
    )
    raca_repo = RacaRepository(pool)
    recommender = RecomendacaoCuidados(raca_repo)
    detector = PetDetector(settings.YOLO_WEIGHTS_PATH)
    classifier = BreedClassifier(settings.BREED_CLASSIFIER_WEIGHTS_PATH)
    service = IdentificacaoRacaService(detector, classifier, recommender)
    return service, pool


@app.command("run-job")
def run_job() -> None:
    """Executa o ciclo de lembretes de vacinas imediatamente (one-shot)."""
    pool: OracleConnectionPool | None = None
    try:
        service, pool = _create_lembrete_service()
        resumo = service.executar()
        typer.echo(
            f"Concluído — total: {resumo.total} | enviadas: {resumo.enviadas}"
            f" | falhas: {resumo.falhas} | já enviadas: {resumo.ja_enviadas}"
        )
    except Exception as exc:
        logger.exception("Erro fatal em run-job")
        typer.echo(f"Erro: {exc}", err=True)
        raise typer.Exit(code=1)
    finally:
        if pool is not None:
            pool.close()


@app.command("detect")
def detect(caminho: str) -> None:
    """Detecta a raça do pet na imagem e exibe recomendações clínicas."""
    pool: OracleConnectionPool | None = None
    try:
        service, pool = _create_breed_service()
        resultado = service.processar_foto(caminho)

        if not resultado.deteccoes:
            typer.echo("Nenhum pet detectado na imagem.")
            return

        raca = resultado.raca_top1 or "Desconhecida"
        conf = f"{resultado.confianca:.1%}" if resultado.confianca is not None else "N/A"
        typer.echo(f"Pet detectado: {raca} (confiança: {conf})")

        if resultado.recomendacao:
            typer.echo(f"\nRecomendação clínica:\n{resultado.recomendacao}")

        if resultado.imagem_anotada_path:
            typer.echo(f"\nImagem anotada salva em: {resultado.imagem_anotada_path}")
    except Exception as exc:
        logger.exception("Erro fatal em detect")
        typer.echo(f"Erro: {exc}", err=True)
        raise typer.Exit(code=1)
    finally:
        if pool is not None:
            pool.close()


@app.command("serve")
def serve(host: str = "0.0.0.0", port: Optional[int] = None, reload: bool = False) -> None:
    """Inicia o servidor HTTP FastAPI da Luna v2.0."""
    import uvicorn  # noqa: PLC0415 — lazy para não pesar run-job/detect
    from src.web.app import create_app  # noqa: PLC0415

    settings = Settings()
    setup_logging(settings.LOG_LEVEL)
    porta = port if port is not None else settings.LUNA_HTTP_PORT
    uvicorn.run(create_app(settings), host=host, port=porta, reload=reload)


def main() -> None:
    """Entry point da CLI Luna."""
    app()


if __name__ == "__main__":
    main()
