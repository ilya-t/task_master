import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
CALENDAR_DIR = os.path.join(REPO_ROOT, 'utils', 'calendar')
SRC_DIR = os.path.join(CALENDAR_DIR, 'src')
TEST_TMP_ROOT = os.path.join(CALENDAR_DIR, '.test_tmp')
TASK_MASTER_DIR = os.environ.get('TASK_MASTER_DIR', '/app')
GIT_ENV = {
    **os.environ,
    'GIT_AUTHOR_NAME': 'test',
    'GIT_AUTHOR_EMAIL': 'test@example.com',
    'GIT_COMMITTER_NAME': 'test',
    'GIT_COMMITTER_EMAIL': 'test@example.com',
}

sys.path.insert(0, SRC_DIR)
import main as calendar_main  # noqa: E402


def _run_git(args, cwd: str):
    subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True, env=GIT_ENV)


def _init_notes_repo(repo_dir: str):
    os.makedirs(repo_dir, exist_ok=True)

    with open(os.path.join(repo_dir, 'reminders.md'), 'w') as f:
        f.write('- [!] 2026.06.06: reminder checkpoint\n')

    with open(os.path.join(repo_dir, 'notes.md'), 'w') as f:
        f.write('# Notes\n- [ ] plain task\n')

    with open(os.path.join(repo_dir, 'archive.md'), 'w') as f:
        f.write('')

    _run_git(['init'], repo_dir)
    _run_git(['add', '.'], repo_dir)
    _run_git(['commit', '-m', 'init notes'], repo_dir)


class TestUpdateNotesRepo(unittest.TestCase):
    def setUp(self):
        os.makedirs(TEST_TMP_ROOT, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT)
        self.work_dir = self.tmp.name
        self.notes_repo = os.path.join(self.work_dir, 'notes_work')
        self.bare_repo = os.path.join(self.work_dir, 'notes.git')
        self.clone_dir = os.path.join(self.work_dir, 'notes_clone')

        _init_notes_repo(self.notes_repo)
        _run_git(['clone', '--bare', self.notes_repo, self.bare_repo], self.work_dir)
        _run_git(['clone', self.bare_repo, self.clone_dir], self.work_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_update_notes_repo_discards_local_dirt_and_picks_up_remote(self):
        dirty_path = os.path.join(self.clone_dir, 'notes.md')
        with open(dirty_path, 'a') as f:
            f.write('\nlocal dirt\n')
        with open(os.path.join(self.clone_dir, 'untracked.md'), 'w') as f:
            f.write('should be cleaned\n')

        with open(os.path.join(self.notes_repo, 'reminders.md'), 'w') as f:
            f.write('- [!] 2026.06.07: updated remote reminder\n')
        _run_git(['add', 'reminders.md'], self.notes_repo)
        _run_git(['commit', '-m', 'remote update'], self.notes_repo)

        branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=self.clone_dir,
            text=True,
            env=GIT_ENV,
        ).strip()
        _run_git(['push', self.bare_repo, f'HEAD:{branch}'], self.notes_repo)

        calendar_main.update_notes_repo(self.clone_dir)

        with open(os.path.join(self.clone_dir, 'reminders.md')) as f:
            self.assertIn('updated remote reminder', f.read())
        with open(dirty_path) as f:
            self.assertNotIn('local dirt', f.read())
        self.assertFalse(os.path.exists(os.path.join(self.clone_dir, 'untracked.md')))


class TestCalendarRepoSync(unittest.TestCase):
    def setUp(self):
        os.makedirs(TEST_TMP_ROOT, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT)
        self.work_dir = self.tmp.name

        self.notes_repo = os.path.join(self.work_dir, 'notes_work')
        self.bare_repo = os.path.join(self.work_dir, 'notes.git')

        shutil.rmtree(os.path.join(CALENDAR_DIR, 'repo_storage'), ignore_errors=True)
        ics_path = os.path.join(CALENDAR_DIR, calendar_main.ICS_FILENAME)
        if os.path.exists(ics_path):
            os.remove(ics_path)

        _init_notes_repo(self.notes_repo)
        _run_git(['clone', '--bare', self.notes_repo, self.bare_repo], self.work_dir)

    def tearDown(self):
        self.tmp.cleanup()
        shutil.rmtree(os.path.join(CALENDAR_DIR, 'repo_storage'), ignore_errors=True)

    def test_bare_repo_clone_generates_ics_with_reminder(self):
        repo_uri = 'file://' + self.bare_repo
        ics_path = calendar_main.sync_reminders_once(
            task_master_dir=TASK_MASTER_DIR,
            repo_uri=repo_uri,
            ignore_paths_like=[],
        )

        with open(ics_path) as f:
            ics_content = f.read()

        self.assertIn('reminder checkpoint', ics_content)
        self.assertTrue(os.path.isdir(os.path.join(CALENDAR_DIR, 'repo_storage', 'notes')))


