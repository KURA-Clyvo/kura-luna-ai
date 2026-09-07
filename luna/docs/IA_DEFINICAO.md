# Luna — Definição do componente de Inteligência Artificial

**Projeto:** KURA · Clyvo Vet — ecossistema de gestão veterinária
**Disciplina:** Disruptive Architectures: IoT, IoB & Generative IA — Sprint 3
**Data:** 07/09/2026
**Repositório:** `kura-luna-ai` · serviço `luna` (Python 3.12 · FastAPI)

> Este documento define **qual IA existe no KURA, por que ela é assim, quais dados a
> alimentam e como ela se integra ao resto do ecossistema**.
>
> Ele descreve o sistema **como ele é hoje**, não como gostaríamos que fosse. Onde um
> componente está incompleto, isso está escrito com essas palavras. Cada afirmação
> técnica aponta o arquivo e a linha onde pode ser conferida.

---

## Sumário

1. [O problema de negócio](#1-o-problema-de-negócio)
2. [O que a IA faz na jornada de cuidado](#2-o-que-a-ia-faz-na-jornada-de-cuidado)
3. [A abordagem escolhida — e por que não um LLM](#3-a-abordagem-escolhida--e-por-que-não-um-llm)
4. [Os quatro componentes de IA](#4-os-quatro-componentes-de-ia)
5. [Os dados que alimentam a IA](#5-os-dados-que-alimentam-a-ia)
6. [Fluxo de dados ponta a ponta](#6-fluxo-de-dados-ponta-a-ponta)
7. [Arquitetura de integração](#7-arquitetura-de-integração)
8. [Estratégia de personalização](#8-estratégia-de-personalização)
9. [Estado atual, com honestidade](#9-estado-atual-com-honestidade)
10. [Limites conhecidos e evolução](#10-limites-conhecidos-e-evolução)
11. [Governança: LGPD, CFMV e a regra do copiloto](#11-governança-lgpd-cfmv-e-a-regra-do-copiloto)

---

## 1. O problema de negócio

### A dor, em uma frase

**A medicina veterinária brasileira opera de forma reativa: o pet chega à clínica quando o
problema já aconteceu.** Entre uma consulta e a próxima existe um vazio de meses em que o
único observador do animal é o tutor — que não tem formação para saber o que é urgente e o
que é manha.

Esse vazio produz três perdas simultâneas:

| Quem perde | O que perde |
|---|---|
| **O pet** | Tempo de diagnóstico. Sintoma percebido no sábado vira consulta na terça, e alguns quadros não esperam. |
| **O tutor** | Segurança. Não existe canal para a pergunta pequena — a que não justifica uma consulta, mas tira o sono. |
| **A clínica** | Previsibilidade e tempo. A receita depende de emergência, e a equipe gasta parte relevante do dia respondendo mensagem manualmente, uma a uma. |

### Por que esse vazio existe

Não é falta de vontade da clínica. É que **o canal onde o tutor já está — o WhatsApp — não
é um canal clínico**. A mensagem chega, alguém da recepção lê quando pode, responde do
jeito que consegue, e aquilo **não vira registro**. No dia seguinte a informação não existe
em lugar nenhum: nem no prontuário, nem numa fila de prioridade, nem num histórico.

O tutor mandou um sinal. O sistema não o capturou.

### O que a Luna resolve

> **A Luna transforma a mensagem que o tutor já manda em um registro clínico classificado
> por urgência, sem exigir que ele instale aplicativo, faça cadastro ou aprenda nada.**

Ela não substitui o veterinário. Ela garante que **nenhum sinal se perca** e que o que
chegou primeiro na fila seja o que é mais urgente — não o que é mais recente.

---

## 2. O que a IA faz na jornada de cuidado

A rubrica pede que a IA contribua para **personalização, priorização de ações,
recomendação de serviços ou apoio à decisão**. O KURA ocupa as quatro frentes, com pesos
diferentes:

| Contribuição | Como acontece no KURA | Componente |
|---|---|---|
| **Priorização de ações** | Toda mensagem recebida é classificada em `ALTA`/`MEDIA`/`BAIXA` com sintomas e score explícitos. A fila da clínica deixa de ser cronológica e passa a ser clínica. | `TriageEngine` |
| **Apoio à decisão** | O áudio da consulta vira um rascunho SOAP (Subjetivo/Objetivo/Avaliação/Plano) pré-preenchido, que o veterinário revisa e corrige em vez de digitar do zero. | `WhisperGateway` + `montar_soap_draft` |
| **Recomendação de serviços** | A raça do pet é cruzada com as predisposições clínicas conhecidas daquela linhagem, gerando sugestão de avaliação preventiva. | `RecomendacaoCuidados` |
| **Personalização** | A resposta ao tutor muda conforme a urgência detectada e conforme ele ser ou não um tutor identificado na base da clínica. | `InboundMessageService` |

E uma quinta contribuição que **não é IA e não vamos chamar de IA**: o lembrete automático
de vacina próxima do vencimento. É automação determinística por regra de calendário.
Aparece neste documento porque compõe o valor entregue, mas chamá-la de inteligência
artificial seria exagero.

---

## 3. A abordagem escolhida — e por que não um LLM

A rubrica lista seis abordagens possíveis: *IA Generativa, LLM, sistema de recomendação,
motor de regras inteligentes, NLP ou modelo preditivo*.

**Escolhemos três delas, e recusamos deliberadamente as outras.**

| Abordagem | Adotada? | Onde |
|---|---|---|
| **Motor de regras inteligentes** | ✅ **Sim — é o núcleo** | `TriageEngine` (triagem de urgência) |
| **Sistema de recomendação** | ✅ Sim — baseado em conteúdo | `RecomendacaoCuidados` (predisposição por raça) |
| **NLP** | ✅ Sim | ASR via Whisper + classificação de sentença em SOAP |
| **Modelo preditivo** | 🟡 Parcial | `BreedClassifier` (MobileNetV3) — ver §9 |
| **IA Generativa / LLM** | ❌ **Não, por decisão** | — |

### Por que recusamos o LLM na triagem

Esta é a decisão técnica mais importante do projeto, e ela **não foi por falta de acesso à
tecnologia**. Foi por três razões de domínio:

**1. Auditabilidade é requisito, não bônus.**
Em contexto clínico, toda classificação precisa ser explicável: *qual sintoma disparou qual
nível*. O `TriageEngine` devolve, junto com a decisão, a lista literal de sintomas
detectados e o score que os somou. Se um veterinário discordar da classificação, ele
consegue ver exatamente por quê — e nós conseguimos corrigir a regra. Com um LLM, a
resposta a "por que isso foi ALTA?" é uma reconstrução plausível, não a causa real.

**2. Alucinação em triagem veterinária é dano, não bug.**
Um modelo generativo que inventa um sintoma que o tutor não relatou, ou que suaviza um que
ele relatou, produz uma decisão clínica sobre um animal real. O motor de regras tem o
comportamento oposto: ele só reconhece o que está escrito na base de conhecimento. Ele
**erra por omissão, nunca por invenção** — e omissão, num sistema que sempre encaminha ao
humano, é um erro recuperável.

**3. Custo e latência viabilizam o canal.**
A resposta ao tutor sai em milissegundos e com custo zero por mensagem. Isso é o que
permite operar no WhatsApp em volume, sem que cada "bom dia" de tutor vire uma chamada
paga de API.

### Onde usamos rede neural — e por quê exatamente ali

Usamos modelo neural em **dois pontos, os dois de baixo risco e alto ganho**:

- **Transcrição de áudio (Whisper).** Converter fala em texto é uma tarefa em que a rede
  neural é insubstituível e em que o erro é visível e corrigível — o veterinário lê o
  rascunho antes de qualquer coisa ser salva.
- **Visão computacional (YOLOv8n + MobileNetV3).** Identificar cão/gato e raça em foto é
  classificação supervisionada clássica, com saída verificável pelo próprio usuário.

**A regra que separa os dois mundos:** rede neural onde o erro é *percebido e corrigido
pelo humano no mesmo instante*; regra determinística onde o erro *entraria silenciosamente
numa decisão clínica*.

---

## 4. Os quatro componentes de IA

### 4.1 `TriageEngine` — motor de regras léxico para urgência

**Arquivo:** `src/ai/triage_engine.py` · **Base de conhecimento:** `src/ai/triage_rules.py`

É o coração da entrega. Recebe o texto livre que o tutor escreveu no WhatsApp e devolve
uma classificação de urgência com rastro completo.

**Base de conhecimento versionada** (`TRIAGE_RULES_VERSION = "1.0"`) — **11 categorias
clínicas** distribuídas em três níveis:

| Nível | Pontos | Categorias |
|---|---|---|
| **ALTA** | 10 | `convulsao`, `sangramento`, `envenenamento`, `dispneia`, `trauma` |
| **MEDIA** | 3 | `vomito`, `diarreia`, `letargia`, `febre` |
| **BAIXA** | 1 | `duvida`, `comportamento` |

**Como decide, passo a passo:**

1. **Normaliza** texto e palavras-chave por decomposição NFKD — remove acento e caixa. É o
   que faz `"convulsão"`, `"Convulsao"` e `"CONVULSÃO"` caírem na mesma regra, sem
   precisar cadastrar as três formas.
2. **Procura** cada palavra-chave como substring do texto normalizado.
3. **Pontua** cada *categoria* uma única vez por nível — dez menções a sangue não valem
   dez vezes mais que uma.
4. **Decide por hierarquia estrita:** se houve qualquer sintoma de alta, a urgência é
   `ALTA`, independentemente de quantos sintomas leves apareceram junto.
5. **Devolve** `TriageResult(urgencia, sintomas_detectados, score, regras_versao)`.

**O score e a urgência respondem perguntas diferentes, e isso é de propósito.** A urgência
diz *"em que fila isso entra"*. O score acumula pontos de **todos** os níveis detectados e
diz *"dentro da fila, o que vem primeiro"* — uma mensagem com convulsão **e** vômito **e**
febre pontua mais que uma só com convulsão, e as duas são `ALTA`.

**A resposta ao tutor muda conforme o nível**, e é enviada na hora:

| Urgência | Resposta enviada |
|---|---|
| `ALTA` | *"Identificamos sintomas que requerem atenção urgente. Estamos notificando seu veterinário. Para emergências imediatas, ligue para a clínica."* |
| `MEDIA` | *"Mensagem recebida. Nossa equipe retorna em até 2 horas."* |
| `BAIXA` | *"Mensagem registrada. Respondemos em horário comercial."* |

---

### 4.2 `RecomendacaoCuidados` — recomendação baseada em conteúdo

**Arquivo:** `src/ai/recommender.py`

Cruza a raça identificada com a coluna `RACA.DS_PREDISPOSICAO` do Oracle — uma base de
conhecimento clínico curada, não um modelo treinado. Se a raça tem predisposição
registrada, monta a recomendação preventiva; **se não tem, devolve `None` e o sistema fica
calado.**

Esse `None` é a decisão de desenho mais relevante do componente: **o sistema não inventa
recomendação para raça que não conhece.** É a mesma filosofia do motor de regras — errar
por omissão, nunca por invenção.

Tecnicamente é **filtragem baseada em conteúdo** (*content-based*): usa atributo do item
(a raça) contra uma base de conhecimento. Não é filtragem colaborativa e não aprende com o
uso.

---

### 4.3 Visão computacional — detecção e classificação de raça

**Arquivos:** `src/ai/breed_detector.py`, `src/ai/breed_classifier.py`,
`src/services/breed_service.py`

Pipeline de dois estágios, padrão em visão computacional aplicada:

1. **Detecção — `PetDetector` (YOLOv8n).** Localiza objetos na foto, filtra para as classes
   COCO `dog` e `cat`, aplica limiar de confiança de `0.5` e ordena por confiança. Responde
   *"tem um animal aqui, e ele está nestas coordenadas"*.
2. **Classificação — `BreedClassifier` (MobileNetV3-Small).** Recorta a região do animal
   com maior confiança, redimensiona para 224×224, normaliza com as estatísticas do
   ImageNet e classifica. Responde *"este animal é desta raça, com esta confiança"*.
3. **Recomendação.** A raça alimenta o `RecomendacaoCuidados` (§4.2).
4. **Saída visual.** A imagem é anotada com as caixas e os rótulos e salva ao lado da
   original.

**Escopo do classificador: 35 raças** — 30 de cães e 5 de gatos, mapeadas do inglês
(nomenclatura Stanford Dogs) para português brasileiro em `src/ai/breed_labels_ptbr.py`.

> ⚠️ **Este número é 35, não 120.** Documentos anteriores deste repositório afirmavam 120
> raças; a afirmação estava errada e foi corrigida. `_NUM_CLASSES` é derivado por
> `len(BREED_LABELS_PTBR)`, então o número no código e o número neste documento não podem
> divergir sem que alguém edite o dicionário.

**Por que MobileNetV3-Small e não uma rede maior:** o alvo é inferência em CPU, em
container, com resposta em segundos e sem GPU. Uma ResNet-50 acertaria mais e não caberia
no orçamento de infraestrutura de uma clínica pequena. É uma escolha de engenharia, não de
desconhecimento.

**Estado atual deste componente: ver §9.2** — ele é o único dos quatro que não está
operacional.

---

### 4.4 NLP clínico — transcrição e estruturação SOAP

**Arquivo:** `src/services/transcricao_service.py`

O veterinário grava um áudio narrando a consulta. O sistema devolve um rascunho já
organizado no formato **SOAP**, que é o padrão de registro clínico.

**Estágio 1 — ASR (rede neural, de terceiro).** `WhisperGateway` envia o áudio para a API
Whisper da OpenAI (modelo `whisper-1`). Formatos aceitos: `mp3`, `m4a`, `wav`; limite de
25 MB, que é o limite da própria API.

**Estágio 2 — estruturação (heurística, nossa).** `montar_soap_draft` quebra a transcrição
em frases e classifica cada uma em um dos quatro campos, por vocabulário clínico:

| Campo | Dispara com termos como | Significado |
|---|---|---|
| **P** — Plano | *prescr…, tratamento, retorno em, aplicar, administrar, encaminhar, medicar* | o que será feito |
| **A** — Avaliação | *diagnóstico, suspeita, hipótese, quadro compatível, sugestivo de, provável* | o que o vet concluiu |
| **O** — Objetivo | *temperatura, peso, frequência cardíaca, exame físico, ausculta, palpação, mucosa* | o que foi medido |
| **S** — Subjetivo | *(bucket padrão)* | o que foi relatado |

**O bucket padrão é `S`, e isso é intencional.** Frase que o sistema não reconhece vai
para "relato do tutor" — o campo mais inofensivo dos quatro. Uma frase mal classificada em
`S` é ruído que o veterinário move; a mesma frase classificada erradamente em `P` seria uma
conduta que ninguém prescreveu.

**Ordem de avaliação:** Plano → Avaliação → Objetivo → Subjetivo. Uma frase que casa com
mais de um bucket vai para o de maior consequência clínica.

> **Nenhuma linha é persistida por este endpoint.** Ele devolve o rascunho; salvar é ação
> do veterinário, na tela dele. Ver §11.

---

## 5. Os dados que alimentam a IA

A rubrica pede **origem, estrutura e utilização**. É o que segue.

### 5.1 Mapa completo

| Dado | Origem | Estrutura | Utilizado para |
|---|---|---|---|
| **Texto da mensagem** | Tutor, via WhatsApp (webhook Twilio) | `string` livre, sem tamanho garantido | Entrada do `TriageEngine`; persistido em `INTERACAO_CANAL.DS_CONTEUDO` (`VARCHAR2(4000)`) |
| **Telefone do remetente** | Metadado do Twilio | `string` E.164 | Identificar o tutor via `GET /api/v1/tutores/telefone/{numero}`. **PII — nunca logado** (§11) |
| **Contexto do tutor** | API .NET, tabela `TUTOR` | `TutorContextoDTO`: `id_tutor`, `nm_tutor`, `ds_whatsapp`, `id_clinica`, `pets[]` | Vincular a interação à clínica correta e habilitar a triagem |
| **Predisposição por raça** | Oracle, `RACA.DS_PREDISPOSICAO` | Texto curado por raça | Base de conhecimento do recomendador |
| **Vacinas a vencer** | Oracle, view `VW_VACINAS_VENCENDO` | Visão sobre `AGENDAMENTO` + `PET` + `CLINICA` | Lembrete proativo (não é IA) |
| **Áudio da consulta** | Veterinário, via app da clínica → .NET → Luna | `mp3`/`m4a`/`wav`, ≤ 25 MB | Entrada do Whisper. **Não persistido pela Luna** |
| **Foto do pet** | Arquivo local (hoje só via CLI) | Imagem lida por OpenCV | Entrada do pipeline de visão |
| **Base de sintomas** | Curadoria própria, versionada em código | 11 categorias × listas de palavras-chave | Base de conhecimento do `TriageEngine` |

### 5.2 O que a IA escreve de volta

| Tabela | O que grava | Estrutura relevante |
|---|---|---|
| **`INTERACAO_CANAL`** | Toda mensagem recebida | `ID_CLINICA` (anulável), `ID_TUTOR` (anulável), `DS_CANAL`, `DS_DIRECAO`, `DS_CONTEUDO VARCHAR2(4000)`, `DT_RECEBIMENTO` |
| **`TRIAGEM_LUNA`** | O resultado da classificação | `ID_CLINICA`, `ID_TUTOR`, `ID_INTERACAO` (FK), `DS_NIVEL_URGENCIA VARCHAR2(20)`, `DS_DESCRICAO VARCHAR2(2000)`, `DT_TRIAGEM` |
| **`NOTIFICACAO`** | Lembretes enviados e seu status | `DS_CANAL`, `DS_TIPO`, `ST_STATUS`, `DS_ERRO_ENVIO` |
| **`LOG_ERRO`** | Falhas, já sanitizadas de PII | `NM_PROCEDURE`, `DS_ERRO`, `DS_PARAMETROS` |

**A interação é gravada mesmo quando o tutor não é identificado**, com `ID_CLINICA` nulo.
Isso foi uma decisão de produto: preferimos ter o registro de auditoria a descartar o
sinal.
**A consequência precisa ser dita:** linha com clínica nula é invisível a qualquer consulta
escopada por clínica. O ganho é auditoria, não visibilidade na tela.

### 5.3 Uma limitação de modelagem que declaramos

`sintomas[]`, `nr_score` e `ds_recomendacao` **não têm coluna própria** em `TRIAGEM_LUNA` —
são compostos em texto livre dentro de `DS_DESCRICAO`, no formato
`"Sintomas: X, Y. Score: N. Recomendação: Z"`.

Foi uma escolha consciente de não bloquear a integração esperando uma migração de schema.
**O custo é real e é este:** hoje não dá para responder por SQL *"quantas triagens com
score acima de 20 tivemos neste mês"* sem parsear texto. Se essa consulta virar requisito,
a correção é uma migration nova com colunas próprias — não uma gambiarra de parsing.

---

## 6. Fluxo de dados ponta a ponta

### 6.1 Triagem por WhatsApp — o caminho principal

```
┌──────────┐   1. mensagem WhatsApp
│  Tutor   │ ─────────────────────────────► ┌────────────┐
└──────────┘                                 │   Twilio   │
     ▲                                       └─────┬──────┘
     │                                             │ 2. webhook assinado
     │ 8. resposta                                 │    (X-Twilio-Signature)
     │    personalizada                            ▼
     │                                 ┌───────────────────────────┐
     └─────────────────────────────────│   LUNA  ·  FastAPI        │
                                       │  POST /webhook/twilio/... │
                                       └────────────┬──────────────┘
                                                    │ 3. BackgroundTask
                                                    ▼
                                       ┌───────────────────────────┐
                                       │  InboundMessageService    │
                                       └────────────┬──────────────┘
                    4. quem é este número?          │
        ┌───────────────────────────────────────────┤
        │                                           │
        ▼                                           ▼
┌───────────────────┐                   ┌───────────────────────┐
│  API .NET (8080)  │                   │    TriageEngine       │
│  GET /tutores/    │                   │  (só se tutor         │
│      telefone/{n} │                   │   identificado)       │
└─────────┬─────────┘                   └───────────┬───────────┘
          │                                         │
          │ 5. POST /luna/interactions              │ 6. POST /luna/triage
          │    (sempre)                             │    urgência + sintomas + score
          ▼                                         ▼
    ┌─────────────────────────────────────────────────────┐
    │              ORACLE  (schema compartilhado)         │
    │   INTERACAO_CANAL          TRIAGEM_LUNA             │
    └─────────────────────────────────────────────────────┘
                              │
                              │ 7. leitura autenticada por JWT de clínica
                              ▼
                  ┌───────────────────────────┐
                  │  App da Clínica (Expo)    │
                  │  Painel Luna · urgências  │
                  └───────────────────────────┘
```

**Quatro decisões de arquitetura visíveis neste desenho:**

1. **A interação é registrada antes da triagem** (passo 5 antes do 6). Se a classificação
   falhar, a mensagem do tutor não se perde.
2. **Falha de telemetria nunca bloqueia a resposta ao tutor.** O registro da triagem está
   dentro de um `try/except` que loga e segue. O tutor recebe resposta mesmo com o .NET
   fora do ar.
3. **A triagem só roda para tutor identificado.** Número desconhecido tem a interação
   gravada (com clínica nula) e recebe a resposta genérica de fallback. É escopo
   declarado, não esquecimento — ver §10.
4. **Processamento em `BackgroundTask`.** O webhook devolve `200` ao Twilio imediatamente;
   o trabalho acontece depois. Sem isso, o Twilio marcaria timeout e reentregaria.

### 6.2 Transcrição clínica — o caminho do veterinário

```
Veterinário grava áudio
        │
        ▼
┌────────────────────┐   POST /eventos-clinicos/{id}/transcricao
│ App Clínica (Expo) │ ──────────────────────────────────────►┐
└────────────────────┘                                        │
                                                              ▼
                                                  ┌───────────────────────┐
                                                  │   API .NET  (8080)    │
                                                  │ LunaTranscricaoService│
                                                  └───────────┬───────────┘
                                                              │ multipart + X-API-Key
                                                              ▼
                                                  ┌───────────────────────┐
                                                  │  LUNA  POST /transcricao
                                                  └───────────┬───────────┘
                                            ┌─────────────────┴──────────────┐
                                            ▼                                ▼
                                 ┌────────────────────┐         ┌──────────────────────┐
                                 │ Whisper API        │  texto  │ montar_soap_draft()  │
                                 │ (OpenAI)           │ ──────► │ heurística S/O/A/P   │
                                 └────────────────────┘         └──────────┬───────────┘
                                                                           │
                                        rascunho S/O/A/P (NÃO persistido)  │
                                 ◄─────────────────────────────────────────┘
                                            │
                                            ▼
                              Veterinário revisa, corrige e SALVA
                                            │
                                            ▼
                                  EVENTO_CLINICO (Oracle)
```

**Degradação por desenho:** se o Whisper falhar, o endpoint devolve `200` com
`transcricao=null, soap=null`, e o app abre o formulário vazio para digitação manual.
**Nunca devolve erro de servidor** — a consulta não pode parar porque a IA parou.

---

## 7. Arquitetura de integração

### 7.1 O princípio: um banco, duas APIs, um serviço de IA

O KURA tem **duas APIs de negócio que nunca conversam por HTTP entre si** — elas
compartilham um único schema Oracle:

| Serviço | Stack | Porta | Contexto |
|---|---|---|---|
| `backend-clinica-dotnet` | .NET 10 · Clean Architecture | 8080 | B2B — clínica e veterinário |
| `backend-tutor-java` | Java 21 · Spring Boot | 8081 | B2C — tutor e pet |
| `kura-luna-ai` | Python 3.12 · FastAPI | 8000 | **IA e comunicação proativa** |

**A Luna não fala com o Oracle para escrever dado clínico.** Ela escreve *através* da API
.NET, por HTTP. Isso é deliberado: a regra de negócio de multi-tenancy, a derivação de
clínica a partir do tutor e a validação de consistência vivem em um lugar só. Se a Luna
escrevesse direto na tabela, essas regras precisariam existir duas vezes — e divergiriam.

A exceção é a **leitura** de dados de referência (`RACA`, `VW_VACINAS_VENCENDO`), onde a
Luna tem pool Oracle próprio. Leitura de catálogo não carrega regra de tenancy.

### 7.2 Contrato Luna → .NET

Três endpoints, autenticados **por chave de API server-a-servidor** (`X-Api-Key`), não por
JWT — a Luna é um serviço, não um usuário:

| Método | Rota | Papel |
|---|---|---|
| `GET` | `/api/v1/tutores/telefone/{numero}` | Identificar o tutor pelo WhatsApp. `404` = não cadastrado (legítimo) |
| `POST` | `/api/v1/luna/interactions` | Registrar a interação. Aceita `id_tutor` nulo |
| `POST` | `/api/v1/luna/triage` | Registrar o resultado da triagem |

Corpo em `snake_case`, com `[JsonPropertyName]` explícito nos DTOs C# — o contrato é
declarado nos dois lados, não herdado de convenção de serialização.

### 7.3 Superfície HTTP da Luna

| Rota | Autenticação | Toca IA? |
|---|---|---|
| `GET /health` | aberta | não — liveness |
| `GET /ready` | aberta | não — verifica Oracle e .NET de verdade |
| `POST /webhook/twilio/whatsapp` | assinatura Twilio (`403` se ausente ou inválida) | ✅ `TriageEngine` |
| `POST /whatsapp/enviar` | `X-API-Key`, comparada com `secrets.compare_digest` | não |
| `POST /transcricao` | `X-API-Key` | ✅ Whisper + SOAP |

**Uso de `secrets.compare_digest`, e não `==`:** comparação de string comum vaza a chave
por tempo de execução. É defesa contra *timing attack*, barata e correta.

### 7.4 Padrões de engenharia adotados

| Padrão | Onde | Por quê |
|---|---|---|
| **Portas e adaptadores** | `IKuraClient`, `ITwilioGateway`, `IWhisperGateway` (`typing.Protocol`) | Os testes substituem o transporte sem herança nem monkey-patch |
| **Injeção por construtor** | Todos os services | Nenhum serviço constrói a própria dependência |
| **Composition root único** | `src/cli/main.py` | Um lugar só sabe montar o grafo de objetos |
| **Imports preguiçosos** | `cli/main.py` | `luna run-job` não paga o custo de carregar `torch` |
| **Application factory** | `create_app(settings)` | Testes sobem a app com settings próprias |
| **Sanitização de PII** | `redigir_url_sensivel`, `raise ... from None` | §11 |

---

## 8. Estratégia de personalização

A personalização do KURA **não vem de perfilamento comportamental nem de modelo treinado
por usuário**. Ela vem de contexto relacional já existente no banco. São quatro camadas:

**1. Personalização por identidade.**
O telefone identifica o tutor, que traz junto a clínica e a lista de pets. A mesma
mensagem vinda de dois números diferentes produz registros vinculados a clínicas
diferentes, com respostas diferentes.

**2. Personalização por urgência.**
A resposta muda conforme a classificação. O tutor de um caso `ALTA` recebe orientação de
emergência; o de uma dúvida simples recebe o prazo real de resposta. Nenhum dos dois recebe
o texto genérico do outro.

**3. Personalização por raça.**
A recomendação preventiva depende da predisposição registrada para aquela linhagem. Um
Buldogue Francês e um Border Collie recebem recomendações diferentes porque **têm riscos
clínicos diferentes** — não porque um algoritmo inferiu preferência.

**4. Personalização por calendário do pet.**
O lembrete de vacina dispara pela data real da próxima dose daquele animal naquela clínica,
com nome do pet, nome do tutor e nome da clínica no texto.

> **O que deliberadamente não fazemos:** não construímos perfil comportamental, não
> inferimos características não declaradas e não usamos histórico clínico de um pet para
> alimentar modelo que decide sobre outro. Em dado de saúde, isso não é conservadorismo —
> é o que a LGPD trata como dado sensível.

---

## 9. Estado atual, com honestidade

Esta seção existe porque um documento técnico que só descreve o que funciona é material de
marketing, não de engenharia.

### 9.1 O que está operacional e integrado

| Componente | Estado | Evidência |
|---|---|---|
| `TriageEngine` | ✅ **Operacional** | 22 testes dedicados; cadeia até o Oracle validada em ciclo de integração anterior |
| Contrato Luna → .NET | ✅ **Operacional** | Os 3 endpoints existem dos dois lados, com a mesma rota e a mesma autenticação |
| Registro em `INTERACAO_CANAL` / `TRIAGEM_LUNA` | ✅ **Operacional** | Provado por consulta SQL contra Oracle real em ciclo anterior |
| `POST /transcricao` | ✅ **Operacional** *(requer `OPENAI_API_KEY`)* | Cadeia app → .NET → Luna → Whisper fechada em código |
| `RecomendacaoCuidados` | 🟡 **Funciona, mas inalcançável** | Só é chamado de dentro do pipeline de visão — ver §9.2 |
| Pipeline de visão | 🔴 **Não executável como entregue** | Ver §9.2 |
| Lembrete de vacina | 🔴 **Contrato de leitura quebrado** | Ver §9.3 |

### 9.2 A visão computacional não roda como entregue

**O código está completo e correto. O que falta é o modelo treinado.**

- `src/ai/models/` contém apenas `.gitkeep`, e o `.gitignore` do projeto exclui `*.pt` e
  `*.pth`. Existe script para baixar os pesos do YOLO (`scripts/download_yolo_weights.py`),
  mas **não existe script de download nem de treino para o classificador de raça**.
- Consequência direta: `luna detect` **falha na construção do objeto** — `load_state_dict`
  sem arquivo — em qualquer máquina que tenha só o repositório.
- **Além disso, este componente não tem endpoint HTTP.** Ele só existe pela CLI. Nenhum dos
  dois aplicativos móveis tem caminho para acioná-lo.

**Risco silencioso que precisa ser registrado:** o mapa índice→rótulo é construído com
`enumerate(BREED_LABELS_PTBR.keys())`, ou seja, **depende da ordem de inserção do
dicionário**. Um checkpoint treinado com outra ordem de rótulos produziria classificações
confiantes e erradas, **sem nenhum erro de execução**. Se este componente for retomado, a
ordem dos rótulos precisa ser fixada junto com os pesos, não inferida do código.

### 9.3 O lembrete de vacina não sobrevive ao schema real

`VacinaRepository` consulta `VW_VACINAS_VENCENDO` pedindo **nove colunas**. A view, como
definida na migração vigente, expõe **sete** — e três das pedidas não existem em nenhuma
migration do projeto: `NM_TUTOR`, `DS_WHATSAPP` e `DIAS_RESTANTES`.

`DIAS_RESTANTES` é justamente a coluna do filtro (`WHERE DIAS_RESTANTES <= :dias`).

**Contra um Oracle real construído pelo Flyway, `luna run-job` termina em
`ORA-00904: invalid identifier`.**

**Por que nenhum teste pegou:** os testes do repositório entregam uma tupla de nove
posições escrita à mão para um cursor simulado. Eles provam que o mapeamento
tupla→objeto está certo — e **nunca executam o SQL contra a view real**. É um teste
correto medindo a coisa errada.

**Nota relacionada:** `LembreteVacinaJob.iniciar_scheduler` não tem nenhum chamador em
produção. O container executa apenas o servidor FastAPI. O agendamento diário descrito na
documentação anterior **não está ativo**.

### 9.4 O que os números de teste realmente dizem

| Medição | Resultado |
|---|---|
| Funções `test_` no repositório | **252** |
| CI (Python 3.12, todas as dependências) | ✅ **verde**, execução de 07/09/2026 |
| Suíte local sem `torch`/`ultralytics` | **211 coletados · 210 passaram · 1 falhou** |
| Suíte local completa | ❌ **não coleta** — 4 erros de importação |

A falha local é `test_smoke.py::test_all_modules_importable`, por ausência de
`ultralytics`. Não é regressão: é o ambiente. `torch==2.4.1` não tem *wheel* para Python
3.13/3.14, então a suíte completa exige Python 3.12 — que é o que o CI usa.

**A leitura honesta:** os testes cobrem bem a lógica de decisão (triagem, DTOs, cliente
HTTP, roteadores). Eles **não cobrem**, e não pretendem cobrir, a integração com Oracle
real, com Twilio real ou com a Whisper real. Todos os três são simulados.

---

## 10. Limites conhecidos e evolução

### 10.1 Limites do motor de regras — ditos antes de alguém descobrir

| Limite | Exemplo concreto | Gravidade |
|---|---|---|
| **Sem fronteira de palavra** | `"acidente"` casa dentro de `"acidentalmente"` → falso positivo de urgência ALTA | Média — erra para o lado seguro |
| **Sem tratamento de negação** | *"ele **não** está vomitando"* classifica como MEDIA | Média — erra para o lado seguro |
| **Sem stemming nem sinônimo aprendido** | *"regurgitou"* não está na base e não é reconhecido | Alta — este é o erro que importa |
| **Sem contexto de conversa** | Cada mensagem é classificada isoladamente | Baixa |
| **Vocabulário fixo** | Ampliar cobertura exige editar `triage_rules.py` e subir versão | Por desenho |

**Os dois primeiros erram para o lado seguro** — escalam urgência que não precisava
escalar, e um humano descarta. **O terceiro é o que merece atenção**: sintoma real que a
base não conhece passa como `BAIXA`. É por isso que `TRIAGE_RULES_VERSION` existe: a base
é um artefato vivo, revisável com o veterinário, versionado como código.

### 10.2 Limite da heurística SOAP

`montar_soap_draft` é classificação por palavra-chave, não compreensão. O próprio código
declara isso e aponta a evolução natural: reconhecimento de entidades clínicas.
**Aqui um LLM faria sentido**, e por um motivo específico: o veterinário revisa cada campo
antes de salvar, então o erro do modelo é sempre interceptado por um humano qualificado.
É o oposto do caso da triagem.

### 10.3 O caminho para 100%

Em ordem de valor por esforço:

1. **Corrigir a view `VW_VACINAS_VENCENDO`** — migration nova adicionando `NM_TUTOR`,
   `DS_WHATSAPP` (join com `TUTOR`) e `DIAS_RESTANTES` (expressão de data). Destrava a
   funcionalidade que o README anuncia há mais tempo.
2. **Um teste de integração que execute o SQL real** contra o schema — não um cursor
   simulado. É o gate que teria pegado o item 1.
3. **Expor a recomendação por raça via HTTP**, usando a raça **já cadastrada** do pet.
   Isso torna o recomendador alcançável **sem depender de visão computacional**.
4. **Escrever `ST_ENCAMINHADO_VET`** quando a urgência for `ALTA`. Hoje o campo é lido no
   relatório e nunca escrito, o que faz o indicador "encaminhadas para o veterinário" ser
   estruturalmente zero.
5. **Triar também tutor não identificado** — classificar o texto antes de saber quem
   enviou, gravando a triagem sem vínculo.
6. **Resolver o checkpoint de raça** — treinar e versionar fora do git, com a ordem dos
   rótulos fixada junto.

---

## 11. Governança: LGPD, CFMV e a regra do copiloto

### 11.1 A regra do copiloto

> **A Luna sugere. O veterinário decide.**

Não é postura defensiva de apresentação — está no código:

- `POST /transcricao` **não persiste nada**. Devolve rascunho.
- O motor de regras **classifica urgência, não diagnostica**. Nenhuma saída da Luna é
  apresentada como conclusão clínica.
- A recomendação por raça é **preventiva e genérica** (*"recomendamos uma avaliação"*),
  nunca prescritiva.

Isso conversa diretamente com a Resolução CFMV 1.465/2022, que exige atendimento presencial
prévio para teleconsulta e mantém a responsabilidade clínica com o profissional.

### 11.2 LGPD — PII em log é restrição dura

**O telefone do tutor viaja no path da rota de consulta.** Qualquer log que imprima URL ou
traceback vazaria dado pessoal. Três defesas, todas em código:

1. **Redação de path sensível** antes de qualquer log.
2. **Correlação por `message_sid` do Twilio**, não por telefone. Todo log de erro do fluxo
   inbound identifica a mensagem por um identificador não-PII.
3. **`raise ... from None`, nunca `from exc`.** Esta é a mais sutil e a mais importante:
   encadear a causa preserva `__cause__`, e `logger.exception()` formata a **cadeia
   inteira**, reimprimindo a mensagem original com o telefone cru — mesmo que a exceção
   nova esteja sanitizada. Só `from None` suprime.

O item 3 vale ser destacado porque **é uma armadilha que não aparece em revisão de código
superficial**: o código parece sanitizado, a exceção nova é limpa, e o dado sensível
reaparece pelo formatador do traceback. Foi confirmado com reprodução isolada, e vale
igualmente para a tabela `LOG_ERRO`, que é compartilhada no Oracle.

### 11.3 Segredos

Nenhuma credencial tem valor padrão utilizável. `OPENAI_API_KEY` e `LUNA_INBOUND_API_KEY`
têm default **vazio**, de propósito: sem a chave, o recurso falha de forma explícita em vez
de operar com uma credencial de exemplo.

---

## Apêndice — como conferir cada afirmação

| Afirmação | Comando |
|---|---|
| 11 categorias de sintoma | `grep -c '": \[' src/ai/triage_rules.py` |
| 35 raças no classificador | `grep -c '": "' src/ai/breed_labels_ptbr.py` |
| Nenhum checkpoint versionado | `ls -la src/ai/models/` |
| Suíte de testes | `pytest -m "not slow"` (requer Python 3.12) |
| Rotas HTTP expostas | `grep -rn "@router\." src/web/routers/` |
| Contrato com o .NET | `grep -n "api/v1" src/integration/kura_client.py` |

**Documentos relacionados neste repositório:**
`docs/architecture.md` (diagramas) · `docs/api_contracts.md` (contratos REST) ·
`docs/runbook.md` (operação) · `docs/demo_script.md` (roteiro de demonstração)
