#!/bin/zsh
set -euo pipefail

script_dir=${0:A:h}
project_root=${script_dir:h}
app_path="$project_root/build/OpenReader.app"
contents_path="$app_path/Contents"

if [[ "$app_path" != "$project_root/build/OpenReader.app" ]]; then
  print -u2 "Refusing unexpected app bundle path: $app_path"
  exit 1
fi

"$project_root/scripts/build_engine.sh"
swift build -c release --package-path "$project_root/apps/macos"

/bin/rm -rf "$app_path"
mkdir -p "$contents_path/MacOS" "$contents_path/Resources"
cp "$project_root/apps/macos/.build/release/OpenReader" "$contents_path/MacOS/OpenReader"
cp "$project_root/dist/openreader-engine" "$contents_path/Resources/openreader-engine"
cp "$project_root/apps/macos/Resources/Info.plist" "$contents_path/Info.plist"
chmod 755 "$contents_path/MacOS/OpenReader" "$contents_path/Resources/openreader-engine"

codesign --force --sign - --timestamp=none "$contents_path/Resources/openreader-engine"
codesign --force --deep --sign - --timestamp=none "$app_path"
codesign --verify --deep --strict "$app_path"

print "$app_path"
