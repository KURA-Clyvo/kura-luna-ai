# Arquitetura — Luna

> **Escopo deste documento:** os diagramas abaixo cobrem o estado **v2** do serviço —
> servidor FastAPI, webhook do WhatsApp, motor de triagem, integração com a API .NET,
> transcrição clínica e o pipeline de visão computacional.
>
> A definição do componente de IA (problema, dados, abordagem, limites) está em
> **[`IA_DEFINICAO.md`](IA_DEFINICAO.md)**.

---

## 1. Diagrama arquitetural do ecossistema

Este é o diagrama de referência: mostra a comunicação entre **aplicações**, **APIs**,
**banco de dados** e **componentes de IA**.

```mermaid
graph TB
    subgraph clientes["👤 Clientes"]
        TUTOR["Tutor<br/><i>WhatsApp — sem app, sem cadastro</i>"]
        APPT["App do Tutor<br/><i>React Native · Expo</i>"]
        APPC["App da Clínica<br/><i>React Native · Expo</i>"]
    end

    subgraph externo["☁️ Serviços externos"]
        TW["Twilio<br/><i>WhatsApp Business</i>"]
        WH["OpenAI Whisper<br/><i>ASR</i>"]
    end

    subgraph apis["⚙️ APIs de negócio"]
        NET["backend-clinica-dotnet<br/><b>:8080</b> · .NET 10<br/><i>contexto B2B — clínica</i>"]
        JAVA["backend-tutor-java<br/><b>:8081</b> · Spring Boot<br/><i>contexto B2C — tutor</i>"]
    end

    subgraph luna["🧠 kura-luna-ai · :8000 — serviço de IA"]
        WEB["FastAPI<br/><i>webhook · transcrição · envio</i>"]
        IMS["InboundMessageService<br/><i>orquestração resiliente</i>"]

        subgraph ia["Componentes de IA"]
            TE["<b>TriageEngine</b><br/>motor de regras léxico<br/><i>11 categorias · v1.3</i>"]
            SOAP["<b>montar_soap_draft</b><br/>NLP por vocabulário clínico<br/><i>S · O · A · P</i>"]
            YOLO["<b>PetDetector</b><br/>YOLOv8n — detecção"]
            MNET["<b>BreedClassifier</b><br/>MobileNetV3 — 35 raças"]
            REC["<b>RecomendacaoCuidados</b><br/>recomendação por conteúdo"]
        end

        KC["KuraClient<br/><i>httpx · X-Api-Key</i>"]
    end

    ORA[("🗄️ <b>ORACLE</b> — schema compartilhado<br/>INTERACAO_CANAL · TRIAGEM_LUNA<br/>NOTIFICACAO · RACA · LOG_ERRO<br/>EVENTO_CLINICO · VW_VACINAS_VENCENDO")]

    TUTOR -->|"1 · mensagem"| TW
    TW -->|"2 · webhook assinado"| WEB
    WEB --> IMS
    IMS --> TE
    IMS -->|"3 · quem é este número?"| KC
    KC -->|"4 · REST · X-Api-Key"| NET
    IMS -->|"5 · resposta por urgência"| TW
    TW -->|"6 · resposta"| TUTOR

    APPC -->|"áudio da consulta"| NET
    NET -->|"multipart"| WEB
    WEB --> SOAP
    SOAP <-->|"transcrição"| WH
    WEB -.->|"rascunho — NÃO persiste"| NET

    CLI["luna detect<br/><i>somente CLI</i>"] --> YOLO
    YOLO --> MNET --> REC
    REC -->|"leitura de catálogo"| ORA

    APPT --> JAVA
    APPC --> NET
    NET <--> ORA
    JAVA <--> ORA

    classDef iaBox fill:#1A3A52,stroke:#4A6944,stroke-width:2px,color:#fff
    classDef dbBox fill:#4A6944,stroke:#1A3A52,stroke-width:2px,color:#fff
    class TE,SOAP,YOLO,MNET,REC iaBox
    class ORA dbBox
```

### Os três princípios que este desenho expressa

