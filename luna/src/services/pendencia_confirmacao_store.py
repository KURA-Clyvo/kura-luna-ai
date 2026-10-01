"""Mapa efêmero em memória de pendências de confirmação D-1 (REC-16, G0 item 11).

Decisão de desenho (opção 'a' do G0 item 11, recomendada no brief de despacho): o
job que envia o lembrete (`confirmacao_d1_job.py`/`ConfirmacaoD1Service`) registra
aqui telefone -> (id_agendamento, id_tutor, expiração) no momento em que confirma
o envio de verdade (status Twilio terminal de sucesso — ver G0 item 10). O
`InboundMessageService` consulta este mapa ANTES da triagem para decidir se uma
resposta curta reconhecida deve virar uma chamada a `resposta-confirmacao` em vez
de seguir para a IA.

Por que não existe uma query "buscar pendência por telefone" no `.NET`: a REC-15
só expõe a listagem GLOBAL do dia (`GET confirmacao-pendente?data=`) e a escrita
por id (`POST .../resposta-confirmacao`, que exige `idAgendamento`+`idTutor`).
Abrir um endpoint novo só para isto ampliaria um escopo já fechado sem necessidade
comprovada — o estado efêmero do lado Python resolve sem tocar o `.NET` de novo.

Efêmero por natureza, e isso é aceitável: perdido em restart do processo. O
`.NET` continua sendo a fonte de verdade (`DT_LEMBRETE_CONFIRMACAO`); um restart
no meio do dia só faz o tutor perder a janela de resposta AUTOMÁTICA (a mensagem
dele cai na triagem normal em vez de na transição de status) — não há perda de
dado, só degradação de uma conveniência.

Chave: telefone no MESMO formato que `twilio_inbound.chave_telefone` produz para
`InboundMessage.numero_origem` (dígitos, sem prefixo `whatsapp:`/`+`) — single
source of truth para as duas direções (job grava com essa chave a partir de
`DS_WHATSAPP` em E.164; o webhook inbound lê com essa chave a partir do `From`
do Twilio).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class PendenciaConfirmacao:
    """Uma pendência de confirmação D-1 aguardando resposta do tutor."""

    id_agendamento: int
    id_tutor: int
    expira_em: datetime  # timezone-aware (UTC)


class PendenciaConfirmacaoStore:
    """Mapa telefone -> `PendenciaConfirmacao`, com expiração.

    Não é thread-safe por design explícito: todo acesso acontece dentro do loop
    de eventos asyncio único do processo (mesma premissa de `app.state.
    lembrete_lock`), e nenhuma seção crítica aqui contém `await` — mutação de
    dict em CPython é atômica por GIL, então não há corrida real a proteger.
    """

    def __init__(self) -> None:
        self._por_telefone: dict[str, PendenciaConfirmacao] = {}

    def registrar(self, telefone: str, pendencia: PendenciaConfirmacao) -> None:
        """Registra (ou substitui) a pendência deste telefone."""
        self._por_telefone[telefone] = pendencia

    def buscar(self, telefone: str) -> PendenciaConfirmacao | None:
        """Devolve a pendência ativa deste telefone, ou None (ausente/expirada).

        Uma pendência expirada é removida como efeito colateral da busca (limpeza
        preguiçosa — não há necessidade de um job de limpeza periódico separado
        para um mapa deste tamanho/tempo de vida)."""
        pendencia = self._por_telefone.get(telefone)
        if pendencia is None:
            return None
        if pendencia.expira_em <= datetime.now(tz=timezone.utc):
            del self._por_telefone[telefone]
            return None
        return pendencia

    def remover(self, telefone: str) -> None:
        """Remove a pendência deste telefone (resposta já processada)."""
        self._por_telefone.pop(telefone, None)

    def ja_processado_hoje(self, id_agendamento: int) -> bool:
        """True se já existe pendência ATIVA para este agendamento.

        Usado pelo job (REC-16) como defesa em profundidade contra 2 execuções
        no mesmo dia mandarem 2 mensagens para o MESMO agendamento — mesmo que o
        `.NET` ainda devolva o candidato numa 2ª chamada (ex.: corrida entre o
        `POST lembrete-enviado` da 1ª execução e um `GET confirmacao-pendente`
        feito antes dele persistir). A exclusão real e definitiva continua sendo
        `DT_LEMBRETE_CONFIRMACAO IS NULL` do lado `.NET` — isto é só a segunda
        linha de defesa, local ao processo.
        """
        agora = datetime.now(tz=timezone.utc)
        return any(
            p.id_agendamento == id_agendamento and p.expira_em > agora
            for p in self._por_telefone.values()
        )
