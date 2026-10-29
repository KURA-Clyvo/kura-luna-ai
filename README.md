# Kura / Clyvo Vet — Luna AI Service

> **FIAP Challenge 2026** · Backend Python do sistema de gestão veterinária Kura

Este repositório contém o microserviço **Luna** — responsável pela comunicação proativa e IA veterinária do sistema Kura.

---

## O que é a Luna

Luna é o serviço Python que opera em dois eixos independentes:

1. **Lembretes de vacinas via WhatsApp** — lê vacinas próximas do vencimento no Oracle, cria registros de notificação e dispara mensagens pelo Twilio Sandbox.
2. **Identificação de raça por foto** — 🟡 extra opcional (`--build-arg WITH_VISION=true`), fora da imagem padrão. Detecta cão/gato com YOLOv8n, classifica a raça com MobileNetV3 e retorna recomendações clínicas — ver `luna/README.md` e `luna/docs/IA_DEFINICAO.md` §9.2.
3. **Recepção bidirecional de mensagens (v2.0)** — servidor FastAPI recebe mensagens WhatsApp, classifica urgência por triagem de sintomas e aciona o time veterinário.

---

## Tecnologias utilizadas

Cada linha foi conferida contra `luna/requirements.txt`, `luna/Dockerfile` e o código em `luna/src/`.

| Tecnologia | Versão / fonte | Para que serve aqui |
|---|---|---|
| Python | 3.12 (`luna/Dockerfile`: `python:3.12-slim`; `pyproject.toml`: `requires-python >= 3.12`) | Linguagem do serviço |
| FastAPI + Uvicorn | `fastapi==0.115.0`, `uvicorn==0.30.6` (`src/web/app.py`) | API HTTP: webhook do Twilio, `/transcricao`, `/health`, jobs |
| Twilio WhatsApp | `twilio==9.3.2` (`src/messaging/twilio_client.py`) | Envio e recepção de mensagens (sandbox) |
| OpenAI Whisper (API) | `whisper-1` via `httpx` (`src/services/transcricao_service.py`) | Transcrição do áudio da consulta; **exige `OPENAI_API_KEY`** |
| Motor de regras próprio | `src/ai/triage_rules.py`, `src/ai/triage_engine.py` (regras v1.4) | Triagem de urgência por léxico, sem LLM e com explicação do porquê |
| Estruturação SOAP | `src/services/transcricao_service.py` (`montar_soap_draft`) | Texto transcrito vira rascunho SOAP; o veterinário confirma antes de salvar |
| APScheduler | `APScheduler==3.10.4` (`AsyncIOScheduler` em `src/web/app.py`) | Jobs de lembrete de vacina e de confirmação D-1 |
| httpx | `httpx==0.27.2` (`src/integration/kura_client.py`) | Cliente da API .NET (`/api/v1/luna/*`) |
| Oracle (`oracledb`) | `oracledb==2.4.1` | Leitura de vacinas e gravação de notificações e de `LOG_ERRO` |
| Pydantic | `pydantic==2.8.2` | DTOs do contrato e configuração |
| pytest | `pytest==8.3.3`, `pytest-asyncio==0.24.0` (`requirements-dev.txt`) | Testes unitários, de contrato e de integração |
| Docker | `luna/Dockerfile` (imagem padrão sem visão computacional) | Empacotamento do serviço |
| Visão computacional (opcional) | `luna/requirements-vision.txt` (YOLOv8n + MobileNetV3), `--build-arg WITH_VISION=true` | Extra fora da imagem padrão; **sem checkpoint de raça** (ver "Limites") |

---

## Resultados e avaliação

**Regra desta seção: os dois corpora aparecem sempre juntos.** Um número isolado de qualquer um deles engana.

| Corpus | Regras | Resultado | Quem escreveu |
|---|---|---|---|
| Corpus do time (`luna/tests/fixtures/triagem_corpus_v1.jsonl`) | v1.4 | 150 mensagens, acurácia 99,3% (149/150), subtriagem de ALTA 0/77 | O próprio time, que conhecia as palavras-chave. **Mede aderência às regras, não segurança clínica.** |
| Conjunto cego (61 mensagens, 35 rotuladas ALTA) | v1.4 | **2 de 35 ALTA reconhecidas**; 33 caíram em BAIXA. Dentro das categorias do motor: 2/27 reconhecidas; fora: 0/8 | Um revisor que ainda não tinha visto o código do motor. Rótulos dele, não de veterinário. |

- O conjunto cego deu o mesmo resultado nas regras v1.0, v1.3 e v1.4. As revisões de vocabulário não melhoraram a cobertura de mensagens escritas por quem não conhecia as palavras-chave.
- **Rede de segurança:** toda resposta que não é ALTA leva a orientação de emergência (`_ORIENTACAO_EMERGENCIA`, `luna/src/services/inbound_message_service.py`). Medido contra o `InboundMessageService` real: as 33 mensagens ALTA que o classificador perdeu, em 4 cenários cada (tutor conhecido, desconhecido, timeout na busca, timeout no registro), geraram 132 respostas, e as 132 trazem a orientação (ausente em 0).
- **Conclusão honesta:** o classificador ordena a fila da clínica. Quem garante que nenhuma emergência fique sem orientação é a resposta padrão, e não o vocabulário reconhecido.