| Princípio | Como aparece no diagrama |
|---|---|
| **Um banco, duas APIs, sem HTTP entre elas** | `NET` e `JAVA` tocam o mesmo `ORA` e não têm seta entre si. A integração é pelo schema. |
| **A IA escreve *através* da API, não no banco** | `KuraClient → NET → ORA`. A Luna só lê Oracle direto para **catálogo** (`RACA`), onde não há regra de tenancy. |
| **A IA é assistiva** | A seta de transcrição volta pontilhada e rotulada *"NÃO persiste"*. Quem salva é o veterinário. |

---

## 2. Fluxo principal — triagem de urgência por WhatsApp

```mermaid
sequenceDiagram
    autonumber
    actor T as Tutor
    participant TW as Twilio
    participant W as FastAPI<br/>/webhook/twilio
    participant S as InboundMessageService
    participant TE as TriageEngine
    participant K as KuraClient
    participant N as API .NET
    participant O as Oracle

    T->>TW: "meu cachorro está convulsionando"
    TW->>W: POST + X-Twilio-Signature
    W->>W: valida assinatura (403 se inválida)
    W-->>TW: 200 OK (imediato)
    Note over W,S: processamento em BackgroundTask —<br/>o Twilio não espera

    W->>S: processar(msg)
    S->>K: buscar_tutor_por_telefone
    K->>N: GET /api/v1/tutores/telefone/{n}
    N->>O: SELECT TUTOR
    O-->>N: tutor + clínica + pets
    N-->>K: 200 TutorContextoDTO

    S->>K: registrar_interacao (SEMPRE, mesmo sem tutor)
    K->>N: POST /api/v1/luna/interactions
    N->>O: INSERT INTERACAO_CANAL
    N-->>K: 201 {id_interacao}

    alt tutor identificado
        S->>TE: classificar(texto)
        TE-->>S: ALTA · [convulsionando] · score 10
        S->>K: registrar_triagem
        K->>N: POST /api/v1/luna/triage
        N->>O: INSERT TRIAGEM_LUNA
        Note over S: falha aqui NÃO derruba a resposta —<br/>try/except com log
    else tutor desconhecido
        Note over S: interação gravada com ID_CLINICA nulo.<br/>Sem triagem. Resposta genérica.
    end

    S->>TW: resposta conforme urgência
    TW->>T: "Identificamos sintomas que requerem<br/>atenção urgente..."
```

**A ordem importa e é deliberada:** a interação é registrada (passo 8) **antes** da triagem
(passo 12). Se a classificação ou o registro dela falharem, a mensagem do tutor já está
salva. O sinal nunca se perde.

---

## 3. Fluxo — transcrição de consulta em rascunho SOAP

```mermaid
sequenceDiagram
    autonumber
    actor V as Veterinário
    participant A as App da Clínica
    participant N as API .NET
    participant L as Luna /transcricao
    participant W as OpenAI Whisper

    V->>A: grava áudio narrando a consulta
    A->>N: POST /eventos-clinicos/{id}/transcricao
    N->>L: multipart + X-API-Key
    L->>L: valida formato (mp3/m4a/wav) e tamanho (≤25MB)
    L->>W: POST /v1/audio/transcriptions

    alt Whisper responde
        W-->>L: texto transcrito
        L->>L: montar_soap_draft — classifica frases
        L-->>N: 200 {transcricao, soap:{s,o,a,p}}
    else Whisper falha ou sem OPENAI_API_KEY
        L-->>N: 200 {transcricao:null, soap:null}
        Note over L,N: degradação silenciosa por desenho —<br/>NUNCA 500. A consulta não para.
    end

    N-->>A: rascunho (ou formulário vazio)
    V->>A: revisa, corrige e confirma
    A->>N: POST evento clínico definitivo
    N->>N: grava EVENTO_CLINICO
```

> ⚠️ **A degradação é silenciosa de propósito, e isso tem um custo:** sem
> `OPENAI_API_KEY` configurada, o rascunho volta vazio **sem nenhum erro visível**. Numa
> demonstração, isso é indistinguível de "o veterinário não gravou áudio". Conferir a
> variável antes de demonstrar.

