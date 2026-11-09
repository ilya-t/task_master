#!/bin/bash
set -euo pipefail

extension_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$extension_directory"
npm ci
npm test
mkdir -p build_artifacts
npm run package

printf 'Extension packaged: %s/build_artifacts/task-master-companion.vsix\n' "$extension_directory"
printf 'Install: code --install-extension "%s/build_artifacts/task-master-companion.vsix" --force\n' "$extension_directory"
