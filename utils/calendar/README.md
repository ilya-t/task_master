# Calendar Sync
Scans Markdown files for reminders, processes them as an .ics calendar file over a local HTTP server.

# Quick start
```sh
./start.sh /path/to/config.json
```

Config.json format example
```json
{
  "notes_dir": "/dir/to/your/notes",
  "ignore_paths_like": ["archive", "tmp", "private"]
}
```
* **notes_dir** (required)
  Path to directory containing your Markdown notes.

* **ignore_paths_like** (optional)
  List of substrings. If a file's relative path contains any of them, it will be skipped.
  Example:
  * `"archive"` → skips `notes/archive/todo.md`
  * `"tmp"` → skips `notes/tmp/file.md`