---

## 4. Fluxo — identificação de raça por foto

```mermaid
sequenceDiagram
    autonumber
    actor U as Operador
    participant C as CLI luna detect
    participant D as PetDetector<br/>(YOLOv8n)
    participant B as BreedClassifier<br/>(MobileNetV3)
    participant R as RecomendacaoCuidados
    participant O as Oracle RACA

    U->>C: luna detect foto.jpg
    C->>D: detectar(caminho)
    D-->>C: [Deteccao(dog, 0.94, bbox)]

    alt nenhum pet detectado
        C-->>U: "Nenhum pet detectado na imagem."
    else pet detectado
        C->>B: classificar_raca(recorte do bbox top-1)
        B-->>C: ("Labrador Retriever", 0.91)
        C->>R: gerar("Labrador Retriever")
        R->>O: SELECT DS_PREDISPOSICAO WHERE UPPER(NM_RACA)=...

        alt raça tem predisposição registrada
            O-->>R: texto clínico
            R-->>C: recomendação preventiva
        else raça sem predisposição
            R-->>C: None
            Note over R: o sistema fica calado —<br/>não inventa recomendação
        end

        C-->>U: raça + confiança + recomendação + imagem anotada
    end
```

> 🔴 **Este fluxo não é executável a partir do repositório.** O checkpoint do
> `BreedClassifier` não é versionado, e este pipeline **não tem endpoint HTTP** — só existe
> pela CLI. Ver [`IA_DEFINICAO.md`](IA_DEFINICAO.md) §9.2.

---

## 5. Componentes internos e composition root

```mermaid
graph LR
    subgraph roots["Pontos de entrada"]
        SERVE["luna serve<br/><i>uvicorn</i>"]
        JOB["luna run-job"]
        DET["luna detect"]
    end

    subgraph app["src/web — camada HTTP"]
        FA["create_app(settings)"]
        R1["/webhook/twilio/whatsapp"]
        R2["/transcricao"]
        R3["/whatsapp/enviar"]
        R4["/health · /ready"]
    end

    subgraph svc["src/services — orquestração"]
        IMS["InboundMessageService"]
        LVS["LembreteVacinaService"]
        IRS["IdentificacaoRacaService"]
        TS["transcricao_service"]
    end

    subgraph portas["Portas — typing.Protocol"]
        IK["IKuraClient"]
        IT["ITwilioGateway"]
        IW["IWhisperGateway"]
    end

    subgraph infra["Adaptadores"]
        KC["KuraClient · httpx"]
        TG["TwilioGateway"]
        WG["WhisperGateway"]
        REPO["Repositories · oracledb"]
    end

    SERVE --> FA --> R1 & R2 & R3 & R4
    JOB --> LVS
    DET --> IRS
    R1 --> IMS
    R2 --> TS
    IMS --> IK & IT
    LVS --> IT & REPO
    TS --> IW
    IK -.implementa.-> KC
    IT -.implementa.-> TG
    IW -.implementa.-> WG
```

**Por que `Protocol` e não classe base abstrata:** o teste substitui o adaptador sem
herdar de nada — basta ter os métodos com a assinatura certa. Isso mantém os testes
independentes da hierarquia de classes de produção.

**Por que imports preguiçosos no composition root:** `luna run-job` e `luna serve` não
carregam `torch` nem `ultralytics`, que só o `luna detect` precisa. Sem isso, subir o
servidor pagaria segundos de import e centenas de megabytes de memória por um pipeline que
aquele processo nunca usa.

---

## 6. Fila de triagem, lembrete de vacina e o scheduler (`LU-04`/`LU-08`)

### 6.1 Fila de triagem — leitura pelo app da clínica

A Luna **não expõe** a fila; quem consulta é o app da clínica, direto no `.NET`, por JWT:

```
GET /api/v1/luna/triagens   (Authorization: Bearer <JWT de clínica>)
```

