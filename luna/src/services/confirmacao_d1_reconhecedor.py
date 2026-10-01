"""Reconhecimento de resposta curta ao lembrete de confirmação D-1 (REC-16, A-10/a).

Ruling A-10(a) (`KURA_BACKLOG_RECEPCAO.md`): "só conta como resposta de
confirmação uma mensagem CURTA e RECONHECIDA (`1`/`2`/`3`,
`sim`/`não`/`cancelar`/`remarcar`); qualquer outra mensagem vai para a
triagem" — a rede de segurança da Luna (LU-07, orientação de emergência em
toda resposta não-ALTA) nunca pode ser contornada por uma resposta ambígua
que *comece* com uma palavra reconhecida (`"sim, mas ele está vomitando"` é
o exemplo literal do backlog). Por isso o reconhecimento é por IGUALDADE do
texto inteiro normalizado, nunca por substring/prefixo.

Mapeamento (G0 item 11 do backlog lista 4 palavras para 3 ações — "não" e
"cancelar" mapeiam para a MESMA ação, cancelamento):
    1 / sim                -> SIM        (confirma presença)
    2 / não / cancelar     -> CANCELAR   (libera a vaga)
    3 / remarcar           -> REMARCAR   (só registra o pedido, A-10/b)
"""
from __future__ import annotations

import unicodedata

_RESPOSTAS_RECONHECIDAS: dict[str, str] = {
    "1": "SIM",
    "sim": "SIM",
    "2": "CANCELAR",
    "nao": "CANCELAR",
    "cancelar": "CANCELAR",
    "3": "REMARCAR",
    "remarcar": "REMARCAR",
}

_PONTUACAO_DE_BORDA = " .!?,;:\t\n\r"


def _normalizar(texto: str) -> str:
    """Minúsculas, sem acento (NFKD + remoção de combining marks — mesmo idioma
    de `triage_engine._normalize`/`transcricao_service._normalize`, copiado aqui
    em vez de importado porque os dois são privados de seus módulos), sem
    pontuação nas bordas."""
    nfkd = unicodedata.normalize("NFKD", texto.lower())
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.strip(_PONTUACAO_DE_BORDA)


def reconhecer_resposta_confirmacao(texto: str) -> str | None:
    """Devolve `"SIM"`/`"CANCELAR"`/`"REMARCAR"` se `texto` for uma resposta curta
    reconhecida (igualdade exata após normalização); `None` se ambígua.

    `None` é o sinal para o chamador (`InboundMessageService`) seguir para a
    triagem normal, SEM consumir a pendência — o tutor pode responder de novo.
    """
    return _RESPOSTAS_RECONHECIDAS.get(_normalizar(texto))
