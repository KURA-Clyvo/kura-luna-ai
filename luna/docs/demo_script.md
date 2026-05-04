# Roteiro de Demo — Luna · FIAP Challenge 2026

**Duração total:** 5 minutos  
**Apresentador:** 1 pessoa (terminal visível em tela cheia)  
**Pré-requisito:** virtualenv ativado, `.env` configurado, Oracle e Twilio Sandbox ativos

---

## 00:00 – 00:30 | Introdução (30 s)

**Fala sugerida:**
> "Sou o Felipe, e vou apresentar a Luna — o serviço de comunicação proativa e IA veterinária do Kura.
> A Luna tem duas responsabilidades principais: enviar lembretes de vacinas por WhatsApp antes do vencimento,
> e identificar a raça de um pet por foto para gerar recomendações clínicas personalizadas.
> Tudo isso integrado ao nosso banco Oracle 19c e ao Twilio Sandbox."

---

## 00:30 – 01:00 | Setup do ambiente (30 s)

Mostrar no terminal:

```bash
# Estrutura do projeto
ls luna/src/

# Variáveis de ambiente configuradas
cat .env
```

**Fala sugerida:**
> "O projeto usa Pydantic Settings para carregar as credenciais do `.env`.
> Oracle, Twilio e caminhos dos modelos de IA ficam todos aqui — sem hard-code no código."

---

## 01:00 – 02:30 | Demo 1 — Lembrete de vacinas (1 min 30 s)

```bash
# Executar o job de lembretes
luna run-job
```

**Saída esperada:**
```
Concluído — total: 3 | enviadas: 2 | falhas: 0 | já enviadas: 1
```

**Fala sugerida:**
> "O job consultou a view `VW_VACINAS_VENCENDO` no Oracle, encontrou 3 pets com vacinas
> vencendo em até 7 dias. Um já tinha notificação enviada nas últimas 24 horas — idempotência
> garantida. Dois lembretes foram disparados via WhatsApp pelo Twilio."

Mostrar a mensagem recebida no WhatsApp Sandbox (print ou celular ao vivo):

```
Olá, João! 🐾

A vacina *Antirrábica* do(a) *Rex* vence em 5 dias.

Agende o reforço com a Clínica Kura para manter a proteção em dia.

Qualquer dúvida, estamos aqui! — Equipe Clínica Kura
```

**Fala sugerida:**
> "Cada notificação é registrada na tabela `NOTIFICACAO` com status `ENVIADA`. Se o Twilio
> falhar em algum item, o erro vai para `LOG_ERRO` e o restante do lote continua normalmente."

---

## 02:30 – 04:00 | Demo 2 — Identificação de raça (1 min 30 s)

```bash
# Detectar raça em uma foto de Labrador
luna detect fotos/labrador_teste.jpg
```

**Saída esperada:**
```
Pet detectado: Labrador Retriever (confiança: 91.3%)

Recomendação clínica:
Detectamos que seu pet é da raça *Labrador Retriever*. Raças desta
linhagem têm predisposição a: displasia coxofemoral, obesidade.
Recomendamos uma avaliação preventiva com seu veterinário —
a detecção precoce faz toda a diferença! 🏥

Imagem anotada salva em: fotos/labrador_teste_anotada.jpg
```

Abrir a imagem anotada (`labrador_teste_anotada.jpg`) — mostra o bounding box verde com o rótulo "Labrador Retriever 91%".

**Fala sugerida:**
> "O pipeline tem três etapas: primeiro o YOLOv8n detecta que há um cão na imagem.
> Em seguida o MobileNetV3, treinado em 120 raças Stanford Dogs, classifica a raça
> com 91% de confiança. Por último, cruzamos com a tabela `RACA` no Oracle — que a
> equipe de backend populou com predisposições clínicas — e geramos uma recomendação
> personalizada para o tutor."

---

## 04:00 – 04:45 | Suite de testes (45 s)

```bash
pytest -m "not slow" -q
```

**Saída esperada:**
```
..........................................................   [100%]
58 passed in 0.87s
```

```bash
# Teste de integração E2E
pytest tests/integration/ -v
```

**Fala sugerida:**
> "Cobrimos 85% do código com testes unitários que nunca tocam Oracle nem Twilio real.
> O teste E2E exercita o fluxo completo — 3 vacinas, 2 enviadas, 1 com falha no Twilio —
> em menos de 2 segundos, usando mocks apenas nos dois adaptadores externos."

---

## 04:45 – 05:00 | Conclusão (15 s)

**Fala sugerida:**
> "A Luna é o braço de comunicação proativa do Kura: notifica tutores no momento certo
> e entrega inteligência clínica via visão computacional, tudo integrado ao Oracle
> compartilhado com os demais serviços da plataforma. Obrigado."

---

## Checklist pré-gravação

- [ ] Virtualenv ativado e `luna --help` funcionando
- [ ] `.env` com Oracle e Twilio configurados e testados
- [ ] Pesos `yolov8n.pt` e `breed_classifier.pth` presentes nos caminhos do `.env`
- [ ] Foto de teste em `fotos/labrador_teste.jpg` preparada
- [ ] WhatsApp Sandbox ativo e celular com o número de destino configurado
- [ ] Terminal em fonte ≥ 18pt para legibilidade na gravação
- [ ] `pytest -m "not slow" -q` passando localmente antes de gravar
