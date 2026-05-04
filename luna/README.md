# Luna — Comunicação Proativa & IA | Kura Vet (FIAP Challenge 2026)

Luna é o serviço Python responsável por notificações proativas e visão computacional do sistema Kura (Clyvo Vet). Envia lembretes de vacinas via WhatsApp (Twilio) e identifica raças de pets por foto usando YOLOv8 + MobileNetV3.

## Pré-requisitos

- Python 3.12+
- Acesso ao Oracle 19c (modo thin — sem Instant Client)
- Conta Twilio com WhatsApp Sandbox ativo
- pip

## Instalação

```bash
cd luna
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
# Edite .env com suas credenciais
```

## Comandos

```bash
# Detectar raça em uma foto
python -m src.cli.main detect caminho/para/foto.jpg

# Disparar job de lembrete de vacinas manualmente
python -m src.cli.main run-job
```

## Testes

```bash
pytest                          # todos os testes
pytest -m "not slow"            # pula testes com modelos reais
pytest --cov=src --cov-report=term-missing
```
