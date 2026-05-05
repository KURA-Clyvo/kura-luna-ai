# Luna v2.0 — Runbook Operacional

## Pré-requisitos

- Python 3.12, virtualenv ativado, `pip install -r requirements-dev.txt && pip install -e .`
- `.env` preenchido a partir de `.env.example`
- [ngrok](https://ngrok.com/download) instalado (para expor o servidor em desenvolvimento)
- Conta Twilio com Sandbox WhatsApp configurado

---

## 1. Subir localmente

```powershell
# No diretório luna/
luna serve --host 0.0.0.0 --port 8000
```

O servidor estará disponível em `http://localhost:8000`. Verifique:

```
GET http://localhost:8000/health   → {"status":"ok"}
GET http://localhost:8000/ready    → {"status":"ok","kura_api":true,"oracle":true}
```

---

## 2. Expor com ngrok

```bash
ngrok http 8000
```

O ngrok exibirá uma URL pública, ex.:

```
Forwarding  https://abcd-1234.ngrok-free.app -> http://localhost:8000
```

Copie a URL completa do webhook:

```
https://abcd-1234.ngrok-free.app/webhook/twilio/whatsapp
```

Atualize o `.env`:

```env
WEBHOOK_PUBLIC_URL=https://abcd-1234.ngrok-free.app/webhook/twilio/whatsapp
```

Reinicie o servidor após alterar o `.env`.

---

## 3. Configurar URL no Console Twilio Sandbox

1. Acesse [console.twilio.com/us1/develop/sms/settings/whatsapp-sandbox](https://console.twilio.com/us1/develop/sms/settings/whatsapp-sandbox)
2. Em **"When a message comes in"**, cole a URL do ngrok:
   ```
   https://abcd-1234.ngrok-free.app/webhook/twilio/whatsapp
   ```
3. Método: `HTTP POST`
4. Salve.

Agora qualquer mensagem enviada para o número Sandbox do Twilio será encaminhada para a Luna.

---

## 4. Testar o fluxo completo

Envie uma mensagem WhatsApp para o número Sandbox (ex.: `+1 415 523 8886`) com o conteúdo:

```
meu cachorro está convulsionando
```

Verifique nos logs do servidor:

```
INFO  InboundMessageService — urgencia=ALTA, id_interacao=X
```

E aguarde a resposta automática no WhatsApp:

> "Identificamos sintomas que requerem atenção urgente. Estamos notificando seu veterinário..."

---

## 5. Verificar saúde em produção

```bash
curl -s https://<seu-dominio>/ready | python -m json.tool
```

Saída esperada:

```json
{
  "status": "ok",
  "kura_api": true,
  "oracle": true
}
```

Qualquer campo `false` indica degradação. Verifique logs do servidor e conectividade com Oracle/Kura API.

---

## 6. Variáveis de ambiente relevantes para o servidor

| Variável | Descrição |
|---|---|
| `KURA_API_BASE_URL` | URL base da API .NET (ex: `http://kura-api:5000`) |
| `KURA_API_KEY` | Bearer token para autenticação Luna → .NET |
| `KURA_API_TIMEOUT` | Timeout HTTP em segundos (default: 10) |
| `WEBHOOK_PUBLIC_URL` | URL pública do webhook (usada pelo Twilio para validação de assinatura) |
| `LUNA_HTTP_PORT` | Porta HTTP (default: 8000) |
