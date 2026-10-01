"""Templates de mensagem parametrizados para a Luna."""
from datetime import datetime


def confirmacao_d1(
    nm_tutor: str,
    nm_pet: str | None,
    dt_agendamento: datetime,
    ds_servico: str | None,
) -> str:
    """Template do lembrete de confirmação D-1 (REC-16, A-10).

    Texto livre (não é template aprovado da Meta/WhatsApp Business — mesmo
    padrão do `lembrete_vacina` abaixo, mesmo risco documentado no G0 item 10
    do backlog: fora da janela de 24h desde a última mensagem do tutor, o
    envio pode falhar com 63016. Risco operacional conhecido, não bloqueante).

    As 3 opções numéricas casam exatamente com
    `confirmacao_d1_reconhecedor.reconhecer_resposta_confirmacao` (A-10/a).
    `nm_clinica` não está disponível aqui — `ConfirmacaoPendenteItemDto` (REC-15)
    não carrega o nome da clínica, só o id (ver `dtos.ConfirmacaoPendenteItemDTO`)
    — por isso o texto não cita o nome da clínica.
    """
    hora = dt_agendamento.strftime("%H:%M")
    pet_trecho = f" do(a) {nm_pet}" if nm_pet else ""
    servico_trecho = f" ({ds_servico})" if ds_servico else ""

    return (
        f"Olá, {nm_tutor}! 🐾\n\n"
        f"Você tem um agendamento{pet_trecho} amanhã às {hora}{servico_trecho}.\n\n"
        "Por favor, responda com uma das opções:\n"
        "1 — Confirmar presença\n"
        "2 — Cancelar\n"
        "3 — Preciso remarcar\n\n"
        "Você também pode responder só com a palavra: sim, cancelar ou remarcar."
    )


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