class TestGenerateIcs(unittest.TestCase):
    def setUp(self):
        self.ics_dir = tempfile.mkdtemp(dir=TEST_TMP_ROOT)
        self.original_path = calendar_main.PYTHON_SCRIPT_PATH
        calendar_main.PYTHON_SCRIPT_PATH = self.ics_dir
        calendar_main.ICS_FILENAME = 'test_reminders.ics'

    def tearDown(self):
        calendar_main.PYTHON_SCRIPT_PATH = self.original_path
        shutil.rmtree(self.ics_dir, ignore_errors=True)

    def _make_reminder(self, timestamp: int, title: str = 'test event') -> dict:
        return {
            f'file/{title}/{timestamp}': {
                'title': title,
                'summary': f'{title}\n\n=====================\nauto-generated event',
                'timestamp': timestamp,
                'duration_minutes': 30,
                'add_notification': True,
            }
        }

    def test_generate_ics_renders_timestamps_as_utc(self):
        """Timestamps (pre-shifted) are rendered as UTC in ICS output."""
        ts = 1721462400  # 2024-07-20T08:00:00Z
        reminders = self._make_reminder(ts)
        ics_path = calendar_main.generate_ics(reminders)

        with open(ics_path) as f:
            content = f.read()

        # DTSTART should be at 08:00:00Z (no additional shift)
        self.assertIn('DTSTART:20240720T080000Z', content)
        self.assertIn('DTEND:20240720T083000Z', content)

    def test_generate_ics_renders_pre_shifted_timestamp(self):
        """A pre-shifted timestamp (e.g. +60min) is rendered as-is in UTC."""
        ts = 1721462400 + 3600  # 2024-07-20T09:00:00Z (already shifted by +1h)
        reminders = self._make_reminder(ts)
        ics_path = calendar_main.generate_ics(reminders)

        with open(ics_path) as f:
            content = f.read()

        self.assertIn('DTSTART:20240720T090000Z', content)
        self.assertIn('DTEND:20240720T093000Z', content)

    def test_generate_ics_renders_all_events(self):
        """All events rendered correctly."""
        ts1 = 1721462400       # 2024-07-20T08:00:00Z
        ts2 = 1721466000       # 2024-07-20T09:00:00Z
        reminders = {}
        reminders.update(self._make_reminder(ts1, 'event one'))
        reminders.update(self._make_reminder(ts2, 'event two'))
        ics_path = calendar_main.generate_ics(reminders)

        with open(ics_path) as f:
            content = f.read()

        self.assertIn('DTSTART:20240720T080000Z', content)
        self.assertIn('DTSTART:20240720T090000Z', content)


