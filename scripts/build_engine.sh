#!/bin/zsh
set -euo pipefail

script_dir=${0:A:h}
project_root=${script_dir:h}

cd "$project_root"
uv sync --extra dev
uv run pyinstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name openreader-engine \
  --paths "$project_root/engine" \
  --collect-submodules uvicorn \
  --collect-submodules multipart \
  "$project_root/scripts/engine_entry.py"

"$project_root/dist/openreader-engine" --help >/dev/null
codesign --force --sign - --timestamp=none "$project_root/dist/openreader-engine"
codesign --verify --strict "$project_root/dist/openreader-engine"
