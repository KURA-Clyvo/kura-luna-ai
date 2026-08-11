# Luna v2.0 — Contratos de API com a camada .NET Kura

Este documento descreve os endpoints que a Luna consome da API .NET.

> ⚠️ **Verificado contra o contrato real do servidor em 2026-08-08** (TASK-68,
> `KURA_BACKLOG_FIX_6`). Antes desta revisão, este documento descrevia rotas
> (`/api/...`, sem `/v1`) e um esquema de autenticação (`Authorization: Bearer`)
> que **nunca existiram no servidor** — a Luna nunca tinha sido auditada como
> cliente HTTP até este backlog. Os 3 endpoints abaixo foram implementados pela
> TASK-67 (`backend-clinica-dotnet`) sobre a tabela `INTERACAO_CANAL` criada
> pela TASK-66 (`backend-tutor-java`, `V15__interacao_canal.sql`). Fonte da
> verdade usada para esta revisão: snapshot congelado do commit `823f400` dos
> controllers/DTOs C# (`LunaController`, `TutoresController`,
> `LunaApiKeyAuthFilter`, DTOs em `Kura.Application.DTOs.Luna`).

---

## Autenticação

Os 3 endpoints consumidos pela Luna (server-a-server, nunca JWT de clínica)
exigem o header:

```
X-Api-Key: <chave>
```

A chave é a mesma nos dois lados a partir da variável `LUNA_API_KEY` cabeada
no `docker-compose.yml`: o lado .NET a lê como `Luna:ApiKey`
(env `Luna__ApiKey`) via `LunaApiKeyAuthFilter`; o lado Luna a lê como
`KURA_API_KEY` (`src/config/settings.py`). Nomes de variável diferentes nos
dois serviços, mesmo valor — não confundir com `Luna:InboundApiKey`
(direção oposta, .NET → Luna, usada pela FEAT-02/transcrição) nem com
`IoT:ApiKey` (domínio não relacionado).

Requisição sem o header, ou com valor incorreto, recebe `401`.

---

## Endpoints consumidos

### GET /api/v1/tutores/telefone/{numero}

Busca o contexto do tutor (clínica + pets) pelo número de WhatsApp (sem
prefixo `whatsapp:` e sem `+`).

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

`nm_raca` é opcional (`null` quando o pet não tem raça cadastrada).

**Resposta 401:** API Key ausente ou inválida.

**Resposta 404:** Nenhum tutor ativo com esse telefone. Legítimo — significa
"tutor desconhecido/não cadastrado", não erro. A Luna registra a interação
mesmo assim, com `id_tutor=null`, e envia fallback ao usuário — desde a
TASK-77 (`backend-clinica-dotnet`), `/interactions` aceita esse payload com
`201` (ver seção abaixo; a divergência que existia aqui foi fechada).

**Resposta 5xx:** Luna trata como falha irrecuperável, envia fallback ao
usuário e registra em `LOG_ERRO`.

---

### POST /api/v1/luna/interactions

Registra uma interação de canal (inbound ou outbound) recebida ou enviada
pela IA Luna. O servidor deriva `id_clinica` a partir do tutor.

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
| `id_tutor` | int \| null | Chave sempre presente; valor pode ser `null` | `null` = tutor desconhecido. Servidor grava a interação com `id_clinica`/`id_tutor` nulos (TASK-77, `V16__interacao_canal_clinica_nullable.sql`) |
| `ds_canal` | string | Sim | `WHATSAPP`, `EMAIL`, `SMS` |
| `ds_direcao` | string | Sim | `INBOUND`, `OUTBOUND` |
| `ds_conteudo` | string | Sim | Corpo da mensagem |
| `dt_recebimento` | ISO 8601 UTC | Sim | |
| `ds_metadados` | object \| null | Não | Dados extras (ex.: IDs de mídia do WhatsApp); persistido como JSON bruto em `DS_METADADOS` (CLOB), sem shape fixo |

**Resposta 201:**
```json
{
  "id_interacao": 100
}
```

O campo `id_interacao` é obrigatório na resposta — a Luna o usa para vincular
a triagem.

**Resposta 400:** Payload malformado (`ds_canal`/`ds_direcao` fora do enum,
`ds_conteudo` vazio).

**Resposta 404:** `id_tutor` informado não corresponde a um tutor existente
(caso de payload inconsistente — um `id_tutor` que a Luna mandou e não
existe. Diferente de `id_tutor` ausente por tutor não cadastrado, que não é
erro — ver abaixo).

