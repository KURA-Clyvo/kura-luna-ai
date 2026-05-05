# Luna v2.0 — Contratos de API com a camada .NET Kura

Este documento descreve os endpoints que a Luna consome da API .NET. Enviar ao time responsável pelo backend .NET para garantir compatibilidade.

---

## Autenticação

Todas as chamadas incluem o header:

```
Authorization: Bearer <KURA_API_KEY>
```

O valor de `KURA_API_KEY` é configurado no `.env` da Luna e deve ser cadastrado na API .NET como token de serviço.

---

## Endpoints consumidos

### GET /api/tutores/telefone/{numero}

Busca o contexto do tutor pelo número WhatsApp (sem prefixo `whatsapp:` e sem `+`).

**Parâmetro de rota:**
- `numero` — string, ex: `5511999999999`

**Resposta 200:**
```json
{
  "id_tutor": 42,
  "nm_tutor": "Maria Silva",
  "ds_whatsapp": "+5511999999999",
  "id_clinica": 1,
  "pets": [
    {
      "id_pet": 7,
      "nm_pet": "Rex",
      "nm_especie": "Cão",
      "nm_raca": "Pastor Alemão"
    }
  ]
}
```

**Resposta 404:** Tutor não encontrado. A Luna registra a interação com `id_tutor=null` e envia fallback ao usuário. Sem corpo obrigatório.

**Resposta 5xx:** Luna trata como falha irrecuperável, envia fallback ao usuário e registra em `LOG_ERRO`.

---

### POST /api/luna/interactions

Registra uma interação de canal (inbound ou outbound).

**Request body:**
```json
{
  "id_tutor": 42,
  "ds_canal": "WHATSAPP",
  "ds_direcao": "INBOUND",
  "ds_conteudo": "meu pet está doente",
  "dt_recebimento": "2026-05-05T14:30:00Z",
  "ds_metadados": null
}
```

**Campos:**
| Campo | Tipo | Obrigatório | Valores |
|---|---|---|---|
| `id_tutor` | int \| null | Sim | null se tutor desconhecido |
| `ds_canal` | string | Sim | `WHATSAPP`, `EMAIL`, `SMS` |
| `ds_direcao` | string | Sim | `INBOUND`, `OUTBOUND` |
| `ds_conteudo` | string | Sim | Corpo da mensagem |
| `dt_recebimento` | ISO 8601 UTC | Sim | |
| `ds_metadados` | object \| null | Não | Dados extras opcionais |

**Resposta 201:**
```json
{
  "id_interacao": 100
}
```

O campo `id_interacao` é obrigatório na resposta — a Luna o usa para vincular a triagem.

---

### POST /api/luna/triage

Registra o resultado da triagem automática de uma interação.

**Request body:**
```json
{
  "id_interacao": 100,
  "id_tutor": 42,
  "sintomas": ["convulsão"],
  "ds_urgencia": "ALTA",
  "nr_score": 10,
  "ds_recomendacao": "Identificamos sintomas que requerem atenção urgente..."
}
```

**Campos:**
| Campo | Tipo | Obrigatório | Valores |
|---|---|---|---|
| `id_interacao` | int | Sim | ID retornado por `/interactions` |
| `id_tutor` | int | Sim | |
| `sintomas` | string[] | Sim | Keywords detectadas |
| `ds_urgencia` | string | Sim | `ALTA`, `MEDIA`, `BAIXA` |
| `nr_score` | int | Sim | Score acumulado (ALTA=10/match, MEDIA=3, BAIXA=1) |
| `ds_recomendacao` | string | Sim | Texto enviado ao tutor |

**Resposta 201:**
```json
{
  "id_triagem": 200
}
```

> **Observação:** Falha neste endpoint (5xx, timeout) **não impede** a resposta ao tutor. A Luna loga o erro e prossegue.

---

### GET /health

Probe de liveness consumido pelo endpoint `/ready` da Luna.

**Resposta esperada:** HTTP `200` com qualquer corpo.

Qualquer outra resposta (4xx, 5xx, timeout) faz o `/ready` da Luna reportar `kura_api: false`.

---

## Regras de contrato

1. `id_interacao` e `id_triagem` devem ser inteiros positivos únicos.
2. O campo `dt_recebimento` usa sempre UTC com sufixo `Z`.
3. `ds_canal` e `ds_direcao` são case-sensitive — enviar exatamente como documentado.
4. A Luna chama `/triage` apenas se o tutor for encontrado (`id_tutor != null`).
5. A Luna não envia `ds_metadados` por ora — pode ser ignorado ou armazenado como `null`.
