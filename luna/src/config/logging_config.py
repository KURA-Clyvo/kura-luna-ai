"""Logging configuration via dictConfig."""
import logging
import logging.config
import re

# TASK-72 (LGPD): o log INFO nativo do httpx ("HTTP Request: %s %s ...")
# imprime a URL completa de cada chamada — inclusive GET /api/v1/tutores/
# telefone/{numero}, que carrega o telefone do tutor (dado pessoal) no
# path. Lista pequena e explícita de propósito, mesmo padrão do
# `SegmentosSensiveis`/`RedigirPathSensivel` já usado do lado .NET
# (TASK-67, ExceptionHandlerMiddleware.cs) — quem adicionar uma rota nova
# com PII no path (ex.: .../cpf/{numero}) precisa lembrar de somar aqui.
_MARCADORES_PATH_SENSIVEL = ("/tutores/telefone/",)


class RedigirUrlSensivelFilter(logging.Filter):
    """Redige o segmento sensível da URL nos registros do logger ``httpx``.

    httpx loga em INFO, para cada request, algo como::

        HTTP Request: GET http://host/api/v1/tutores/telefone/5511999998888 "HTTP/1.1 200 OK"

    (ver ``httpx._client.Client._send_single_request`` /
    ``AsyncClient._send_single_request``: ``logger.info('HTTP Request: %s %s
    "%s %d %s"', method, url, http_version, status_code, reason_phrase)``).

    Em vez de silenciar o logger ``httpx`` inteiro — o que apagaria também o
    método, o status e a versão HTTP de *toda* chamada, inclusive as que não
    têm PII (``registrar_interacao``, ``registrar_triagem``, ``verificar_saude``,
    e os próprios 4xx/5xx de ``buscar_tutor_por_telefone``) — este filtro
    redige só o trecho sensível de cada argumento posicional do registro,
    preservando o resto para diagnóstico. Mesma decisão de design do lado
    .NET (redigir, não silenciar), adaptada ao mecanismo de filtro do
    ``logging`` padrão do Python em vez de replicar a implementação C#.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._redigir(v) for k, v in record.args.items()}
            else:
                record.args = tuple(self._redigir(v) for v in record.args)
        return True

    @staticmethod
    def _redigir(valor: object) -> object:
        """Redige `valor` se ele contiver um marcador sensível; senão devolve
        o objeto original intacto (mesmo tipo) — importante para não quebrar
        a formatação `%d` do status_code caso ele passe por aqui."""
        texto = str(valor)
        redigido = texto
        for marcador in _MARCADORES_PATH_SENSIVEL:
            if marcador in redigido:
                redigido = re.sub(re.escape(marcador) + r'[^\s"]+', marcador + "{redacted}", redigido)
        return redigido if redigido != texto else valor


def setup_logging(level: str = "INFO") -> None:
    """Configure application logging with console and file handlers."""
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            },
        },
        "filters": {
            "redigir_url_sensivel": {
                "()": "src.config.logging_config.RedigirUrlSensivelFilter",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "standard",
                "filename": "luna.log",
                "maxBytes": 10_485_760,
                "backupCount": 3,
                "encoding": "utf-8",
            },
        },
        "root": {
            "level": level,
            "handlers": ["console", "file"],
        },
        "loggers": {
            # TASK-72: filtro aplicado no logger "httpx" em si (não nas
            # handlers) — roda uma única vez antes do record propagar para
            # os handlers do root, e não exige handlers próprios aqui.
            "httpx": {
                "level": level,
                "filters": ["redigir_url_sensivel"],
                "propagate": True,
            },
        },
    }
    logging.config.dictConfig(config)
