# Luna — Comunicação Proativa & IA Veterinária

> Subprojeto do sistema **Kura / Clyvo Vet** · FIAP Challenge 2026

Luna é o serviço Python responsável pela comunicação proativa e visão computacional do Kura. Ele opera em dois eixos:

1. **Lembretes de vacinas via WhatsApp** — lê vacinas próximas do vencimento no Oracle, cria registros de notificação e dispara mensagens pelo Twilio Sandbox.
2. **Identificação de raça por foto** — detecta cão/gato com YOLOv8n, classifica a raça com MobileNetV3 e cruza com predisposições clínicas armazenadas no Oracle para gerar recomendação personalizada.

---

## Arquitetura resumida

```
luna detect foto.jpg          luna run-job
       │                             │
       ▼                             ▼
IdentificacaoRacaService    LembreteVacinaService
  PetDetector (YOLO)          VacinaRepository  ──► Oracle VW_VACINAS_VENCENDO
  BreedClassifier (MNet)      NotificacaoRepository ► Oracle NOTIFICACAO
  RecomendacaoCuidados ──►    TwilioGateway ────────► WhatsApp (Twilio)
    RacaRepository ──► Oracle RACA
```

Diagrama completo: [`docs/architecture.md`](docs/architecture.md)

---

## Pré-requisitos

| Requisito | Versão mínima |
|-----------|--------------|
| Python | 3.12 |
| Oracle 19c | thin mode (sem Instant Client) |
| Conta Twilio | WhatsApp Sandbox ativo |
| pip / pip-tools | qualquer recente |

> **Windows:** use `pyenv-win` ou o instalador oficial do Python 3.12 para garantir a versão correta.

---

## Instalação

```bash
# 1. Clonar / entrar no diretório
cd luna

# 2. Criar e ativar virtualenv
python3.12 -m venv .venv
source .venv/bin/activate          # Linux / macOS
.venv\Scripts\Activate.ps1        # Windows PowerShell

# 3. Instalar dependências (inclui dev tools)
pip install -r requirements-dev.txt

# 4. Instalar o pacote em modo editável (habilita o comando `luna`)
pip install -e .

# 5. Configurar variáveis de ambiente
cp .env.example .env
# Edite .env com suas credenciais (veja seção abaixo)
```

---

## Variáveis de ambiente (`.env`)

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `ORACLE_DSN` | Host:porta/service do Oracle | `db.host:1521/KURA` |
| `ORACLE_USER` | Usuário Oracle | `kura_luna` |
| `ORACLE_PASSWORD` | Senha Oracle | `•••` |
| `TWILIO_SID` | Account SID do Twilio | `ACxxxxxxxxxxxxxxx` |
| `TWILIO_TOKEN` | Auth Token do Twilio | `•••` |
| `TWILIO_FROM_NUMBER` | Número sandbox Twilio | `+14155238886` |
| `YOLO_WEIGHTS_PATH` | Caminho para `yolov8n.pt` | `src/ai/models/yolov8n.pt` |
| `BREED_CLASSIFIER_WEIGHTS_PATH` | Caminho para pesos MobileNetV3 | `src/ai/models/breed_classifier.pth` |
| `LOG_LEVEL` | Nível de log | `INFO` |

> Para baixar os pesos do YOLO: `python scripts/download_yolo_weights.py`

---

## Comandos CLI

Após `pip install -e .`, o comando `luna` fica disponível no PATH do virtualenv.

### `luna run-job` — Lembrete de vacinas (one-shot)

```bash
luna run-job
# Concluído — total: 12 | enviadas: 10 | falhas: 0 | já enviadas: 2
```

Executa imediatamente o ciclo de lembretes: lê vacinas com até 7 dias restantes, verifica idempotência (janela 24 h), cria notificação `PENDENTE`, dispara WhatsApp e marca `ENVIADA` ou `FALHA`.

> Para execução agendada (diária às 08h BRT), use `LembreteVacinaJob.iniciar_scheduler()` diretamente via Python.

### `luna detect <caminho>` — Identificação de raça

```bash
luna detect fotos/rex.jpg
# Pet detectado: Labrador Retriever (confiança: 91.3%)
#
# Recomendação clínica:
# Detectamos que seu pet é da raça *Labrador Retriever*. Raças desta
# linhagem têm predisposição a: displasia coxofemoral, obesidade.
# Recomendamos uma avaliação preventiva...
#
# Imagem anotada salva em: fotos/rex_anotada.jpg
```

Pipeline: detecta pets com YOLOv8n → classifica raça top-1 com MobileNetV3 (pt-BR) → busca predisposições no Oracle → exibe recomendação e salva imagem anotada com bounding box.

---

## Testes

