import os
import shutil
import sys
import uuid
import time
from datetime import datetime
from typing import Callable

python_script_path = os.path.dirname(__file__)
LOG_FILE = python_script_path + '/operations.log'
DIVE_TEMPLATE_INTRO = 'dive-in:'
DIVE_TEMPLATE_SCRIPT_BODY = 'git checkout branch_name'
HISTORY_DIR = '/tmp/task_master_memories'


def current_timestamp() -> int:
    return int(time.time())


class TaskMaster:
    def __init__(self, config_file: str, timestamp_provider: Callable[[], int] = current_timestamp) -> None:
        super().__init__()
        self._timestamp_provider = timestamp_provider
        self._config_file = config_file
        with open(self._config_file, 'r') as file:
            self._lines = file.readlines()

    def _untitled_to_tasks(self) -> None:
        if self._lines[0].startswith('# '):
            return

        datetime_obj = datetime.fromtimestamp(self._timestamp_provider())
        current_time = datetime_obj.strftime('%d_%m_%Y_%H_%M')

        self._insert(0, '# [ ] ' + current_time)

    def _insert_setup_template_to_tasks(self):
        await_template = False
        for i, line in enumerate(self._lines):
            if line.startswith('# ['):
                await_template = True
                continue

            if await_template:
                if not line.startswith(DIVE_TEMPLATE_INTRO):
                    self._insert(i, '```')
                    self._insert(i, DIVE_TEMPLATE_SCRIPT_BODY)
                    self._insert(i, '```sh')
                    self._insert(i, DIVE_TEMPLATE_INTRO)
                await_template = False
        pass

    def execute(self):
        self._untitled_to_tasks()
        self._insert_setup_template_to_tasks()

        if self._changed:
            updated_content = ''.join(self._lines)
            self._make_defensive_copy()
            write_to(file_name=self._config_file, content=updated_content)

    def _insert(self, index: int, line):
        self._lines.insert(index, line+'\n')
        self._changed = True

    def _make_defensive_copy(self):
        dst = HISTORY_DIR + '/' + str(uuid.uuid4())
        os.makedirs(dst, exist_ok=True)
        shutil.copy(self._config_file, dst + '/' + os.path.basename(self._config_file))
        pass


def log(message: str) -> None:
    with open(LOG_FILE, mode='a') as log_file:
        print(message, file=log_file)


def write_to(file_name, content):
    text_file = open(file_name, "w")
    text_file.write(content)
    text_file.close()


def main(config_file: str):
    TaskMaster(config_file).execute()


if __name__ == "__main__":
    main(config_file=sys.argv[1])
