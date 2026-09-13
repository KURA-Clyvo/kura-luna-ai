"""Listas versionadas de sintomas para triagem de mensagens de tutores."""

TRIAGE_RULES_VERSION = "1.1"

# Cada chave é o nome da categoria; os valores são keywords em português (com ou sem acento).
# O TriageEngine normaliza tudo antes de comparar.

# ── LU-07 item 1: fronteira de palavra ──────────────────────────────────────
# O TriageEngine casa cada keyword por TOKEN inteiro (não substring), então
# "acidentalmente" não casa mais a keyword "acidente" (era o falso positivo
# de trauma na v1.0).

# ── LU-07 item 2: negação com janela curta ──────────────────────────────────
# Regra escrita aqui como DADO — o motor (triage_engine.py) só a aplica.
# Gatilhos em português informal (normalizado, sem acento); "parou de" tem
# 2 tokens e é casado como sequência contígua, igual às keywords.
# NEGATION_WINDOW_TOKENS = quantos tokens IMEDIATAMENTE ANTES do início da
# keyword casada são varridos em busca de um gatilho.
#
# Efeito: se um gatilho aparecer na janela, a categoria MEDIA/BAIXA daquela
# keyword é anulada (ex.: "não está vomitando mais" deixa de contar como
# MEDIA por vômito).
#
# ALTA é IMUNE a esta anulação — decisão deliberada (nunca afrouxar ALTA
# para ganhar acurácia, brief-comum §regras e KURA_BACKLOG_LUNA_AI §4).
# É por isso que "não respira"/"nao respira" (dispneia, abaixo) continuam
# ALTA mesmo contendo um gatilho de negação: a keyword JÁ É o estado grave
# (falta de ar), não um sintoma positivo sendo negado.
NEGATION_TRIGGERS: list[str] = ["nao", "nunca", "sem", "parou de"]
NEGATION_WINDOW_TOKENS = 3

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