Como reproduzir (de dentro de `luna/`):

```bash
# Corpus do time (v1.4): 150 / 149 / 0 de 77
PYTHONPATH=. python scripts/avaliar_triagem.py

# Testes sem visão computacional (sem torch): ignora os 4 arquivos que importam torch/ultralytics
PYTHONPATH=. python -m pytest tests/unit -q \
  --ignore=tests/unit/ai/test_breed_classifier.py --ignore=tests/unit/ai/test_breed_detector.py \
  --ignore=tests/unit/cli/test_main.py --ignore=tests/unit/services/test_breed_service.py
```

O conjunto cego e o roteiro de medição estão em `luna/docs/IA_DEFINICAO.md` §9.5. O texto das 61 mensagens, a sonda que classifica cada uma e a medição da rede de segurança (132/132) ficam no repositório de planejamento do projeto, que não é público; as contagens acima vêm de lá. A medição das 61 mensagens nas regras v1.4 foi refeita em 29/10/2026 com o `TriageEngine` deste repositório.

---

## Demonstração reproduzível

```bash
cd luna
PYTHONPATH=. python scripts/demo_sprint3.py          # interativo (pausa entre atos)
PYTHONPATH=. python scripts/demo_sprint3.py --auto   # sem pausas
```

Roda sem Docker, sem Oracle, sem Twilio e sem chave de API. São quatro atos:

1. **Triagem:** o `TriageEngine` classifica mensagens reais de tutor e mostra urgência, sintomas que dispararam a decisão e score.
2. **Cadeia inteira:** o `InboundMessageService` de produção, com os gateways de saída trocados por dublês que imprimem o payload exato que iria pela rede (interação registrada antes da triagem; tutor cadastrado, dúvida simples e número não cadastrado).
3. **NLP clínico:** texto de consulta transcrito vira rascunho SOAP.
4. **Limites:** o que o motor de regras não faz (negação, tempo, contexto, sinônimo fora da base), medido e não estimado.

---

## Integração com o KURA

```
WhatsApp (tutor) -> Luna (webhook Twilio, triagem) -> API .NET (/api/v1/luna/*, header X-Api-Key)
   -> Oracle (INTERACAO_CANAL, TRIAGEM_LUNA) -> card da triagem no app da clínica, com "Agendar"
```

- O contrato com a API .NET está em `luna/docs/api_contracts.md`; a cadeia detalhada, em `luna/docs/IA_DEFINICAO.md` §6 e §7.
- A tela do app da clínica fica no repositório `mobile-clinica-rn`, não neste.
- **Confirmação D-1:** a Luna pode pedir ao tutor que confirme o agendamento do dia seguinte e interpretar a resposta. Fica **desligada por padrão** (`LEMBRETE_CONFIRMACAO_HABILITADO=false`, `luna/src/config/settings.py`).

---

## Personalização

A personalização vem de contexto já existente no banco, sem perfilamento (`luna/docs/IA_DEFINICAO.md` §8):

1. **Identidade:** o telefone identifica o tutor, a clínica e os pets.
2. **Urgência:** a resposta muda conforme a classificação (emergência x dúvida simples).
3. **Raça:** a recomendação preventiva depende da predisposição registrada para a raça (hoje só alcançável pelo pipeline de visão opcional).
4. **Calendário do pet:** o lembrete de vacina usa a data real da próxima dose, o nome do pet, do tutor e da clínica.

**O que não fazemos:** não construímos perfil comportamental, não inferimos características não declaradas e não usamos o histórico clínico de um pet para alimentar um modelo que decide sobre outro, por tratar-se de dado de saúde sensível pela LGPD.

---

## Limites e o que não está verificado

- **Visão computacional sem checkpoint:** não há pesos treinados para o classificador de raça nem script de treino; `luna detect` não roda só com o repositório, e o componente não tem endpoint HTTP (`IA_DEFINICAO.md` §9.2).
- **WhatsApp ao vivo não foi verificado neste ciclo:** a demonstração é simulada. O envio e a recepção reais pelo sandbox do Twilio dependem de configuração externa.
- **Transcrição exige `OPENAI_API_KEY`:** sem a chave, o Ato 3 da demonstração usa um texto já transcrito e só exercita a estruturação SOAP.
- **O motor é léxico:** não trata negação em outra oração, nem tempo, nem contexto, e perde sinônimos fora da base (a demonstração, Ato 4, e `IA_DEFINICAO.md` §10 mostram cada caso).
- **Os corpora não foram validados por veterinário.**

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
