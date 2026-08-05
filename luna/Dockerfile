FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# FORÇA O PYTHON A LER A PASTA /app COMO RAIZ DOS MÓDULOS (Isso resolve o erro do src)
ENV PYTHONPATH=/app

# Instala dependências de sistema exigidas pelo OpenCV (YOLO)
# curl é exigido pelo healthcheck do docker-compose.yml (CMD-SHELL curl -f .../health)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Instala a CLI da Luna
RUN pip install -e .

EXPOSE 8000

# Inicia o servidor HTTP da Luna v2.0
CMD uvicorn src.web.app:app --host 0.0.0.0 --port 8000