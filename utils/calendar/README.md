# Calendar Sync
Scans Markdown files for reminders, processes them as an .ics calendar file over a local HTTP server.

# Quick start
```sh
./start.sh /path/to/config.json
```

Config.json format example
```json
{
  "repo_uri": "https://github.com/my/notes",
  "ignore_paths_like": ["archive", "tmp", "private"]
}
```
* **repo_uri** (required)
  Git repository URL containing your Markdown notes. Supports HTTPS (`https://github.com/my/notes`) and SSH (`git@github.com:my/notes.git`).
  The repo is cloned to `utils/calendar/repo_storage/<repo_name>/` (for example, `utils/calendar/repo_storage/notes/`).

* **ignore_paths_like** (optional)
  List of substrings. If a file's relative path contains any of them, it will be skipped.
  Example:
  * `"archive"` → skips `notes/archive/todo.md`
  * `"tmp"` → skips `notes/tmp/file.md`

# Tests
Run from `utils/calendar/` (requires `../../setup.sh` for the TaskMaster venv):

```sh
./testrun.sh
```
