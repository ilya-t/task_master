import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.request

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
CALENDAR_DIR = os.path.join(REPO_ROOT, 'utils', 'calendar')
TEST_TMP_ROOT = os.path.join(CALENDAR_DIR, '.test_tmp')
GIT_ENV = {
    **os.environ,
    'GIT_AUTHOR_NAME': 'test',
    'GIT_AUTHOR_EMAIL': 'test@example.com',
    'GIT_COMMITTER_NAME': 'test',
    'GIT_COMMITTER_EMAIL': 'test@example.com',
}


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


def _cleanup_calendar_service():
    subprocess.run(
        ['./stop.sh'],
        cwd=CALENDAR_DIR,
        capture_output=True,
        text=True,
    )

    for name in ['reminders.ics', 'service.log', 'service.pid']:
        path = os.path.join(CALENDAR_DIR, name)
        if os.path.exists(path):
            os.remove(path)

    shutil.rmtree(os.path.join(CALENDAR_DIR, 'repo_storage'), ignore_errors=True)


def _wait_for_ics(timeout_seconds: float = 120) -> str:
    ics_host = os.environ.get('ICS_HOST', 'localhost')
    ics_url = f'http://{ics_host}:37200/reminders.ics'
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(ics_url) as response:
                return response.read().decode()
        except Exception:
            time.sleep(0.5)
    raise TimeoutError(f'ICS file was not served at {ics_url}')


class TestCalendarRepoSync(unittest.TestCase):
    def setUp(self):
        os.makedirs(TEST_TMP_ROOT, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT)
        self.work_dir = self.tmp.name

        self.notes_repo = os.path.join(self.work_dir, 'notes_work')
        self.bare_repo = os.path.join(self.work_dir, 'notes.git')
        self.config_path = os.path.join(self.work_dir, 'config.json')

        _cleanup_calendar_service()
        _init_notes_repo(self.notes_repo)
        _run_git(['clone', '--bare', self.notes_repo, self.bare_repo], self.work_dir)

        bare_repo_in_container = '/app/utils/calendar/' + os.path.relpath(
            self.bare_repo, CALENDAR_DIR
        ).replace(os.sep, '/')

        with open(self.config_path, 'w') as f:
            json.dump({
                'repo_uri': 'file://' + bare_repo_in_container,
                'ignore_paths_like': [],
            }, f)

    def tearDown(self):
        _cleanup_calendar_service()
        self.tmp.cleanup()

    def test_bare_repo_clone_generates_ics_with_reminder(self):
        subprocess.run(
            ['./start.sh', self.config_path],
            cwd=CALENDAR_DIR,
            check=True,
        )

        ics_content = _wait_for_ics()

        self.assertIn('reminder checkpoint', ics_content)
        self.assertTrue(os.path.isdir(os.path.join(CALENDAR_DIR, 'repo_storage', 'notes')))
        self.assertTrue(os.path.isfile(
            os.path.join(CALENDAR_DIR, 'repo_storage', 'notes', 'reminders.md')
        ))


if __name__ == '__main__':
    unittest.main()
