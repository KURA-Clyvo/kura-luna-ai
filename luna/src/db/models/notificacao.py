"""Dataclass espelhando as colunas de NOTIFICACAO usadas pela Luna (V9 + V21/LU-02)."""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Notificacao:
    """Representa um registro a inserir/atualizar em NOTIFICACAO.

    ``id_clinica`` é obrigatório porque a coluna é ``NOT NULL`` desde a V9 —
    esquecê-la faz o INSERT falhar com ``ORA-01400`` (achado N1/LU-01).
    """

    id_clinica: int
    id_tutor: int
    id_pet: int
    ds_titulo: str
    ds_mensagem: str
    ds_canal: str
    ds_tipo: str
    st_envio: str
    id_notificacao: int | None = None
    dt_envio: datetime | None = None
    ds_erro_envio: str | None = None
