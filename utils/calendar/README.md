# Calendar Sync
Scans Markdown files for reminders, processes them as an .ics calendar file over a local HTTP server.

# Quick start
Requires Docker installed and running.

```sh
./start.sh /path/to/config.json
# ICS: http://localhost:37200/reminders.ics
./stop.sh
```

Logs: `docker logs -f task-master-calendar`

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

# SSH git access
For SSH `repo_uri` values, the container mounts your host `~/.ssh` read-only at `/root/.ssh`.
Ensure your private key and `known_hosts` entry for the git host are present on the host before starting.

# Tests
Run from `utils/calendar/` (requires Docker):

```sh
./testrun.sh
```

Pytest runs inside the calendar Docker image (overriding the default entrypoint). The HTML report is written to `utils/calendar/report.html` on the host for CI artifact upload.
