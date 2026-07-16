import time
import datetime
import json
import os.path
import shlex
import subprocess
import sys
import threading
import functools
from typing import List, Optional, Any, Union
from http.server import HTTPServer, SimpleHTTPRequestHandler
import datetime
import argparse
import re

GENERATED_DESC = 'auto-generated event'
DEFAULT_DURATION_MINUTES = 30
PYTHON_SCRIPT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ICS_FILENAME="reminders.ics"
REPO_STORAGE_DIR = os.path.join(PYTHON_SCRIPT_PATH, 'repo_storage')


def prettify_title(raw: str) -> str:
    # Matches [title](url) and replaces it with the captured 'title'
    processed = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', raw)
    processed = processed.replace('`', '')
    return processed

def task_master_reminders_to_internal_model(reminders_file: str, reminders_json: {}) -> {}:
    reminders = reminders_json['reminders']
    now = datetime.datetime.now()
    filename = os.path.splitext(os.path.basename(reminders_file))[0]
    
    today_start = datetime.datetime(now.year, now.month, now.day)
    
    local_time = datetime.datetime.now().astimezone()

    start_of_day = int(today_start.timestamp())
    end_of_day = int(datetime.datetime(now.year, now.month, now.day, 23, 59, 59).timestamp())
    # shifting time by default duration would place event right to end of day and not pass to second day
    end_of_day_timestamp = end_of_day - (DEFAULT_DURATION_MINUTES * 60)

    results = {}
    for r in reminders:
        title = prettify_title(r['title'])
        timestamp = int(r['timestamp'])
        event_time = datetime.datetime.fromtimestamp(timestamp)
        is_outdated = event_time < today_start

        if is_outdated:
            original_date_str = event_time.strftime("%Y.%m.%d")
            timestamp = end_of_day_timestamp
            title = f'[{original_date_str}] {title}'

        if not r['exact_time'] and (start_of_day <= timestamp <= end_of_day):
            timestamp = end_of_day_timestamp

        uid = f'{filename}/{title}/{str(timestamp)}'
        actual_summary = '' if title == r['title'] else r['title']

        results[uid] = {
            'title': title,
            'summary':  f'{actual_summary}\n\n=====================\n{GENERATED_DESC}\nTech Data\nuid: {uid}\nfilename: {filename}', 
            'timestamp': timestamp, 
            'duration_minutes': DEFAULT_DURATION_MINUTES, 
            'add_notification': not is_outdated,
        }

    if 'errors' in reminders_json:
        errors = map(lambda it: it['title'], reminders_json['errors'])
        uid = f'{filename}/_errors_/{str(end_of_day_timestamp)}'
        error_desc = '\n - '.join(errors)
        results[uid] = {
            'title': f'{filename}: ERRORS!',
            'summary':  f'Error Lines:\n - {error_desc}\n\n=====================\n{GENERATED_DESC}\nuid: {uid}\nfilename: {filename}', 
            'timestamp': end_of_day_timestamp, 
            'duration_minutes': DEFAULT_DURATION_MINUTES, 
            'add_notification': not is_outdated,
        }

    return results


def update_reminders_at_google_calendar(app, reminders: {}):
    up_to_date_reminders = set()
    def maybe_delete(event) -> bool:
        desc = event.get('description')
        if not desc or not GENERATED_DESC in desc:
            return False

        for uid in reminders:
            if uid in desc:
                up_to_date_reminders.add(uid)
                return False
        
        return True
            
    app.delete_event_by_filter(maybe_delete)

    print('Up-to-date_reminders: ', len(up_to_date_reminders))

    for uid in up_to_date_reminders:
        reminders.pop(uid)
    print(f'Will add {len(reminders.keys())} reminders to calendar!')

    for key in reminders:
        r = reminders[key]
        title = r['title']
        print(f'Adding event for: {title}')

        app.add_event(
          title=r['title'],
          summary=r['summary'],
          timestamp=r['timestamp'],
          duration_minutes=r['duration_minutes'],
          add_notification=r['add_notification'],
        )


def format_ics_text(text):
    """
    Escapes special characters and applies line folding for iCalendar TEXT values.
    """
    # 1. Escape special characters (\ must be first)
    escaped = (text.replace('\\', '\\\\')
                   .replace(';', '\\;')
                   .replace(',', '\\,')
                   .replace('\n', '\\n'))

    # 2. Line Folding (limit to 75 octets)
    # RFC 5545 requires lines to be folded with CRLF + Space (or Tab)
    line_limit = 75
    folded = []
    current = ""

    for ch in escaped:
        candidate = current + ch

        if len(candidate.encode('utf-8')) > line_limit:
            folded.append(current)
            current = ch
        else:
            current = candidate

    folded.append(current)

    # Fold using CRLF + SPACE
    return '\r\n '.join(folded)

