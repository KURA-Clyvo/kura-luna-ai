"""Listas versionadas de sintomas para triagem de mensagens de tutores."""

TRIAGE_RULES_VERSION = "1.0"

# Cada chave é o nome da categoria; os valores são keywords em português (com ou sem acento).
# O TriageEngine normaliza tudo antes de comparar.

SINTOMAS_ALTA_URGENCIA: dict[str, list[str]] = {
    "convulsao": [
        "convulsão",
        "convulsao",
        "convulsionando",
        "convulsoes",
        "tremendo muito",
        "espasmo",
        "desmaiou",
        "perdeu a consciencia",
        "perdeu a consciência",
    ],
    "sangramento": [
        "sangrando",
        "sangue",
        "hemorragia",
        "sangramento",
        "ferida aberta",
    ],
    "envenenamento": [
        "envenenado",
        "envenenamento",
        "veneno",
        "intoxicado",
        "intoxicação",
        "comeu produto",
        "ingeriu produto",
        "rato veneno",
        "raticida",
    ],
    "dispneia": [
        "dificuldade respirar",
        "não respira",
        "nao respira",
        "respiração difícil",
        "respiracao dificil",
        "ofegante",
        "sufocando",
        "engasgou",
    ],
    "trauma": [
        "atropelado",
        "atropelamento",
        "caiu de altura",
        "bateu a cabeça",
        "bateu a cabeca",
        "fratura",
        "osso quebrado",
        "acidente",
    ],
}

SINTOMAS_MEDIA_URGENCIA: dict[str, list[str]] = {
    "vomito": [
        "vomitando",
        "vomitou",
        "vômito",
        "vomito",
        "enjoo",
        "enjôo",
        "nausea",
        "náusea",
    ],
    "diarreia": [
        "diarreia",
        "diarréia",
        "fezes moles",
        "cocô mole",
        "coco mole",
        "intestino solto",
    ],
    "letargia": [
        "letárgico",
        "letargico",
        "sem apetite",
        "não quer comer",
        "nao quer comer",
        "muito quieto",
        "parado demais",
        "fraco",
        "cansado demais",
    ],
    "febre": [
        "febre",
        "temperatura alta",
        "quente demais",
        "febril",
    ],
}

SINTOMAS_BAIXA_URGENCIA: dict[str, list[str]] = {
    "duvida": [
        "dúvida",
        "duvida",
        "pergunta",
        "queria saber",
        "como faço",
        "informação",
        "informacao",
    ],
    "comportamento": [
        "comportamento estranho",
        "latindo muito",
        "miando muito",
        "roendo",
        "arranhando",
        "pulga",
        "carrapato",
    ],
}