class TestTaskMasterRemindersToInternalModel(unittest.TestCase):
    OFFSET_MIN = 180
    OFFSET_TZ = datetime.timezone(datetime.timedelta(minutes=OFFSET_MIN))
    NOW = datetime.datetime(2026, 8, 26, 9, 57, tzinfo=OFFSET_TZ)
    TODAY_END = 1787776199  # 2026-08-26 20:29:59 UTC == 23:29:59 UTC+3

    def _convert(self, reminders, offset_min=None, now=None):
        return calendar_main.task_master_reminders_to_internal_model(
            reminders_file='calendar.md',
            reminders_json={'reminders': reminders},
            offset_min=self.OFFSET_MIN if offset_min is None else offset_min,
            now=self.NOW if now is None else now,
        )

    def _event(self, results):
        self.assertEqual(len(results), 1)
        return next(iter(results.values()))

    def test_outdated_all_day_event_moves_to_today(self):
        """Past date-only reminders are shown at the end of today, with the original date in the title."""
        ts = int(datetime.datetime(2026, 8, 18, tzinfo=datetime.timezone.utc).timestamp())
        event = self._event(self._convert([
            {'title': 'coffee', 'timestamp': str(ts), 'exact_time': False, 'line': 1},
        ]))

        self.assertEqual(event['title'], '[2026.08.18] coffee')
        self.assertEqual(event['timestamp'], self.TODAY_END)
        self.assertFalse(event['add_notification'])

    def test_outdated_exact_time_event_moves_to_today(self):
        ts = int(datetime.datetime(2026, 8, 25, 10, 0, tzinfo=datetime.timezone.utc).timestamp())
        event = self._event(self._convert([
            {'title': 'workout', 'timestamp': str(ts), 'exact_time': True, 'line': 1},
        ]))

        self.assertEqual(event['title'], '[2026.08.25] workout')
        self.assertEqual(event['timestamp'], self.TODAY_END)
        self.assertFalse(event['add_notification'])

    def test_future_all_day_event_stays_on_its_own_day(self):
        ts = int(datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc).timestamp())
        event = self._event(self._convert([
            {'title': 'payday', 'timestamp': str(ts), 'exact_time': False, 'line': 1},
        ]))

        self.assertEqual(event['title'], 'payday')
        # 2026-09-01 23:29:59 UTC+3
        self.assertEqual(event['timestamp'], 1788294599)
        self.assertTrue(event['add_notification'])

    def test_future_exact_time_event_keeps_shifted_timestamp(self):
        ts = int(datetime.datetime(2026, 9, 1, 13, 0, tzinfo=datetime.timezone.utc).timestamp())
        event = self._event(self._convert([
            {'title': 'meeting', 'timestamp': str(ts), 'exact_time': True, 'line': 1},
        ]))

        self.assertEqual(event['title'], 'meeting')
        self.assertEqual(event['timestamp'], ts - self.OFFSET_MIN * 60)
        self.assertTrue(event['add_notification'])


