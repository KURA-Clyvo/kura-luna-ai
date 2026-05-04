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
│   ├── messaging/      # TwilioGateway (Protocol + impl) + templates
│   ├── ai/             # PetDetector (YOLO) + BreedClassifier (MobileNetV3) + Recommender
│   ├── services/       # LembreteVacinaService + IdentificacaoRacaService
│   ├── jobs/           # LembreteVacinaJob (APScheduler wrapper)
│   └── cli/            # main.py — Composition Root + Typer
├── tests/
│   ├── unit/           # Testes isolados por camada
│   └── integration/    # E2E mockando só Oracle e Twilio
├── docs/
│   ├── architecture.md  # Diagrama Mermaid detalhado
│   └── demo_script.md   # Roteiro de 5 min para banca FIAP
└── scripts/
    └── download_yolo_weights.py
```

---

## Dependências principais

| Pacote | Uso |
|--------|-----|
| `oracledb` 2.4 | Oracle thin (sem Instant Client) |
| `pydantic-settings` 2.4 | Configuração via `.env` |
| `twilio` 9.3 | Envio WhatsApp Sandbox |
| `ultralytics` 8.3 | YOLOv8n — detecção dog/cat |
| `torch` + `torchvision` 2.4 | MobileNetV3 — classificação de raça |
| `opencv-python-headless` 4.10 | Anotação de bounding boxes |
| `typer` 0.12 | CLI |
| `APScheduler` 3.10 | Agendamento do job de vacinas |
