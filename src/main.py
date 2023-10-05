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
        self._changed = False
        self._timestamp_provider = timestamp_provider
        self._config_file = config_file
        with open(self._config_file, 'r') as file:
            self._lines: [str] = file.readlines()

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

    def _inject_extra_checkboxes(self):
        def count_incomplete(s: int, e: int) -> int:
            result = 0
            for l in self._lines[s:e + 1]:
                if not l.lstrip().startswith('- [x]'):
                    result += 1
                pass
            return result

        check_groups = []
        check_group = {}
        for i, line in enumerate(self._lines):
            if line.lstrip().startswith('- [') and 'start' not in check_group:
                check_group['start'] = i

            end_of_file = i == len(self._lines) - 1
            if 'start' in check_group and (not line.lstrip().startswith('- [') or end_of_file):
                if end_of_file:
                    check_group['end'] = i
                else:
                    check_group['end'] = i - 1

                check_groups.append(check_group)
                check_group = {}

        nested_groups = []
        for group in check_groups:
            start: int = group['start']
            subgroup = None
            group_lines = self._lines[start: group['end'] + 1]
            for i, line in enumerate(group_lines):
                if subgroup:
                    if line.startswith('- [') or i == len(group_lines) - 1:
                        subgroup['end'] = start + i - 1
                        nested_groups.append(subgroup)
                        subgroup = None
                else:
                    if not line.startswith('- ['):
                        # -1 includes parent so its complete status would also count.
                        subgroup = {'start': start + i - 1}

        check_groups.extend(nested_groups)
        sorted_groups = sorted(check_groups, key=lambda x: x['end'], reverse=True)

        for group in sorted_groups:
            start: int = group['start']
            end: int = group['end']
            if self._lines[end].strip() == '- [ ]':
                continue
            incomplete_tasks = count_incomplete(start, end)
            if incomplete_tasks > 0:
                line = self._lines[end]
                padding = line[:line.index('- [')]
                self._insert(end + 1, padding + '- [ ] ')

    def execute(self):
        self._untitled_to_tasks()
        self._insert_setup_template_to_tasks()
        self._inject_extra_checkboxes()

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
