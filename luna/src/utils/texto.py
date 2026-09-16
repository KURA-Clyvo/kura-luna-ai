"""Utilitários de texto — truncamento seguro por bytes UTF-8.

Mesmo raciocínio do ``TruncarPorBytesUtf8`` do ``backend-clinica-dotnet``
(FIX_6): colunas Oracle ``VARCHAR2(n)`` são dimensionadas em BYTES, não em
caracteres. Truncar por índice de caractere (``texto[:n]``) pode gerar uma
string cujo tamanho em bytes ainda excede ``n`` quando há caractere
multibyte (acentuação, emoji) perto do limite — e truncar por índice de byte
sem cuidado pode partir um caractere multibyte no meio, gerando bytes
inválidos.
"""


def truncar_por_bytes_utf8(texto: str, max_bytes: int) -> str:
    """Trunca ``texto`` para no máximo ``max_bytes`` bytes UTF-8.

    Nunca parte um caractere multibyte: o último caractere que não couber
    inteiro no limite de bytes é descartado por completo (``errors="ignore"``
    na decodificação do sufixo cortado).
    """
    codificado = texto.encode("utf-8")
    if len(codificado) <= max_bytes:
        return texto
    cortado = codificado[:max_bytes]
    return cortado.decode("utf-8", errors="ignore")
