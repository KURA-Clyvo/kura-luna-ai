"""Dataclass espelhando a tabela NOTIFICACAO."""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Notificacao:
    """Representa um registro na tabela NOTIFICACAO."""

    id_tutor: int
    ds_canal: str
    ds_tipo: str
    ds_titulo: str
    ds_mensagem: str
    dt_agendada: datetime
    st_status: str
    id_notificacao: int | None = None
    id_pet: int | None = None
    id_evento: int | None = None
    dt_enviada: datetime | None = None
    ds_erro_envio: str | None = None