```bash
# Suite completa
pytest

# Sem testes lentos (pula carregamento real de modelos)
pytest -m "not slow"

# Com cobertura
pytest --cov=src --cov-report=term-missing

# Apenas integração E2E
pytest tests/integration/
```

Cobertura mínima alvo: **85%** por módulo. Os testes nunca conectam ao Oracle nem ao Twilio real — tudo é mockado via `unittest.mock`.

---

## Estrutura do projeto

```
luna/
├── src/
│   ├── config/         # Settings (Pydantic) + logging
│   ├── db/
│   │   ├── connection.py        # Pool oracledb thin
│   │   ├── models/              # Dataclasses frozen
│   │   └── repositories/        # VacinaRepo, NotificacaoRepo, RacaRepo, LogErroRepo
│   ├── messaging/      # TwilioGateway (outbound) + twilio_inbound + templates
│   ├── ai/             # PetDetector (YOLO) + BreedClassifier + TriageEngine (v2)
│   ├── integration/    # IKuraClient + KuraClient (httpx) + DTOs + exceções (v2)
│   ├── services/       # LembreteVacinaService + IdentificacaoRacaService + InboundMessageService (v2)
│   ├── jobs/           # LembreteVacinaJob (APScheduler wrapper)
│   ├── web/            # FastAPI app factory + dependencies + routers (v2)
│   └── cli/            # main.py — Composition Root + Typer (run-job, detect, serve)
├── tests/
│   ├── unit/           # Testes isolados por camada
│   └── integration/    # E2E mockando Oracle, Twilio e API .NET via respx
├── docs/
│   ├── architecture.md  # Diagrama Mermaid detalhado
│   ├── runbook.md       # Subir servidor, ngrok, configurar Twilio (v2)
│   ├── api_contracts.md # Contratos REST esperados da API .NET (v2)
│   └── demo_script.md   # Roteiro de 5 min para banca FIAP
└── scripts/
    └── download_yolo_weights.py
```

---

## Modo servidor (v2.0)

A partir da v2.0, a Luna inclui um servidor FastAPI bidirecional para receber mensagens WhatsApp.

### Pré-requisitos adicionais

| Requisito | Descrição |
|---|---|
| ngrok | Para expor o servidor localmente durante desenvolvimento |
| API .NET Kura | URL e chave configuradas em `KURA_API_BASE_URL` e `KURA_API_KEY` |

### Variáveis de ambiente adicionais

| Variável | Descrição | Default |
|---|---|---|
| `KURA_API_BASE_URL` | URL base da API .NET | — (obrigatório) |
| `KURA_API_KEY` | Bearer token Luna → .NET | — (obrigatório) |
| `KURA_API_TIMEOUT` | Timeout HTTP (segundos) | `10` |
| `WEBHOOK_PUBLIC_URL` | URL pública do webhook (validação Twilio) | — (obrigatório) |
| `LUNA_HTTP_PORT` | Porta HTTP | `8000` |

### Subindo o servidor

```bash
# Inicia o servidor FastAPI
luna serve

# Opções avançadas
luna serve --host 0.0.0.0 --port 9000 --reload
```

### Fluxo inbound

```
Tutor WhatsApp → Twilio → POST /webhook/twilio/whatsapp
                                    │
                          Valida assinatura X-Twilio-Signature
                          Retorna TwiML <Response/> em < 200ms
                                    │ (BackgroundTask)
                          InboundMessageService.processar()
                            ├─ GET /api/tutores/telefone/{nr}  [.NET]
                            ├─ POST /api/luna/interactions     [.NET]
                            ├─ TriageEngine.classificar()      [local]
                            ├─ POST /api/luna/triage           [.NET]
                            └─ TwilioGateway.enviar_whatsapp() [outbound]
```

Guia completo: [`docs/runbook.md`](docs/runbook.md)
Contratos REST com o .NET: [`docs/api_contracts.md`](docs/api_contracts.md)

---

## Dependências principais

| Pacote | Uso |
|--------|-----|
| `oracledb` 2.4 | Oracle thin (sem Instant Client) |
| `pydantic-settings` 2.4 | Configuração via `.env` |
| `twilio` 9.3 | Envio e validação assinatura WhatsApp |
| `ultralytics` 8.3 | YOLOv8n — detecção dog/cat |
| `torch` + `torchvision` 2.4 | MobileNetV3 — classificação de raça |
| `opencv-python-headless` 4.10 | Anotação de bounding boxes |
| `typer` 0.12 | CLI |
| `APScheduler` 3.10 | Agendamento do job de vacinas |
| `fastapi` 0.115 | Servidor webhook (v2.0) |
| `uvicorn` 0.30 | ASGI server (v2.0) |
| `httpx` 0.27 | Cliente HTTP async para API .NET (v2.0) |
