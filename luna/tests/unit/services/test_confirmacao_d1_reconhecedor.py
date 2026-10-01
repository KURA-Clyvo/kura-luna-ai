"""Testes do reconhecedor de resposta curta de confirmação D-1 (REC-16, A-10/a)."""
import pytest

from src.services.confirmacao_d1_reconhecedor import reconhecer_resposta_confirmacao


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("1", "SIM"),
        ("sim", "SIM"),
        ("Sim", "SIM"),
        ("SIM", "SIM"),
        (" sim ", "SIM"),
        ("sim.", "SIM"),
        ("2", "CANCELAR"),
        ("não", "CANCELAR"),
        ("nao", "CANCELAR"),
        ("Não", "CANCELAR"),
        ("cancelar", "CANCELAR"),
        ("Cancelar!", "CANCELAR"),
        ("3", "REMARCAR"),
        ("remarcar", "REMARCAR"),
        ("Remarcar", "REMARCAR"),
    ],
)
def test_reconhece_respostas_curtas_validas(texto: str, esperado: str) -> None:
    assert reconhecer_resposta_confirmacao(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "sim, mas ele está vomitando",
        "sim mas preciso remarcar",
        "não sei",
        "meu pet está passando mal",
        "",
        "   ",
        "1 2 3",
        "simm",
        "talvez",
        "oi",
    ],
)
def test_nao_reconhece_mensagens_ambiguas(texto: str) -> None:
    """A-10/a — nunca por substring/prefixo: a rede de segurança da Luna nunca
    pode ser contornada por uma resposta que comece com uma palavra
    reconhecida (o exemplo literal do backlog é 'sim, mas ele está vomitando')."""
    assert reconhecer_resposta_confirmacao(texto) is None
