#!/usr/bin/env bash
#
# Build the Nyora Python Sphinx docs into the nyora-site public tree so they
# are served at https://nyora.app/docs/python/.
#
# This writes ONLY into nyora-site/public/docs/python — it never deletes or
# touches any other content under nyora-site/public.
set -euo pipefail

REPO_ROOT="/Users/hasanraza/Desktop/kotatsu/Nyora/nyora-python"
DOCS_SRC="${REPO_ROOT}/docs"
OUT_DIR="/Users/hasanraza/Desktop/kotatsu/Nyora/nyora-site/public/docs/python"

mkdir -p "${OUT_DIR}"

sphinx-build -b html "${DOCS_SRC}" "${OUT_DIR}"

echo "Docs built into: ${OUT_DIR}"
