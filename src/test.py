import subprocess
import time
import unittest

from parameterized import parameterized  # pip3 install parameterized # ?
import main
import shutil
import os
import filecmp

python_script_path = os.path.dirname(__file__)

TASK_MASTER_APP_VAR = '$task_master'

def file_compare(file1, file2):
    with open(file1, 'rb') as f1, open(file2, 'rb') as f2:
        return f1.read() == f2.read()


def read_file(f: str) -> str:
    with open(f, 'r') as file:
        return file.read()


def get_test_cases() -> [str, str]:
    def dir_to_case(prefix: str, parent: str, dir_name: str) -> (str, str):
        name = prefix + dir_name
        path = parent + '/' + dir_name
        return name, path

    def scan_cases(src: str, prefix: str = '') -> []:
        r = []
        for root, dirs, files in os.walk(src):
            if root != src:
                continue
            r.extend(map(lambda d: dir_to_case(prefix, root, d), dirs))
        return r

    cases = []

    cases.extend(scan_cases(python_script_path + '/tests/cases'))
    cases.extend(scan_cases(python_script_path + '/tests/future', prefix='NOT SUPPORTED YET!'))
    # debug filtering
    # cases = list(filter(lambda c: c[0].endswith('raw_text_transformed_into_task'), cases))
    return cases


def test_time() -> int:
    return 3371810400


def prepare_artifact(src: str, dst: str):
    if os.path.exists(dst):
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        else:
            os.remove(dst)
    if os.path.exists(src):
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy(src, dst)
    pass


def run_task_master_at(test_dir: str):
    def read_exec_script(test_dir: str) -> str:
        script_path = test_dir + '/main.sh'
        if os.path.exists(script_path):
            return read_file(script_path)

        return f'{TASK_MASTER_APP_VAR} --archive ./archive.md ./main.md'

    script = read_exec_script(test_dir)
    cmd = f'cd {test_dir}\n' + script.replace(TASK_MASTER_APP_VAR, f'python3 {python_script_path}/main.py')
    print(subprocess.check_output(cmd, universal_newlines=True, shell=True))
    pass


class TestTaskMaster(unittest.TestCase):
    @parameterized.expand(get_test_cases())
    def test_cases(self, _: str, case_path: str):
        self._run_testcase(case_path)

    def setUp(self):
        super().setUp()
        os.environ[main.WAIT_EXECUTIONS_ENV] = 'true'

    def tearDown(self):
        super().tearDown()
        os.unsetenv(main.WAIT_EXECUTIONS_ENV)

    def _run_testcase(self, case_path: str):
        test_dir = case_path + '/actual'
        prepare_artifact(src=case_path + '/setup', dst=test_dir)
        test_executions = case_path + '/test_executions.log'
        prepare_artifact(src=case_path + '/executions.log',
                         dst=test_executions)
        run_task_master_at(test_dir)

        self.assertEqual(
            read_file(case_path + '/expected/main.md'),
            read_file(test_dir + '/main.md'),
        )

        self.compare_directories(expected_dir=case_path + '/expected',
                                 actual_dir=test_dir)

        if os.path.exists(case_path + '/executions.log'):
            self.assertEqual(
                read_file(case_path + '/executions.log'),
                read_file(test_executions),
            )

    def compare_directories(self, expected_dir, actual_dir, retry_scan: bool = False):
        comparison = filecmp.dircmp(expected_dir, actual_dir)
        diff = len(comparison.diff_files) + len(comparison.left_only) + len(comparison.right_only)
        if diff != 0 and retry_scan:
            print('files are not different, giving extra-time to sync!')
            time.sleep(1)
            comparison = filecmp.dircmp(expected_dir, actual_dir)
            diff = len(comparison.diff_files) + len(comparison.left_only) + len(comparison.right_only)

        if diff == 0:
            return

        def file_diff(file: str) -> str:
            actual = read_file(f'{actual_dir}/{file}').replace('\n', '\\n')
            expected = read_file(f'{expected_dir}/{file}').replace('\n', '\\n')
            return f'{file}\n   Want: "{expected}"\n    Got: "{actual}"'

        if len(comparison.diff_files) == 1:
            file = comparison.diff_files[0]
            self.assertEqual(
                read_file(f'{expected_dir}/{file}'),
                read_file(f'{actual_dir}/{file}'),
                f'File {actual_dir}/{file} is different'
            )

        diff_files = map(file_diff, comparison.diff_files)

        self.fail('\n'.join([
            "The directories are not equal. Differences:",
            "Different Files:", '\n'.join(diff_files),
            "Files only in the expected directory:", '\n'.join(comparison.left_only),
            "Files only in the actual directory:", '\n'.join(comparison.right_only),
        ]))


if __name__ == "__main__":
    unittest.main()
