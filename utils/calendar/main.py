import time
import datetime
import json
import os.path
import subprocess
import sys
import threading
import functools
from typing import List, Optional, Any, Union
from http.server import HTTPServer, SimpleHTTPRequestHandler
import datetime
import argparse

GENERATED_DESC = 'auto-generated event'
DEFAULT_DURATION_MINUTES = 30
PYTHON_SCRIPT_PATH = os.path.dirname(__file__)
ICS_FILENAME="reminders.ics"


def task_master_reminders_to_internal_model(reminders_file: str, reminders_json: {}) -> {}:
    reminders = reminders_json['reminders']
    now = datetime.datetime.now()
    filename = os.path.splitext(os.path.basename(reminders_file))[0]
    
    today_start = datetime.datetime(now.year, now.month, now.day)
    
    local_time = datetime.datetime.now().astimezone()

    end_of_day = int(datetime.datetime(now.year, now.month, now.day, 23, 59, 59).timestamp())
    # shifting time by default duration would place event right to end of day and not pass to second day
    end_of_day_timestamp = end_of_day - (DEFAULT_DURATION_MINUTES * 60)

    prefix = f'{filename}: '

    results = {}
    for r in reminders:
        title = r['title']
        timestamp = int(r['timestamp'])
        event_time = datetime.datetime.fromtimestamp(timestamp)
        is_outdated = event_time < today_start

        if is_outdated:
            original_date_str = event_time.strftime("%Y.%m.%d")
            timestamp = end_of_day_timestamp
            title = f'[{original_date_str}] {title}'

        if not r['exact_time']:
            timestamp = end_of_day_timestamp

        uid = f'{filename}/{title}/{str(timestamp)}'

        results[uid] = {
            'title': prefix + title,
            'summary':  f'{GENERATED_DESC}\nuid: {uid}', 
            'timestamp': timestamp, 
            'duration_minutes': DEFAULT_DURATION_MINUTES, 
            'add_notification': not is_outdated,
        }

    if 'errors' in reminders_json:
        errors = map(lambda it: it['title'], reminders_json['errors'])
        uid = f'{filename}/_errors_/{str(end_of_day_timestamp)}'
        error_desc = '\n - '.join(errors)
        results[uid] = {
            'title': prefix + 'ERRORS!',
            'summary':  f'{GENERATED_DESC}\nuid: {uid}\nError Lines:\n - {error_desc}', 
            'timestamp': timestamp, 
            'duration_minutes': DEFAULT_DURATION_MINUTES, 
            'add_notification': not is_outdated,
        }

    return results


def update_reminders_at_google_calendar(app, reminders: {}):
    up_to_date_reminders = set()
    def maybe_delete(event) -> bool:
        desc = event.get('description')
        if not desc or not desc.startswith(GENERATED_DESC):
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
            f"DESCRIPTION:{r['summary']}",
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


def sync(task_master_dir: str, notes_dir: str, port: int, ignore_paths_like: list):
    def update_reminders():
        print('Updating your notes!')
        capture_output(f'cd {notes_dir} && git pull --rebase') # TODO: let user decide how to update
        print('Generating reminders!')
        reminders: {} = generate_reminders(task_master_dir, notes_dir, ignore_paths_like)
        generate_ics(reminders)

    def update_reminders_loop():
        while True:
            time.sleep(3600) # 1h
            update_reminders()

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
        help="Path to JSON config file containing notes_dir and ignore_paths_like"
    )

    args = parser.parse_args()

    with open(args.config, "r") as f:
        config = json.load(f)

    notes_dir = config["notes_dir"]
    ignore_paths_like = config.get("ignore_paths_like", [])

    sync(
        task_master_dir=args.task_master_dir,
        notes_dir=notes_dir,
        port=args.port,
        ignore_paths_like=ignore_paths_like,
    )


if __name__ == '__main__':
    main()