> ✅ **Divergência fechada pela TASK-77/TASK-78 (`FIX_7`).** Até a TASK-67,
> `id_tutor=null` respondia `422` (*"servidor não consegue derivar
> `id_clinica` sem um tutor"*) — mas `InboundMessageService._processar_interno`
> (`luna/src/services/inbound_message_service.py`) sempre envia
> `id_tutor=null` quando `buscar_tutor_por_telefone` devolve `None` (tutor
> desconhecido é o fluxo real esperado em WhatsApp, não uma exceção). Como
> `registrar_interacao` não está dentro de um `try/except` dedicado em
> `_processar_interno`, o `422` propagava até o `except Exception` genérico de
> `processar()`: a Luna ainda enviava o fallback ao tutor (nunca crashava),
> mas gravava uma entrada FALSA em `LOG_ERRO` e **nenhuma** `INTERACAO_CANAL`
> era persistida — perda de dado de analytics para todo o volume de tutores
> desconhecidos.
>
> Decisão de produto do Felipe (TASK-77, `V16__interacao_canal_clinica_
> nullable.sql` do `backend-tutor-java`, TASK-76): `INTERACAO_CANAL.ID_CLINICA`
> passou a ser nullable, e `id_tutor=null` agora responde `201`, gravando a
> interação com `id_clinica`/`id_tutor` nulos — o ganho é auditoria (a
> mensagem não se perde), não visibilidade (uma linha com clínica nula é
> invisível a qualquer leitura escopada por clínica). Do lado da Luna
> (TASK-78), nenhuma mudança de código de produção foi necessária —
> `buscar_tutor_por_telefone` já devolvia `None` de forma graciosa no 404 e
> `_processar_interno` já pulava a triagem com `if tutor:` — o "erro falso"
> em `LOG_ERRO` era consequência exclusiva do `422` que a TASK-77 removeu.
> Provado ponta a ponta (não por leitura) em
> `tests/integration/test_inbound_e2e.py::test_cenario_tutor_desconhecido`
> (interação completa sem gravar `LOG_ERRO`) e
> `::test_cenario_tutor_desconhecido_regressao_pre_task77_grava_log_erro`
> (prova de mordida: reproduz o `422` antigo e confirma que o cenário acima
> teria detectado a regressão).

---

### POST /api/v1/luna/triage

Registra o resultado de uma triagem de IA, ligada à interação que a originou
(`id_interacao`).

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

`sintomas`, `nr_score` e `ds_recomendacao` não têm coluna própria em
`TRIAGEM_LUNA` — o servidor os compõe dentro de `DS_DESCRICAO` (`VARCHAR2(2000)`).

**Resposta 201:**
```json
{
  "id_triagem": 200
}
```

**Resposta 400:** Payload malformado (`ds_urgencia` fora do enum, campo
obrigatório ausente).

**Resposta 404:** `id_interacao` ou `id_tutor` informados não existem.

**Resposta 422:** `id_interacao` pertence a uma interação de um tutor de
clínica diferente da `id_clinica` derivada do `id_tutor` informado
(checagem de multi-tenancy — `interacao.IdClinica != tutor.IdClinica`).

> **Observação:** Falha neste endpoint (qualquer status, timeout) **não
> impede** a resposta ao tutor. A Luna loga o erro e prossegue —
> `InboundMessageService._processar_interno` envolve a chamada a
> `registrar_triagem` num `try/except Exception` dedicado, separado do
> fluxo principal.

---

### GET /health

Probe de liveness consumido pelo endpoint `/ready` da Luna. Não exige
`X-Api-Key` (fora do escopo do `LunaApiKeyAuthFilter`, que cobre apenas os
3 endpoints acima).

**Resposta esperada:** HTTP `200` com qualquer corpo.

Qualquer outra resposta (4xx, 5xx, timeout) faz o `/ready` da Luna reportar
`kura_api: false`.

---

## Regras de contrato

1. `id_interacao` e `id_triagem` devem ser inteiros positivos únicos.
2. O campo `dt_recebimento` usa sempre UTC com sufixo `Z`.
3. `ds_canal` e `ds_direcao` são case-sensitive — enviar exatamente como
   documentado.
4. A Luna chama `/triage` apenas se o tutor for encontrado (`id_tutor !=
   null`).
5. A Luna não envia `ds_metadados` por ora — pode ser ignorado ou armazenado
   como `null`.
6. Todas as respostas de erro (`4xx`/`5xx`) usam o shape padrão
   `ProblemDetails` do ASP.NET Core, exceto `401` do `LunaApiKeyAuthFilter`
   (resultado vazio — o filtro roda antes do model binding).

## Divergências conhecidas (não corrigidas nesta revisão)

- O cliente Python (`src/integration/kura_client.py`) só distingue `404` de
  `>= 500` (`_handle_error_status` levanta `KuraApiError` só para `5xx`).
  Um `422` (ex.: mismatch de tenant em `/triage`) cai em
  `resp.raise_for_status()` e propaga como `httpx.HTTPStatusError` cru, não
  como uma exceção tipada do módulo `src/integration/exceptions.py`.
  Verificado que isso não quebra o fluxo — `_processar_interno` já envolve a
  chamada a `registrar_triagem` num `try/except Exception` genérico (não
  bloqueia a resposta ao tutor) — mas é uma inconsistência de tipagem sem
  correção nesta task (ver relatório da TASK-68, §4).
- **Achado lateral, fora do escopo do brief, mas com implicação de LGPD real:**
  o log de request nativo do próprio `httpx` (nível INFO, formato "HTTP
  Request: GET .../telefone/{numero} ...") embute o número de telefone cru
  na URL e é emitido de verdade em produção — `luna serve`
  (`src/cli/main.py:123`) chama `setup_logging(settings.LOG_LEVEL)` (default
  `INFO`) com `disable_existing_loggers: False`, então o logger `httpx`
  herda o nível INFO do root e grava tanto no console quanto no arquivo
  rotativo `luna.log`. Esse comportamento é **anterior a esta task** — a URL
  sempre teve o telefone cru, TASK-68 só trocou o prefixo (`/v1`) — e nunca
  tinha sido pego porque nenhum teste anterior usava `caplog` sem escopo de
  logger nesse caminho (descoberto ao escrever o teste de §3.4 desta task:
  a primeira versão do teste, sem filtrar por `record.name`, falhou contra
  o próprio código novo por causa deste log do httpx, não por causa do log
  que esta task adicionou). Fora do escopo do brief (que pede só para o log
  *novo* desta task não vazar o telefone) e fora do "não refatore
  `kura_client.py` além do necessário" — mitigar isso globalmente (baixar o
  nível do logger `httpx`, ou um filtro de log que redija URLs) é uma
  decisão de escopo maior que não me cabe tomar aqui. Candidato a achado
  emergente para o próximo backlog — ver relatório da TASK-68.
