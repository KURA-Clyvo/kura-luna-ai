"""Detector de SQL da Luna contra o schema Oracle real (LU-01).

A7 e N1 (ver g0-diagnostico.md) sao a mesma classe de defeito: SQL escrito
contra um schema imaginado, "provado" so com cursor simulado (MagicMock).
Regra v7 do ciclo: a lista de SQL a verificar NAO pode ser escrita a mao -
tem que ser DERIVADA do codigo, ou o detector fica cego para SQL novo.

Este modulo:
  1. Descobre, via pkgutil, todo modulo em ``src.db.repositories`` e coleta
     toda constante de modulo cujo nome comece com ``_SQL`` e seja ``str``.
     Falha (fora do marker ``oracle`` -- roda sempre) se a descoberta achar 0,
     que e o controle contra um detector cego por import quebrado.
  2. Para cada SQL coletado, um teste parametrizado (`@pytest.mark.oracle`)
     roda ``cursor.parse(sql)`` contra o Oracle real -- parse valida a
     existencia de colunas/tabelas e a sintaxe SEM executar DML (INSERT/
     UPDATE nunca gravam uma linha por causa deste teste).
  3. Para SELECTs, tenta adicionalmente encapsular em
     ``SELECT * FROM (<sql>) WHERE 1=0`` e executar com binds neutros -- mas
     esse passo e best-effort e nao derruba o teste sozinho: um bind
     incompativel (ex. NUMBER vs texto neutro) nao e um defeito de schema,
     e o `cursor.parse` ja verificado acima e quem prova a coluna/tabela.
     Ver "O que NAO foi verificado" no lu-01-report.md.

Sem ``ORACLE_DSN``/``ORACLE_USER``/``ORACLE_PASSWORD`` no ambiente, os testes
marcados ``oracle`` sao pulados (skip) com motivo explicito -- nunca dao
falso-verde por engolir a ausencia de conexao.
"""
from __future__ import annotations

import importlib
import os
import pkgutil
import re
from dataclasses import dataclass

import oracledb
import pytest

import src.db.repositories as repositories_pkg


@dataclass(frozen=True)
class SqlConstante:
    """Uma constante ``_SQL*`` coletada de um modulo de repositorio."""

    modulo: str  # ex.: "notificacao_repo"
    nome: str  # ex.: "_SQL_INSERT"
    sql: str

    @property
    def id(self) -> str:
        return f"{self.modulo}.{self.nome}"


def _descobrir_sql_constantes() -> list[SqlConstante]:
    """Importa todo modulo de ``src/db/repositories/`` e coleta ``_SQL*`` str.

    Derivado do codigo (regra v7): nenhum nome de modulo ou de constante e
    listado a mao aqui. Um repositorio novo, ou uma constante `_SQL_*` nova
    dentro de um repositorio existente, entra na lista sozinha.
    """
    encontrados: list[SqlConstante] = []
    for modinfo in pkgutil.iter_modules(repositories_pkg.__path__):
        modulo = importlib.import_module(f"{repositories_pkg.__name__}.{modinfo.name}")
        for nome, valor in vars(modulo).items():
            if nome.startswith("_SQL") and isinstance(valor, str):
                encontrados.append(SqlConstante(modulo=modinfo.name, nome=nome, sql=valor))
    # Ordem estavel (por modulo, depois por nome) -- parametrizacao deterministica.
    encontrados.sort(key=lambda c: (c.modulo, c.nome))
    return encontrados


_SQL_CONSTANTES = _descobrir_sql_constantes()


def test_descoberta_encontra_pelo_menos_um_sql() -> None:
    """Controle contra detector cego: a descoberta tem que achar > 0 SQL.

    Roda SEMPRE (sem marker ``oracle``) -- nao depende de Oracle, so de
    import. Se isto falhar com 0, ninguem esta sendo verificado e os testes
    parametrizados abaixo colapsam silenciosamente para uma lista vazia
    (pytest nao falha por parametrize([]) por padrao -- por isso este teste
    dedicado existe).
    """
    assert len(_SQL_CONSTANTES) > 0, (
        "Descoberta de _SQL* em src/db/repositories/ achou 0 constantes -- "
        "detector cego. Verifique se os modulos importam sem erro."
    )

    por_arquivo: dict[str, int] = {}
    for c in _SQL_CONSTANTES:
        por_arquivo[c.modulo] = por_arquivo.get(c.modulo, 0) + 1

    print(f"\n[LU-01] descoberta: {len(_SQL_CONSTANTES)} constantes _SQL* em "
          f"{len(por_arquivo)} modulo(s):")
    for modulo, qtd in sorted(por_arquivo.items()):
        print(f"[LU-01]   {modulo}: {qtd}")
    for c in _SQL_CONSTANTES:
        print(f"[LU-01]   - {c.id}")


