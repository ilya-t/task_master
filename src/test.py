import unittest

from parameterized import parameterized  # pip3 install parameterized # ?
import main
import shutil
import os
import filecmp

python_script_path = os.path.dirname(__file__)


def file_compare(file1, file2):
    with open(file1, 'rb') as f1, open(file2, 'rb') as f2:
        return f1.read() == f2.read()


def read_file(f: str) -> str:
    with open(f, 'r') as file:
        return file.read()


def get_test_cases() -> [str]:
    for root, dirs, files in os.walk(python_script_path+'/tests/cases'):
        # debug filtering
        # dirs = list(filter(lambda d: 'deletion_of_unused_local_files' == d, dirs))
        return list(map(lambda d: (d, root+'/'+d), dirs))


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


class TestTaskMaster(unittest.TestCase):
    @parameterized.expand(get_test_cases())
    def test_cases(self, name: str, case_path: str):
        test_output = case_path + '/test_output.md'
        test_files = main.get_config_files(test_output)
        test_archive = case_path + '/test_archive.md'

        prepare_artifact(src=case_path + '/actual_input.md',
                         dst=test_output)

        prepare_artifact(src=case_path + '/actual_input.files',
                         dst=test_files)

        prepare_artifact(src=case_path + '/actual_archive.md',
                         dst=test_archive)

        main.TaskMaster(taskflow_file=test_output,
                        history_file=test_archive,
                        timestamp_provider=test_time).execute()

        self.assertEqual(
            read_file(case_path + '/expected_output.md'),
            read_file(test_output),
        )

        if os.path.exists(case_path + '/expected_archive.md'):
            self.assertEqual(
                read_file(case_path + '/expected_archive.md'),
                read_file(test_archive),
                msg='Archives are different!'
            )

        if os.path.exists(case_path + '/expected_output.files'):
            self.compare_directories(
                case_path + '/expected_output.files',
                case_path + '/test_output.files',
            )

    def compare_directories(self, expected_dir, actual_dir):
        comparison = filecmp.dircmp(expected_dir, actual_dir)

        diff = len(comparison.diff_files) + len(comparison.left_only) + len(comparison.right_only)
        self.assertEqual(0, diff, '\n'.join([
            "The directories are not equal. Differences:",
            "Common Files:", '\n'.join(comparison.common_files),
            "Different Files:", '\n'.join(comparison.diff_files),
            "Files only in the expected directory:", '\n'.join(comparison.left_only),
            "Files only in the actual directory:", '\n'.join(comparison.right_only),
        ]))


if __name__ == "__main__":
    unittest.main()
