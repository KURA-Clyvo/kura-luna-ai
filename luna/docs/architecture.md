# Arquitetura — Luna

## Visão geral

Luna segue uma arquitetura em camadas estrita, com injeção de dependência no construtor e composition root centralizado em `cli/main.py`. Nenhum service ou repository instancia suas próprias dependências.

```
cli/main.py  (Composition Root)
     │
     ├── LembreteVacinaService
     │       ├── VacinaRepository        → Oracle VW_VACINAS_VENCENDO (leitura)
     │       ├── NotificacaoRepository   → Oracle NOTIFICACAO (escrita)
     │       ├── TwilioGateway           → Twilio REST API
     │       └── LogErroRepository       → Oracle LOG_ERRO (fail-safe)
     │
     └── IdentificacaoRacaService
             ├── PetDetector             → YOLOv8n (ultralytics)
             ├── BreedClassifier         → MobileNetV3 (torchvision)
             └── RecomendacaoCuidados
                     └── RacaRepository  → Oracle RACA (leitura)
```

---

## Diagrama de componentes

```mermaid
graph TB
    subgraph cli["CLI — Composition Root"]
        CMD1["luna run-job"]
        CMD2["luna detect &lt;caminho&gt;"]
    end

    subgraph services["Services"]
        SVC1["LembreteVacinaService"]
        SVC2["IdentificacaoRacaService"]
    end

    subgraph ai["AI Pipeline"]
        AI1["PetDetector\n(YOLOv8n)"]
        AI2["BreedClassifier\n(MobileNetV3)"]
        AI3["RecomendacaoCuidados"]
    end

    subgraph repos["Repositories"]
        R1["VacinaRepository"]
        R2["NotificacaoRepository"]
        R3["RacaRepository"]
        R4["LogErroRepository"]
    end

    subgraph ext["Sistemas Externos"]
        ORC[("Oracle 19c")]
        TWI["Twilio\nWhatsApp Sandbox"]
    end

    CMD1 --> SVC1
    CMD2 --> SVC2

    SVC1 --> R1
    SVC1 --> R2
    SVC1 --> R4
    SVC1 -->|"ITwilioGateway"| TWI

    SVC2 --> AI1
    SVC2 --> AI2
    SVC2 --> AI3
    AI3 --> R3

    R1 -->|"VW_VACINAS_VENCENDO"| ORC
    R2 -->|"NOTIFICACAO"| ORC
    R3 -->|"RACA"| ORC
    R4 -->|"LOG_ERRO\n(fail-safe)"| ORC
```

---

## Fluxo: lembrete de vacinas

```mermaid
sequenceDiagram
    participant CLI as luna run-job
    participant SVC as LembreteVacinaService
    participant VR  as VacinaRepository
    participant NR  as NotificacaoRepository
    participant TW  as TwilioGateway
    participant LR  as LogErroRepository
    participant ORC as Oracle 19c
    participant WA  as WhatsApp (Twilio)

    CLI->>SVC: executar()
    SVC->>VR: listar_vencendo_em(dias=7)
    VR->>ORC: SELECT VW_VACINAS_VENCENDO WHERE DIAS_RESTANTES <= 7
    ORC-->>VR: [rows]
    VR-->>SVC: [VacinaVencendo...]

    loop Para cada VacinaVencendo
        SVC->>NR: existe_pendente_para_vacina()
        NR->>ORC: SELECT COUNT(*) NOTIFICACAO (janela 24h)
        ORC-->>NR: 0
        SVC->>NR: criar(PENDENTE)
        NR->>ORC: INSERT NOTIFICACAO RETURNING ID
        ORC-->>NR: id_notificacao
        SVC->>TW: enviar_whatsapp(numero, mensagem)
        TW->>WA: POST /Messages
        alt Sucesso
            WA-->>TW: SID
            SVC->>NR: marcar_enviada(id, dt)
            NR->>ORC: UPDATE NOTIFICACAO SET ST_STATUS='ENVIADA'
        else MessagingError
            SVC->>NR: marcar_falha(id, erro)
            NR->>ORC: UPDATE NOTIFICACAO SET ST_STATUS='FALHA'
            SVC->>LR: registrar(exc)
            LR->>ORC: INSERT LOG_ERRO
        end
    end

    SVC-->>CLI: ResumoExecucao(total, enviadas, falhas, ja_enviadas)
```

---

## Fluxo: identificação de raça

```mermaid
sequenceDiagram
    participant CLI  as luna detect foto.jpg
    participant SVC  as IdentificacaoRacaService
    participant DET  as PetDetector (YOLOv8n)
    participant CLS  as BreedClassifier (MobileNetV3)
    participant REC  as RecomendacaoCuidados
    participant RR   as RacaRepository
    participant ORC  as Oracle RACA

    CLI->>SVC: processar_foto("foto.jpg")
    SVC->>DET: detectar("foto.jpg")
    DET-->>SVC: [Deteccao(classe='dog', conf=0.96, bbox=(...))]

    SVC->>CLS: classificar_raca(recorte_bbox)
    CLS-->>SVC: ("Labrador Retriever", 0.91)

    SVC->>REC: gerar("Labrador Retriever")
    REC->>RR: buscar_por_nome("Labrador Retriever")
    RR->>ORC: SELECT RACA WHERE UPPER(NM_RACA) = UPPER(:nm)
    ORC-->>RR: Raca(ds_predisposicao="displasia coxofemoral, obesidade")
    RR-->>REC: Raca
    REC-->>SVC: "Detectamos que seu pet é da raça *Labrador*..."

    SVC->>SVC: _anotar(imagem, deteccoes, raca, conf) via cv2
    SVC->>SVC: _salvar_anotada → "foto_anotada.jpg"
    SVC-->>CLI: ResultadoIdentificacao(raca_top1, confianca, recomendacao, imagem_anotada_path)
```

---

## Decisões de design

| Decisão | Justificativa |
|---------|--------------|
| Injeção de dependência no construtor | Testabilidade — mocks trocados sem tocar produção |
| `OracleConnectionPool` como singleton | Custo de criação de pool; criado uma vez no composition root |
| `LogErroRepository` fail-safe | Falha no log nunca mascara a exceção original nem derruba o lote |
| `LembreteVacinaService` resiliente por item | Uma falha Twilio não cancela os demais lembretes do lote |
| Idempotência com janela 24 h | Evita duplicação se o job for reiniciado por falha de infra |
| Lazy imports em `cli/main.py` | `luna run-job` não carrega torch/ultralytics; `luna detect` não carrega Twilio |
| `oracledb` thin mode | Elimina dependência do Oracle Instant Client no ambiente de deploy |
| Bind variables (`:param`) | Prevenção de SQL injection e reuso do plano de execução Oracle |
