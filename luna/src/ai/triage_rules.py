"""Listas versionadas de sintomas para triagem de mensagens de tutores."""

TRIAGE_RULES_VERSION = "1.2"

# Cada chave é o nome da categoria; os valores são keywords em português (com ou sem acento).
# O TriageEngine normaliza tudo antes de comparar.

# ── LU-07 item 1: fronteira de palavra ──────────────────────────────────────
# O TriageEngine casa cada keyword por TOKEN inteiro (não substring), então
# "acidentalmente" não casa a keyword "acidente" — mas isso NUNCA foi um
# falso positivo real em v1.0 (motor por substring): "acidente" não é
# substring de "acidentalmente" (os 7 primeiros caracteres batem,
# "acident", o 8º diverge: "a" vs "e"), medido e confirmado em
# lu-07-report.md (achado da retomada da sessão 5) — o comentário anterior
# aqui ("era o falso positivo de trauma na v1.0") estava ERRADO (LU-07 fix
# wave 1, achado A8 da G2). A fronteira de palavra é reforçada de verdade
# pelas mordidas de "sanguessuga" (contém "sangue" como substring) e
# "afebril" (contém "febril" como substring) — ver TestMordidasNominais.

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

# ── LU-07 fix wave 1, item A2: a negação não atravessa oração ───────────────
# Achado da G2 (lu-07-revisao.md, Frente 3): a janela de 3 tokens ignorava
# limite de oração, então um gatilho de negação numa oração rebaixava uma
# categoria MEDIA/BAIXA legítima em OUTRA oração da mesma mensagem
# ("sem comer e vomitando", "sem febre. vomitando" ⇒ MEDIA virava BAIXA).
# Fix: a oração termina em pontuação forte ou em conjunção coordenativa —
# dados aqui, o motor (triage_engine.py) só aplica ao computar a janela.
# CLAUSE_BOUNDARY_CHARS são caracteres (já presentes no texto normalizado,
# que passa a preservar pontuação na tokenização em vez de descartá-la).
# CLAUSE_COORDINATING_CONJUNCTIONS são palavras (já sem acento, minúsculas,
# porque comparadas contra tokens normalizados).
CLAUSE_BOUNDARY_CHARS: str = ".,;!?\n"
CLAUSE_COORDINATING_CONJUNCTIONS: list[str] = ["e", "mas", "porem", "ou"]

# ── LU-07 fix wave 1, item 2: vocabulário ALTA por categoria clínica ────────
# Partindo de categorias reconhecidas de emergência veterinária (lu-07-fix-
# brief.md item 2), cada categoria abaixo ganhou sinônimos informais PT-BR e
# erros comuns de digitação. Fonte da LISTA DE CATEGORIAS (não dos números —
# nenhum número de validação clínica é alegado aqui): quadros de "sinais de
# emergência" amplamente publicados por hospitais/clínicas veterinárias e por
# centros de controle de intoxicação animal (ex.: material público de
# pronto-atendimento veterinário 24h e de centros de toxicologia animal sobre
# quando procurar atendimento imediato). Curadoria do time (implementador
# sonnet), NÃO validada por veterinário — mesma ressalva do corpus abaixo.
# Como `_keyword_detectado` normaliza a keyword em tempo de execução
# (`_normalize` remove acento), não é preciso duplicar forma acentuada e
# sem acento — mantém-se aqui só a forma sem acento por brevidade.
SINTOMAS_ALTA_URGENCIA: dict[str, list[str]] = {
    "convulsao": [
        "convulsão",
        "convulsao",
        "convulsionando",
        "convulsoes",
        "tremendo muito",
        "espasmo",
        "tremores continuos",
        "nao para de tremer",
    ],
    "inconsciencia": [
        "desmaiou",
        "perdeu a consciencia",
        "nao acorda",
        "nao responde",
        "caido sem reagir",
        "sem reagir",
        "inconsciente",
        "desacordado",
    ],
    "sangramento": [
        "sangrando",
        "sangue",
        "hemorragia",
        "sangramento",
        "ferida aberta",
        "sangramento que nao para",
        "nao para de sangrar",
        "jorrando sangue",
    ],
    "intoxicacao": [
        "envenenado",
        "envenenamento",
        "veneno",
        "intoxicado",
        "intoxicação",
        "comeu produto",
        "ingeriu produto",
        "rato veneno",
        "raticida",
        "chocolate",
        "uva",
        "passas",
        "xilitol",
        "remedio humano",
        "produto de limpeza",
        "pilha",
        "bateria",
        "engoliu objeto",
        "objeto estranho",
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
        "nao consegue respirar",
        "respirando de boca aberta",
        "ofegante parado",
        "lingua roxa",
        "lingua azulada",
        "lingua palida",
        "gengiva roxa",
        "gengiva azulada",
        "gengiva palida",
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
        "fratura exposta",
        "mordida de outro animal",
        "mordido por outro animal",
    ],
    "retencao_urinaria": [
        "sem fazer xixi",
        "nao consegue fazer xixi",
        "nao faz xixi",
        "fazendo forca sem sair",
        "nao urina",
    ],
    "parto_complicado": [
        "em trabalho de parto ha horas",
        "fazendo forca ha horas",
        "filhote preso",
        "nao consegue parir",
        "parto complicado",
    ],
    "picada_peconhenta": [
        "picada de cobra",
        "picada de escorpiao",
        "picado por sapo",
        "mordida de cobra",
        "picada de aranha",
    ],
    "abdome_distendido": [
        "barriga inchada e dura",
        "abdomen distendido",
        "barriga estufada",
        "tentando vomitar sem conseguir",
    ],
    "hipertermia": [
        "golpe de calor",
        "hipertermia",
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
