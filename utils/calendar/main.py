import time
import datetime
import json
import os.path
import subprocess
import sys
import threading
from typing import List, Optional, Any, Union
from http.server import HTTPServer, SimpleHTTPRequestHandler
from datetime import datetime

GENERATED_DESC = 'auto-generated event'
DEFAULT_DURATION_MINUTES = 30
PYTHON_SCRIPT_PATH = os.path.dirname(__file__)
ICS_FILENAME="reminders.ics"


def to_reminders(reminders_file: str, reminders: []) -> {}:
    now = datetime.datetime.now()
    filename = os.path.splitext(os.path.basename(reminders_file))[0]
    
    today_start = datetime.datetime(now.year, now.month, now.day)
    
    local_time = datetime.now().astimezone()
    offset_minutes = int(local_time.utcoffset().total_seconds() / 60)

    end_of_day = int(datetime.datetime(now.year, now.month, now.day, 23, 59, 59).timestamp())
    # shifting to time zone would place event at the end of current day locally
    # shifting time by default duration would place event right to end of day and not pass to second day
    outdated_timestamp = end_of_day - (offset_minutes * 60) - (DEFAULT_DURATION_MINUTES * 60)

    prefix = f'{filename}: '

    results = {}
    for r in reminders:
        title = r['title']
        timestamp = int(r['timestamp'])
        event_time = datetime.datetime.fromtimestamp(timestamp)
        is_outdated = event_time < today_start

        if is_outdated:
            original_date_str = event_time.strftime("%Y.%m.%d")
            timestamp = outdated_timestamp
            title = f'[{original_date_str}] {title}'

        uid = f'{filename}/{r['title']}/{str(timestamp)}'

        results[uid] = {
            'title': prefix + title,
            'summary':  f'{GENERATED_DESC}\nuid: {uid}', 
            'timestamp': timestamp, 
            'duration_minutes': DEFAULT_DURATION_MINUTES, 
            'tz_offset_minutes': offset_minutes,
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
        print(f'Adding event for: {r['title']}')

        app.add_event(
          title=r['title'],
          summary=r['summary'],
          timestamp=r['timestamp'],
          duration_minutes=r['duration_minutes'],
          tz_offset_minutes=r['tz_offset_minutes'],
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

    def format_dt(ts: int, tz_offset_minutes: int) -> str:
        tz = datetime.timezone(datetime.timedelta(minutes=tz_offset_minutes))
        dt = datetime.datetime.fromtimestamp(ts, tz)
        return dt.strftime("%Y%m%dT%H%M%S")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//TaskMaster//Reminders Agenda//EN"
    ]

    for uid, r in reminders.items():
        start_ts = r["timestamp"]
        duration = r["duration_minutes"]
        tz_offset = r["tz_offset_minutes"]

        end_ts = start_ts + duration * 60

        dtstart = format_dt(start_ts, tz_offset)
        dtend = format_dt(end_ts, tz_offset)
        dtstamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

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


def generate_reminders(task_master_dir: str, notes_dir: str) -> {}:
    results = {}
    for root, dir, files in os.walk(notes_dir):
        for f in files:
            full_path = f'{root}/{f}'
            if (f.endswith('.md')):
                # print(f'Processing: {full_path}')
                reminders_json: str = capture_output(task_master_dir + f'/run \'{full_path}\' --reminders')
                reminders = to_reminders(reminders_file = f, reminders = json.loads(reminders_json))
                results.update(reminders)
            # else:
                # print(f'Skipped: {full_path}')
    return results


def sync(task_master_dir: str, notes_dir: str, port: int):
    def update_reminders():
        while True:
            print('Generating reminders!')
            reminders: {} = generate_reminders(task_master_dir, notes_dir)
            generate_ics(reminders)
            time.sleep(3600) # 1h

    def serve():
        print(f'Serving local iCal server at: http://localhost:{port}/{ICS_FILENAME}')
        server = HTTPServer(('localhost', port), SimpleHTTPRequestHandler)
        server.serve_forever()

    thread = threading.Thread(target=update_reminders, daemon=True)
    thread.start()
    serve()


def main():
    sync(
        task_master_dir = sys.argv[1],
        notes_dir = sys.argv[2],
        port = int(sys.argv[3]),
    )


if __name__ == '__main__':
    main()
