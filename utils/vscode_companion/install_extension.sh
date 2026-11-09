#!/bin/bash
set -euo pipefail

extension_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
vsix_path="$extension_directory/build_artifacts/task-master-companion.vsix"
if ! command -v code >/dev/null 2>&1; then
    printf 'VS Code CLI not found. Add code to PATH.\n' >&2
    exit 1
fi

"$extension_directory/build_extension.sh"
code --install-extension "$vsix_path" --force
printf '\nTo activate the update, run Developer: Reload Window in VS Code.\n'
