FROM python:3.12-slim

# LU-06 (imagem enxuta): visão computacional (torch/ultralytics/opencv, ~9 GB) é extra opcional.
# Build padrão (WITH_VISION=false) fica < 800 MB; `--build-arg WITH_VISION=true` traz o pipeline
# de detecção de raça (`luna detect`) de volta, junto com libgl1/libglib2.0-0 (exigidas pelo
# OpenCV/YOLO em runtime — sem elas o import de cv2 falha com ImportError de shared library).
ARG WITH_VISION=false

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# FORÇA O PYTHON A LER A PASTA /app COMO RAIZ DOS MÓDULOS (Isso resolve o erro do src)
ENV PYTHONPATH=/app

# curl é exigido pelo healthcheck do docker-compose.yml (CMD-SHELL curl -f .../health).
# libgl1/libglib2.0-0 só entram no ramo com visão (WITH_VISION=true) — são as únicas libs de
# sistema que o build padrão não precisa mais.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && if [ "$WITH_VISION" = "true" ]; then \
         apt-get install -y --no-install-recommends libgl1 libglib2.0-0; \
       fi \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-vision.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$WITH_VISION" = "true" ]; then \
         pip install --no-cache-dir -r requirements-vision.txt; \
       fi

COPY . .

# Instala a CLI da Luna
RUN pip install -e .

# N8 (achado do G0, LU-06): o compose/ACI roda o container como UID 1000, mas a imagem é
# construída como root — /app (e um `luna.log` relativo a ele) fica ilegível/não-gravável para
# 1000, e `run-job`/`serve`/`detect` (que chamam setup_logging cedo) morriam em
# `ValueError: Unable to configure handler 'file'` antes de tocar o Oracle. logs/ gravável por
# 1000 resolve o caso comum; src/config/logging_config.py também cai para console-only se, ainda
# assim, a escrita falhar (defesa em profundidade — não depende só desta permissão de build).
RUN mkdir -p /app/logs && chown -R 1000:1000 /app/logs

EXPOSE 8000

# Inicia o servidor HTTP da Luna v2.0
CMD uvicorn src.web.app:app --host 0.0.0.0 --port 8000