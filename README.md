# Kura / Clyvo Vet — Luna AI Service

> **FIAP Challenge 2026** · Backend Python do sistema de gestão veterinária Kura

Este repositório contém o microserviço **Luna** — responsável pela comunicação proativa e IA veterinária do sistema Kura.

---

## O que é a Luna

Luna é o serviço Python que opera em dois eixos independentes:

1. **Lembretes de vacinas via WhatsApp** — lê vacinas próximas do vencimento no Oracle, cria registros de notificação e dispara mensagens pelo Twilio Sandbox.
2. **Identificação de raça por foto** — detecta cão/gato com YOLOv8n, classifica a raça com MobileNetV3 e retorna recomendações clínicas.
3. **Recepção bidirecional de mensagens (v2.0)** — servidor FastAPI recebe mensagens WhatsApp, classifica urgência por triagem de sintomas e aciona o time veterinário.

---

## Estrutura do repositório

```
kura-luna-ai/
└── luna/               ← subprojeto Python (todo o código está aqui)
    ├── src/
    ├── tests/
    ├── docs/
    ├── requirements.txt
    ├── pyproject.toml
    └── README.md        ← documentação detalhada do subprojeto
```

Todo o código, testes e documentação técnica residem em [`luna/`](luna/).

---

## Quick start

```powershell
cd luna
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pip install -e .
cp .env.example .env   # preencher com credenciais
```

Consulte [`luna/README.md`](luna/README.md) para instruções completas de instalação, variáveis de ambiente e uso da CLI.

---

## Documentação

| Documento | Conteúdo |
|---|---|
| [`luna/README.md`](luna/README.md) | Instalação, CLI, testes, dependências |
| [`luna/docs/architecture.md`](luna/docs/architecture.md) | Diagramas Mermaid da arquitetura |
| [`luna/docs/runbook.md`](luna/docs/runbook.md) | Subir servidor, ngrok, configurar Twilio (v2.0) |
| [`luna/docs/api_contracts.md`](luna/docs/api_contracts.md) | Contratos REST esperados da API .NET |
| [`luna/docs/demo_script.md`](luna/docs/demo_script.md) | Roteiro de demonstração para a banca FIAP |