`idClinica` sai sempre do token (`IClinicaContext`), nunca de parâmetro de URL — isolamento
multi-tenant provado por mutação no G4 (`LU-16`, duas mutações mordendo: predicado primário e
o `IdClinica` do JOIN com `INTERACAO_CANAL`).

### 6.2 Lembrete de vacina — job, gatilho manual e scheduler

```mermaid
sequenceDiagram
    autonumber
    participant S as AsyncIOScheduler<br/>(lifespan, opcional)
    participant M as Gatilho manual<br/>POST /jobs/lembrete-vacina/executar
    participant L as LembreteVacinaService
    participant O as Oracle · VW_VACINAS_VENCENDO
    participant TW as TwilioGateway

    alt LUNA_SCHEDULER_ENABLED=true
        S->>L: tick diário, hora = LUNA_SCHEDULER_HORA (default 8)
    else scheduler desligado (default)
        M->>L: chamada sob demanda (X-API-Key)
    end
    L->>O: SELECT vacinas a vencer (janela de dias configurada)
    L->>L: idempotência por VACINA — 1 lembrete por vacina, não por 24h fixo
    alt Twilio configurado
        L->>TW: envia lembrete
        TW-->>L: sid
        L->>O: INSERT NOTIFICACAO (ENVIADA)
    else credencial ausente
        L-->>M: 503 declarado {"detail":"Mensageria indisponível..."}
        Note over L: nasce ANTES do serviço rodar — 0 linha em NOTIFICACAO
    end
```

- **`LUNA_SCHEDULER_ENABLED` tem default `false`** (`src/config/settings.py:43`) — o container
  padrão **não** dispara lembrete sozinho; só o gatilho manual (`POST
  /jobs/lembrete-vacina/executar`) roda, e só quando chamado. Ligar o scheduler é decisão
  explícita de ambiente, para não rodar em mais de uma réplica.
- **Idempotência por vacina** (ruling do Felipe, 15/09): um `asyncio.Lock` evita o tick e o
  gatilho manual rodarem simultaneamente; a janela de idempotência é derivada da antecedência
  configurada (`24 × dias_antecedência` horas), não um valor fixo de 24h.
- **Verificado no G4 (`LU-16`), e é o estado real desta máquina:** com `TWILIO_SID`/`TWILIO_TOKEN`
  vazios no processo, o gatilho devolve `503` **honesto** (nunca `500` cru) e **nenhuma linha**
  é gravada em `NOTIFICACAO` — a falha nasce na dependência, antes do serviço rodar. O ciclo
  completo (`NOTIFICACAO` com a clínica certa, 2º disparo bloqueado, tutor vendo no app) **não
  foi verificado ao vivo** nesta máquina; ver `IA_DEFINICAO.md` §9 e o ledger `lu-16-revisao.md`.

---

## 7. Decisões de design

| Decisão | Alternativa descartada | Por quê |
|---|---|---|
| Motor de regras na triagem | LLM | Auditabilidade, risco de alucinação em contexto clínico, custo e latência — ver `IA_DEFINICAO.md` §3 |
| Escrita via API .NET | Escrita direta no Oracle | Regra de multi-tenancy em um lugar só. Duas implementações divergiriam |
| `BackgroundTask` no webhook | Processamento síncrono | O Twilio marca timeout e reentrega. `200` imediato evita duplicidade |
| Falha de telemetria não bloqueia | Propagar erro | O tutor precisa de resposta mesmo com o .NET fora do ar |
| Interação gravada antes da triagem | Gravar tudo junto no fim | Se a triagem falhar, a mensagem não se perde |
| `secrets.compare_digest` | `==` | Comparação comum vaza a chave por tempo de execução |
| `raise ... from None` | `raise ... from exc` | Encadear causa faz `logger.exception` reimprimir o telefone do tutor — ver `IA_DEFINICAO.md` §11.2 |
| Degradar transcrição com `200` | Devolver `500` | A consulta não pode parar porque a IA parou |
| `RecomendacaoCuidados` devolve `None` | Texto genérico de fallback | Não inventar recomendação para raça desconhecida |
