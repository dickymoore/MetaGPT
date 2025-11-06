#!/usr/bin/env bash
# Bootstrap script used by the Codex CLI to provision a working Python environment.
set -euo pipefail
IFS=$'\n\t'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "error: unable to locate \"${PYTHON_BIN}\". Install Python 3.9-3.11 and retry." >&2
  exit 1
fi

if [ ! -d "${VENV_DIR}" ]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip setuptools
python -m pip install -e "${ROOT_DIR}[test]"
python -m pip install ruff

# Node dependencies (optional for browser automation). Only install if pnpm is available.
if [ "${SKIP_PNPM:-0}" != "1" ] && command -v pnpm >/dev/null 2>&1; then
  (cd "${ROOT_DIR}" && pnpm install)
fi