def generate_ics(reminders: dict):
    """
    Generates an .ics calendar file from reminders and optionally serves it.
    """
    import datetime
    import os
    from http.server import HTTPServer, SimpleHTTPRequestHandler
    import threading

    output_file = os.path.join(PYTHON_SCRIPT_PATH, ICS_FILENAME)

    def format_dt(ts: int) -> str:
        dt = datetime.datetime.utcfromtimestamp(ts)
        return dt.strftime("%Y%m%dT%H%M%S") + 'Z' # to mark that we're passing UTC

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//TaskMaster//Reminders Agenda//EN"
    ]

    for uid, r in reminders.items():
        start_ts = r["timestamp"]
        duration = r["duration_minutes"]

        end_ts = start_ts + duration * 60

        dtstart = format_dt(start_ts)
        dtend = format_dt(end_ts)
        dtstamp = format_dt(start_ts)

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"SUMMARY:{r['title']}",
            f"DESCRIPTION:{format_ics_text(r['summary'])}",
            "END:VEVENT"
        ])

    lines.append("END:VCALENDAR")

    with open(output_file, "w") as f:
        f.write("\n".join(lines))

    print(f"ICS file generated at: {output_file}")


def capture_output(cmd: str, ignore_errors=False) -> Union[str, None]:
    try:
        return subprocess.check_output(
            cmd, 
            universal_newlines=True, 
            shell=True, 
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as e:
        print(f'Command "{cmd}" failed with error:')
        print(e.output)
        if ignore_errors:
            return None
        raise e


def repo_name_from_uri(uri: str) -> str:
    uri = uri.rstrip('/')
    if uri.endswith('.git'):
        uri = uri[:-4]
    if ':' in uri and '@' in uri.split(':', 1)[0]:
        return uri.split(':', 1)[-1].split('/')[-1]
    return uri.split('/')[-1]


def ensure_repo_cloned(repo_uri: str) -> str:
    repo_name = repo_name_from_uri(repo_uri)
    local_path = os.path.join(REPO_STORAGE_DIR, repo_name)
    if not os.path.isdir(os.path.join(local_path, '.git')):
        os.makedirs(REPO_STORAGE_DIR, exist_ok=True)
        capture_output(f'git clone {shlex.quote(repo_uri)} {shlex.quote(local_path)}')
    return local_path


def update_notes_repo(notes_dir: str):
    """Fetch and hard-reset to upstream. Local clone is a disposable read-only mirror."""
    quoted = shlex.quote(notes_dir)
    capture_output(f'cd {quoted} && git fetch --prune origin')
    upstream = capture_output(
        f'cd {quoted} && git rev-parse --abbrev-ref --symbolic-full-name @{{u}}'
    ).strip()
    capture_output(f'cd {quoted} && git reset --hard {shlex.quote(upstream)}')
    capture_output(f'cd {quoted} && git clean -fd')


def sync_reminders_once(task_master_dir: str, repo_uri: str, ignore_paths_like: list) -> str:
    notes_dir = ensure_repo_cloned(repo_uri)
    print('Updating your notes!')
    update_notes_repo(notes_dir)
    print('Generating reminders!')
    reminders = generate_reminders(task_master_dir, notes_dir, ignore_paths_like)
    generate_ics(reminders)
    return os.path.join(PYTHON_SCRIPT_PATH, ICS_FILENAME)


def generate_reminders(task_master_dir: str, notes_dir: str, ignore_paths_like: list) -> {}:
    results = {}
    for root, dir, files in os.walk(notes_dir):
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, notes_dir)

            if any(pattern in rel_path for pattern in ignore_paths_like):
                print(f"Skipped (ignored): {rel_path}")
                continue

            if (f.endswith('.md')):
                # print(f'Processing: {full_path}')
                reminders_json: str = capture_output(task_master_dir + f'/run \'{full_path}\' --reminders')
                reminders = task_master_reminders_to_internal_model(reminders_file = f, reminders_json = json.loads(reminders_json))
                results.update(reminders)
            # else:
                # print(f'Skipped: {full_path}')
    return results


def sync(task_master_dir: str, repo_uri: str, port: int, ignore_paths_like: list):
    def update_reminders():
        sync_reminders_once(task_master_dir, repo_uri, ignore_paths_like)

    def update_reminders_loop():
        while True:
            time.sleep(3600) # 1h
            try:
                update_reminders()
            except Exception as e:
                print(f'Reminders update failed (will retry next hour): {e}')

    def serve():
        print(f'Serving local iCal server at: http://localhost:{port}/{ICS_FILENAME}')
        handler = functools.partial(SimpleHTTPRequestHandler, directory=PYTHON_SCRIPT_PATH) # TODO: serve single file
        server = HTTPServer(('0.0.0.0', port), handler)
        server.allow_reuse_address = True
        server.serve_forever()

    print('Initial reminders preparation')
    update_reminders()
    thread = threading.Thread(target=update_reminders_loop, daemon=True)
    thread.start()
    serve()


def main():
    parser = argparse.ArgumentParser(description="Sync reminders and serve ICS")
    parser.add_argument("task_master_dir")
    parser.add_argument("port", type=int)
    parser.add_argument(
        "--config",
        required=True,
        help="Path to JSON config file containing repo_uri and ignore_paths_like"
    )

    args = parser.parse_args()

    with open(args.config, "r") as f:
        config = json.load(f)

    repo_uri = config["repo_uri"]
    ignore_paths_like = config.get("ignore_paths_like", [])

    sync(
        task_master_dir=args.task_master_dir,
        repo_uri=repo_uri,
        port=args.port,
        ignore_paths_like=ignore_paths_like,
    )


if __name__ == '__main__':
    main()