class TestGenerateReminders(unittest.TestCase):
    def setUp(self):
        os.makedirs(TEST_TMP_ROOT, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT)
        self.work_dir = self.tmp.name

        self.notes_repo = os.path.join(self.work_dir, 'notes_work')
        self.bare_repo = os.path.join(self.work_dir, 'notes.git')

        # Clean up any leftover ICS and repo_storage from previous runs
        ics_path = os.path.join(CALENDAR_DIR, calendar_main.ICS_FILENAME)
        if os.path.exists(ics_path):
            os.remove(ics_path)
        shutil.rmtree(os.path.join(CALENDAR_DIR, 'repo_storage'), ignore_errors=True)

        self._init_notes_repo_with_reminder()
        self._write_config()

    def _log(self, msg: str):
        """Write a line to stderr so it appears in test reports regardless of capture settings."""
        sys.stderr.write(msg + '\n')
        sys.stderr.flush()

    def tearDown(self):
        # Debug: dump repo state and generated ICS before cleanup
        if hasattr(self, 'notes_repo') and os.path.isdir(self.notes_repo):
            for root, _dirs, files in os.walk(self.notes_repo):
                for f in files:
                    if f.endswith('.md'):
                        path = os.path.join(root, f)
                        with open(path) as fh:
                            self._log(f'--- {os.path.relpath(path, self.notes_repo)} ---')
                            self._log(fh.read().rstrip())

        ics_path = os.path.join(CALENDAR_DIR, 'reminders.ics')
        if os.path.exists(ics_path):
            self._log(f'--- reminders.ics ---')
            with open(ics_path) as fh:
                self._log(fh.read().rstrip())

        self.tmp.cleanup()
        if os.path.exists(ics_path):
            os.remove(ics_path)
        shutil.rmtree(os.path.join(CALENDAR_DIR, 'repo_storage'), ignore_errors=True)

    def _init_notes_repo_with_reminder(self):
        """Create a notes repo with a single README.md containing a reminder and a bare clone as local remote."""
        os.makedirs(self.notes_repo, exist_ok=True)
        content = (
            '# Notes\n'
            '- [!] 2036.06.06 13:00: test reminder from subprocess\n'
            '- [!] 2036.07.07: no specific date reminder\n'
            '- [!] 2020.01.01: overdue all-day reminder'
        )
        with open(os.path.join(self.notes_repo, 'README.md'), 'w') as f:
            f.write(content)
        _run_git(['init'], self.notes_repo)
        _run_git(['add', '.'], self.notes_repo)
        _run_git(['commit', '-m', 'init notes'], self.notes_repo)
        _run_git(['clone', '--bare', self.notes_repo, self.bare_repo], self.work_dir)

    def _write_config(self, config_override: dict = None):
        """Write config.json for the subprocess. Merge ``config_override`` into defaults."""
        config = {
            'repo_uri': 'file://' + self.bare_repo,
            'ignore_paths_like': [],
        }
        if config_override:
            config.update(config_override)
        self.config_path = os.path.join(self.work_dir, 'config.json')
        with open(self.config_path, 'w') as f:
            json.dump(config, f)

    def run_calendar_app(self) -> tuple:
        """Run main.py as a subprocess with --no-daemon. Returns (result, ics_path)."""
        result = subprocess.run(
            [
                sys.executable, 'main.py',
                '--no-daemon',
                TASK_MASTER_DIR,
                '37200',
                '--config', self.config_path,
            ],
            cwd=SRC_DIR,
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, 'TASK_MASTER_DIR': TASK_MASTER_DIR},
        )
        ics_path = os.path.join(CALENDAR_DIR, 'reminders.ics')
        self.assertTrue(
            os.path.exists(ics_path),
            f'ICS file not found at {ics_path}\nstdout: {result.stdout}\nstderr: {result.stderr}',
        )
        with open(ics_path) as f:
            ics_content = f.read()
        return ics_content

    def test_smoke(self):
        ics_content = self.run_calendar_app()

        self.assertIn('test reminder from subprocess', ics_content)
        self.assertIn('BEGIN:VCALENDAR', ics_content)
        self.assertIn('END:VCALENDAR', ics_content)
        self.assertIn('BEGIN:VEVENT', ics_content)
        self.assertIn('END:VEVENT', ics_content)
        # README.md contains 2036.06.06 13:00
        self.assertIn('DTSTAMP:20360606T130000Z', ics_content)
        self.assertIn('DTSTART:20360606T130000Z', ics_content)

        # README.md contains 2036.07.07 with shift to day end
        self.assertIn('DTSTAMP:20360707T232959Z', ics_content)
        self.assertIn('DTSTART:20360707T232959Z', ics_content)
        self.assertIn('DTEND:20360707T235959Z', ics_content)

    def test_timezone_offset(self):
        self._write_config(config_override={'timezone_offset_min': 60})
        ics_content = self.run_calendar_app()

        # README.md contains 2026.06.06 12:00

        self.assertIn('test reminder from subprocess', ics_content)
        self.assertIn('BEGIN:VCALENDAR', ics_content)
        self.assertIn('END:VCALENDAR', ics_content)
        self.assertIn('BEGIN:VEVENT', ics_content)
        self.assertIn('END:VEVENT', ics_content)
        # README.md contains 2036.06.06 13:00 we shift UTC timestamp by 60 minutes back
        # so user at GMT+1 would see 2036.06.06 13:00 cause his calendar will add 60 minutes back.
        self.assertIn('DTSTAMP:20360606T120000Z', ics_content)
        self.assertIn('DTSTART:20360606T120000Z', ics_content)

        # README.md contains 2036.07.07 we shift UTC timestamp by 60 minutes back
        # so user at GMT+1 would see 2036.06.06 13:00 cause his calendar will add 60 minutes back.
        self.assertIn('DTSTAMP:20360707T222959Z', ics_content)
        self.assertIn('DTSTART:20360707T222959Z', ics_content)

    def test_outdated_all_day_event_is_placed_today(self):
        ics_content = self.run_calendar_app()

        self.assertIn('[2020.01.01] overdue all-day reminder', ics_content)
        today = datetime.datetime.now(datetime.timezone.utc)
        self.assertIn(today.strftime('DTSTART:%Y%m%dT232959Z'), ics_content)
        self.assertIn(today.strftime('DTEND:%Y%m%dT235959Z'), ics_content)


if __name__ == '__main__':
    unittest.main()
