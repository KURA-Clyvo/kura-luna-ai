#!/usr/bin/env bash
# LU-01 — roda o detector de SQL-contra-schema (tests/contract, marker
# "oracle") e grava o resultado num log com EXIT= no final, conforme a
# regra 4 do ciclo (EXIT=$? dentro do log e total de testes ao lado).
#
# Exige ORACLE_DSN / ORACLE_USER / ORACLE_PASSWORD no ambiente -- sem eles
# os testes marcados "oracle" são pulados (skip), não falham silenciosamente
# (ver tests/contract/test_sql_contra_schema.py::_oracle_env_ou_skip).
#
# Uso (dentro do container kura_luna_ai, ou em qualquer ambiente com acesso
# ao Oracle do compose e com o worktree copiado):
#   ./scripts/check-sql-schema.sh [log_path]
#
# O caminho do log é opcional; default: check-sql-schema.log no cwd.
set -uo pipefail

LOG_PATH="${1:-check-sql-schema.log}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

{
    echo "== check-sql-schema.sh $(date -u +%Y-%m-%dT%H:%M:%SZ) =="
    echo "cwd: ${REPO_ROOT}"
    if [ -z "${ORACLE_DSN:-}" ] || [ -z "${ORACLE_USER:-}" ] || [ -z "${ORACLE_PASSWORD:-}" ]; then
        echo "AVISO: ORACLE_DSN/ORACLE_USER/ORACLE_PASSWORD ausentes -- os testes 'oracle' serão SKIPPED, não falharão."
    fi
    python -m pytest -m oracle tests/contract -v
    EXIT=$?
    echo "EXIT=${EXIT}"
    exit "${EXIT}"
} 2>&1 | tee "${LOG_PATH}"

# Propaga o exit code real do pytest (não o do tee).
exit "${PIPESTATUS[0]}"
