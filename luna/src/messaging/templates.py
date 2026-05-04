"""Templates de mensagem parametrizados para a Luna."""


def lembrete_vacina(
    nm_tutor: str,
    nm_pet: str,
    nm_vacina: str,
    dias_restantes: int,
    nm_clinica: str,
) -> str:
    """Template de lembrete de vacina próxima do vencimento."""
    if dias_restantes == 0:
        prazo = "hoje"
    elif dias_restantes == 1:
        prazo = "amanhã"
    else:
        prazo = f"em {dias_restantes} dias"

    return (
        f"Olá, {nm_tutor}! 🐾\n\n"
        f"A vacina *{nm_vacina}* do(a) *{nm_pet}* vence {prazo}.\n\n"
        f"Agende o reforço com a {nm_clinica} para manter a proteção em dia.\n\n"
        f"Qualquer dúvida, estamos aqui! — Equipe {nm_clinica}"
    )


def sugestao_cuidados_raca(
    nm_tutor: str,
    nm_pet: str,
    nm_raca: str,
    ds_predisposicao: str,
) -> str:
    """Template de sugestão de cuidados baseada em predisposições da raça."""
    return (
        f"Olá, {nm_tutor}! 🐶\n\n"
        f"Identificamos que *{nm_pet}* é da raça *{nm_raca}*.\n\n"
        f"Raças desta linhagem têm predisposição a: {ds_predisposicao}.\n\n"
        f"Recomendamos uma avaliação preventiva com seu veterinário. "
        f"A detecção precoce faz toda a diferença! 🏥"
    )
