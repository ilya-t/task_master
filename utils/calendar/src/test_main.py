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


if __name__ == '__main__':
    unittest.main()
