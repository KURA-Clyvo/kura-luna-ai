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
#
# Reaproveitada em dois pontos, deliberadamente: aqui, pelo filtro do logger
# "httpx" (abaixo); e em `src.integration.kura_client`, para sanitizar a
# mensagem de `httpx.HTTPStatusError` antes que ela suba para quem loga
# (`inbound_message_service.logger.exception`) ou grave em `LOG_ERRO` — achado
# 1 do fix round 1 da TASK-72: o filtro de log só via os `record.args` do
# logger "httpx"; a exceção que `resp.raise_for_status()` levanta para
# qualquer 4xx não tratado (ex.: 401 de API key errada) embute a URL completa
# como *texto literal na mensagem da exceção*, um caminho que o filtro nunca
# alcança. Ver `kura_client.KuraClient._levantar_erro_sanitizado`.
_MARCADORES_PATH_SENSIVEL = ("/tutores/telefone/",)


def redigir_url_sensivel(texto: str) -> str:
    """Redige o(s) segmento(s) sensível(is) de `texto`, se presentes.

    Devolve `texto` inalterado quando nenhum marcador de `_MARCADORES_PATH_SENSIVEL`
    aparece. Função pura, sem efeito colateral — ponto único de verdade sobre
    "o que é sensível numa URL da Luna", usado tanto pelo filtro de log do
    httpx quanto pelo `KuraClient` para sanitizar mensagens de exceção.
    """
    redigido = texto
    for marcador in _MARCADORES_PATH_SENSIVEL:
        if marcador in redigido:
            redigido = re.sub(re.escape(marcador) + r'[^\s"]+', marcador + "{redacted}", redigido)
    return redigido


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

    Escopo confirmado por verificação empírica (fix round 1 da TASK-72, achado
    3): ``httpcore`` (transporte usado por baixo do httpx) tem loggers
    próprios (``httpcore.connection``, ``httpcore.http11``) que só emitem em
    DEBUG. Rodei uma chamada httpx real (TCP de verdade contra um servidor
    HTTP local — respx intercepta no nível de transporte e nunca chega no
    httpcore, então não serve para testar isto) com o root em DEBUG e
    inspecionei literalmente cada `LogRecord` emitido: no httpcore 1.0.9
    (versão instalada, não pinada em requirements.txt), ``httpcore.connection``
    só loga host/port (``connect_tcp.started host='127.0.0.1' port=... ...``)
    e ``httpcore.http11`` só loga ``<Request [b'GET']>`` (``Request.__repr__``
    devolve só o método, nunca a URL — ver ``httpcore._models.Request.__repr__``).
    Nenhum dos dois inclui o path da request em lugar nenhum do payload de
    DEBUG — logo, nenhum dos dois vaza o telefone. Só o logger ``httpx`` em si
    leva a URL completa, e só em INFO. Por isso este filtro não foi estendido
    para ``httpcore.*``: não há vazamento real para cobrir hoje, e adicionar
    filtro num logger que não vaza nada seria diff sem função, verificável só
    por leitura, não por reprodução. Se uma versão futura do httpcore mudar
    `Trace`/`Request.__repr__` para incluir a URL, isto precisa ser revisto.
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
        redigido = redigir_url_sensivel(texto)
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
