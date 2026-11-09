# Task Master Companion

Runs Task Master when a configured file is saved in VS Code, including autosaves.
Preserves cursors and selections when Task Master updates the file.

## Install

With Node.js 24+ and `code` on PATH, run from this directory:

```sh
./install_extension.sh
```
To build only, use `./build_extension.sh`;
the VSIX appears in `build_artifacts/`.

## Configure

Add a profile in **Settings → Task Master Companion → Edit in settings.json**:

```json
{
  "taskMasterCompanion.profiles": {
    "Work notes": {
      "executable": "~/workspace/task_master/run",
      "files": "notes/**/*.md",
      "params": {
        "archive": "./archive.md",
        "config": "~/workspace/task_master_config.json"
      },
      "verbose": true
    }
  }
}
```

`executable` and `files` (a path or glob) are required; the first matching profile
wins. Paths support `~/` and `${workspaceFolder}`. Relative paths use the file's
workspace folder, or its directory outside a workspace. Settings apply on the
next save. Available parameters have completion and descriptions in VS Code.

Logs appear in **Output → Task Master Companion**; `verbose` opens the panel on
each run. Saves during an active run are skipped. External file changes do not
trigger another run.

## Tests

```sh
npm ci && npm test
```

Tests use isolated editor and command substitutes; they do not launch VS Code.
