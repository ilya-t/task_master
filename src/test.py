import unittest
import uuid

from parameterized import parameterized  # pip3 install parameterized # ?
import main
import shutil
import os

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
        # dirs = list(filter(lambda d: 'links' in d, dirs))
        return list(map(lambda d: (d, root+'/'+d), dirs))


def test_time() -> int:
    return 3371810400


class TestTaskMaster(unittest.TestCase):
    @parameterized.expand(get_test_cases())
    def test_cases(self, name: str, case_path: str):
        test_input = case_path + '/test_output.md'
        shutil.copy(src =case_path + '/actual_input.md',
                    dst =test_input)
        temporal_files = main.get_config_files(test_input)
        if os.path.exists(temporal_files):
            shutil.rmtree(temporal_files)
        test_archive = '/tmp/' + str(uuid.uuid4()) + '.md'
        main.TaskMaster(taskflow_file=test_input,
                        history_file=test_archive,
                        timestamp_provider=test_time).execute()

        self.assertEqual(
            read_file(case_path + '/expected_output.md'),
            read_file(test_input),
        )

        if os.path.exists(case_path + '/expected_archive.md'):
            self.assertEqual(
                read_file(case_path + '/expected_archive.md'),
                read_file(test_archive),
            )


if __name__ == "__main__":
    unittest.main()