def _oracle_env_ou_skip() -> tuple[str, str, str]:
    dsn = os.environ.get("ORACLE_DSN")
    user = os.environ.get("ORACLE_USER")
    password = os.environ.get("ORACLE_PASSWORD")
    if not dsn or not user or not password:
        pytest.skip(
            "ORACLE_DSN/ORACLE_USER/ORACLE_PASSWORD ausentes do ambiente -- "
            "teste de contrato contra Oracle real pulado (nao e um defeito "
            "de SQL, e ausencia de conexao)."
        )
    return dsn, user, password


@pytest.fixture(scope="module")
def oracle_cursor():
    """Cursor Oracle real. Skip explicito (nunca falso-verde) sem env."""
    dsn, user, password = _oracle_env_ou_skip()
    conn = oracledb.connect(dsn=dsn, user=user, password=password)
    cursor = conn.cursor()
    try:
        yield cursor
    finally:
        cursor.close()
        conn.close()


def _is_select(sql: str) -> bool:
    return sql.strip().upper().startswith("SELECT")


def _bind_names(sql: str) -> list[str]:
    # nomes de bind Oracle: ":nome" (evita capturar "::" -- nao ha aqui, mas
    # deixa explicito o que o regex cobre: RETURNING ... INTO :out_id tambem
    # e um bind e entra na lista).
    return sorted(set(re.findall(r":(\w+)", sql)))


@pytest.mark.oracle
@pytest.mark.parametrize(
    "constante",
    _SQL_CONSTANTES,
    ids=[c.id for c in _SQL_CONSTANTES],
)
def test_sql_faz_parse_contra_schema_real(constante: SqlConstante, oracle_cursor) -> None:
    """``cursor.parse`` de cada SQL descoberto contra o Oracle real do compose.

    oracledb faz parse (valida sintaxe + existencia de tabela/coluna) sem
    executar DML -- um INSERT/UPDATE aqui nunca grava uma linha. E o mesmo
    metodo que a sonda `probe_sql.py` do G0 ja provou contra este Oracle.

    Reproduz nominalmente A7 (vacina_repo._SQL) e N1 (os 5 SQLs do
    notificacao_repo) na branch em que este teste foi escrito ainda sem os
    fixes de LU-02/LU-03 -- ver lu-01-report.md para o log literal.
    """
    try:
        oracle_cursor.parse(constante.sql)
    except oracledb.Error as exc:
        pytest.fail(f"{constante.id}: parse falhou contra o schema real -- {exc}")


_SELECTS = [c for c in _SQL_CONSTANTES if _is_select(c.sql)]


@pytest.mark.oracle
@pytest.mark.parametrize("constante", _SELECTS, ids=[c.id for c in _SELECTS])
def test_select_executa_com_where_1_equals_0(constante: SqlConstante, oracle_cursor) -> None:
    """Best-effort: encapsula o SELECT e executa com ``WHERE 1=0``.

    Nao e a prova principal (essa e o `parse` acima) -- e um reforco para
    pegar erro de tipo/expressao que o parser as vezes deixa passar. Uma
    falha por INCOMPATIBILIDADE DE TIPO DE BIND (ORA-01722 e afins, pois os
    binds aqui sao neutros/None, nao os valores reais de producao) nao e
    evidencia de schema errado, entao e reportada como skip com motivo, nao
    como falha do teste -- conforme o brief autoriza ("se complicar, so
    parse -- declare").
    """
    binds = {nome: None for nome in _bind_names(constante.sql)}
    sql_envelope = f"SELECT * FROM ({constante.sql.rstrip(';')}) WHERE 1=0"
    try:
        oracle_cursor.execute(sql_envelope, binds)
    except oracledb.Error as exc:
        codigo = str(exc)
        if "ORA-00904" in codigo or "ORA-00942" in codigo or "ORA-01867" in codigo:
            # Coluna/tabela inexistente ou literal de intervalo invalido --
            # ESTE e o tipo de erro que o LU-01 existe para pegar.
            pytest.fail(f"{constante.id}: WHERE 1=0 acusou schema -- {exc}")
        pytest.skip(
            f"{constante.id}: WHERE 1=0 nao executou por motivo nao-relacionado "
            f"a schema (provavel bind neutro incompativel) -- {exc}"
        )
