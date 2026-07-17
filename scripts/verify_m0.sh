#!/bin/zsh
set -euo pipefail

script_dir=${0:A:h}
project_root=${script_dir:h}
fixture_pdf=${1:-/Users/milanmuriithi/Downloads/personal/books/Elements of Style.pdf}
verification_root="$project_root/build/m0-verification"
handshake_path="$verification_root/engine-handshake.json"
engine_pid=""

if [[ ! -f "$fixture_pdf" || "${fixture_pdf:e:l}" != "pdf" ]]; then
  print -u2 "Expected a PDF fixture: $fixture_pdf"
  exit 1
fi

cleanup() {
  if [[ -n "$engine_pid" ]]; then kill "$engine_pid" 2>/dev/null || true; fi
  /bin/rm -f "$handshake_path"
}
trap cleanup EXIT

cd "$project_root"
mkdir -p "$verification_root"
uv sync --extra dev
uv run pytest
uv run openreader convert "$fixture_pdf" --output-dir "$verification_root" > "$verification_root/conversion-report.json"

fixture_name=${fixture_pdf:t:r}
epub_path="$verification_root/derivatives/$fixture_name.epub"
uv run openreader validate "$epub_path" > "$verification_root/validation-report.json"

"$project_root/scripts/package_macos.sh" > "$verification_root/package-path.txt"
codesign --verify --deep --strict "$project_root/build/OpenReader.app"

# Prove the distributable does not inherit Homebrew/Poppler from the development Mac.
PATH=/usr/bin:/bin "$project_root/build/OpenReader.app/Contents/Resources/openreader-engine" \
  convert "$fixture_pdf" --output-dir "$verification_root/self-contained" \
  > "$verification_root/self-contained-conversion-report.json"
PATH=/usr/bin:/bin "$project_root/build/OpenReader.app/Contents/Resources/openreader-engine" \
  validate "$verification_root/self-contained/derivatives/$fixture_name.epub" \
  > "$verification_root/self-contained-validation-report.json"

"$project_root/build/OpenReader.app/Contents/Resources/openreader-engine" \
  serve --port 0 --token m0-packaging-proof --handshake "$handshake_path" --data-root "$verification_root/runtime" &
engine_pid=$!

for _ in {1..50}; do
  [[ -f "$handshake_path" ]] && break
  sleep 0.1
done

if [[ ! -f "$handshake_path" ]]; then
  print -u2 "Packaged engine did not write its handshake"
  exit 1
fi

engine_port=$(sed -E 's/.*"port"[[:space:]]*:[[:space:]]*([0-9]+).*/\1/' "$handshake_path")
curl --fail --silent "http://127.0.0.1:$engine_port/health" > "$verification_root/engine-health.json"

print "Milestone 0 software verification passed"
print "Fixture: $fixture_pdf"
print "EPUB: $epub_path"
print "App: $project_root/build/OpenReader.app"
print "Self-contained engine: passed without Poppler on PATH"
