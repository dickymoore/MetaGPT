#!/usr/bin/env bash
# Run the fast lint passes expected by Codex CLI workflows.
set -euo pipefail
IFS=$'\n\t'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"

if [ ! -d "${VENV_DIR}" ]; then
  echo "error: missing virtual environment. Run scripts/codex/bootstrap.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"

ruff check "${ROOT_DIR}"
