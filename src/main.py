import os
import re
import pyperclip
import shutil
import sys
import time
import uuid
from datetime import datetime
from typing import Callable

from PIL import ImageGrab  # pip install pillow==10.0.0

python_script_path = os.path.dirname(__file__)
LOG_FILE = python_script_path + '/operations.log'
DIVE_TEMPLATE_INTRO = 'dive-in:'
DIVE_TEMPLATE_SCRIPT_BODY = 'git checkout branch_name'
HISTORY_DIR = '/tmp/task_master_memories'
UNUSED_FILES = '# [ ] unused local files'


def get_config_files(config_file: str) -> str:
    name, _ = os.path.splitext(os.path.basename(config_file))
    return os.path.dirname(config_file) + '/' + name + '.files'


def get_padding(line: str) -> str:
    if len(line) == 0:
        return ''
    return line[:line.index('- [')]


def current_timestamp() -> int:
    return int(time.time())


def write_lines(dst: str, lines: [str]) -> None:
    parent = os.path.dirname(dst)
    os.makedirs(parent, exist_ok=True)
    updated_content = ''.join(map(lambda l: l + '\n', lines))
    text_file = open(dst, "w")
    text_file.write(updated_content)
    text_file.close()


def read_lines(src) -> [str]:
    def remove_trailing_newline(l: str) -> str:
        if l.endswith('\n'):
            return l[:-1]
        return l

    with open(src, 'r') as file:
        return list(map(remove_trailing_newline, file.readlines()))


def trim_trailing_empty_lines(lines: [str]):
    while len(lines) > 0 and lines[-1].strip() == '':
        lines.pop(-1)


def paste_image(file_path: str) -> bool:
    image = ImageGrab.grabclipboard()

    if image is not None:
        parent = os.path.dirname(file_path)
        os.makedirs(parent, exist_ok=True)
        image.save(file_path, 'PNG')
        return True

    return False


def is_checkbox(line: str) -> bool:
    l = line.lstrip()
    return len(l) >= 4 and l.startswith('- [') and l[4] == ']'


def checkbox_status_index(line) -> int:
    if not is_checkbox(line):
        return -1

    return len(get_padding(line)) + 3


class TaskMaster:
    def __init__(self,
                 taskflow_file: str,
                 history_file: str,
                 timestamp_provider: Callable[[], int] = current_timestamp) -> None:
        super().__init__()
        self._changed = False
        self._timestamp_provider = timestamp_provider
        self._config_file = taskflow_file
        self._history_file = history_file
        self._lines: [str] = read_lines(self._config_file)

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
                if line.strip() == '':
                    self._remove(start=i, end=i)
                    self._insert_all(i, [
                        DIVE_TEMPLATE_INTRO,
                        '```sh',
                        DIVE_TEMPLATE_SCRIPT_BODY,
                        '```',
                    ])
                await_template = False
        pass

    def _inject_extra_checkboxes(self):
        def group_completed_or_has_trailing_checkbox(start: int, end: int) -> bool:
            start_line = self._lines[start]
            group_padding = start_line[:start_line.index('- [')]
            all_completed = True
            if len(group_padding) > 0 and start > 0:
                nested_group_parent_completed = self._lines[start - 1].strip().startswith('- [x]')
                if not nested_group_parent_completed:
                    all_completed = False

            for gl in self._lines[start:end + 1]:
                if gl.startswith(group_padding + '- [ ]'):
                    all_completed = False

            return all_completed or self._lines[end].rstrip() == group_padding + '- [ ]'

        def try_insert_checkboxes(groups: []) -> None:
            for group in sort_by_end(groups):
                start: int = group['start']
                end: int = group['end']
                if not group_completed_or_has_trailing_checkbox(start, end):
                    line = self._lines[start]
                    padding = line[:line.index('- [')]
                    self._insert(end + 1, padding + '- [ ] ')

                children = group.get('children', None)
                if children:
                    try_insert_checkboxes(children)

        check_groups = as_nested_dict(self._parse_check_groups())
        try_insert_checkboxes(check_groups)

    def _parse_tasks(self) -> {}:
        check_groups = self._parse_check_groups()
        tasks = []
        task = {}
        for i, line in enumerate(self._lines):
            if line.startswith('# [') and 'start' not in task:
                task['start'] = i
                continue

            end_of_file = i == len(self._lines) - 1
            if 'start' in task and (line.startswith('# [') or end_of_file):
                if end_of_file:
                    task['end'] = i
                else:
                    task['end'] = i - 1
                task['check_groups'] = list(
                    filter(lambda g: g['start'] >= task['start'] and g['start'] <= task['end'], check_groups))

                tasks.append(task)
                task = {
                    'start': i
                }

        return tasks

    def _move_checkboxes_comments_into_tasks(self):
        def add_space_groups():
            for t in tasks:
                space_groups = []
                check_groups = sorted(t['check_groups'], key=lambda x: x['start'])
                check_group_end = None
                for i, cg in enumerate(check_groups):
                    cg_start = cg['start']
                    cg_end = cg['end']

                    if not check_group_end:
                        check_group_end = cg_end
                        continue

                    if cg_start - check_group_end > 1:
                        space_groups.append({
                            'start': check_group_end + 1,
                            'end': cg_start - 1,
                        })

                    if cg_end > check_group_end:
                        check_group_end = cg_end

                if check_group_end:
                    space_groups.append({
                        'start': check_group_end + 1,
                        'end': t['end'],
                    })

                t['check_groups'] = check_groups
                t['space_groups'] = space_groups
            pass

        def get_task_title(str: str) -> str:
            return str[str.index(']') + 1:].strip()

        tasks = self._parse_tasks()
        add_space_groups()
        insertions = []

        for t in sort_by_end(tasks):
            space_groups = sort_by_end(t['space_groups'])

            if len(space_groups) == 0:
                continue

            for s in space_groups:
                subtask_index = s['start'] - 1
                group_padding = get_padding(self._lines[subtask_index])
                lines = list(map(lambda s: s.removeprefix(group_padding), self._lines[s['start']:s['end'] + 1]))
                if len(''.join(lines).strip()) == 0:
                    continue

                if len(get_task_title(self._lines[subtask_index]).strip()) == 0:
                    continue

                insertions.append({
                    'task_line': self._lines[t['start']],
                    'subtask_line': self._lines[subtask_index],
                    'lines': lines,
                    'start': s['start'],
                    'end': s['end'],
                })
                self._lines[subtask_index] = self._lines[subtask_index].replace('- [ ]', '- [^]')
                self._remove(s['start'], s['end'])

        for insertion in sort_by_end(insertions):
            task_start: int = self._lines.index(insertion['task_line'])
            new_task_lines: [str] = insertion['lines']
            task = get_task_title(insertion['task_line'])
            subtask = get_task_title(insertion['subtask_line'])
            new_task_lines.insert(0, '# [ ] ' + task + ' -> ' + subtask)
            if new_task_lines[-1].strip() != '':
                new_task_lines.append('')
            self._insert_all(index=task_start, lines=new_task_lines)
        pass

    def _remove(self, start: int, end: int):
        new_lines = []
        new_lines.extend(self._lines[:start])
        new_lines.extend(self._lines[end + 1:])
        self._lines = new_lines
        self._changed = True

    def execute(self):
        self._untitled_to_tasks()
        self._insert_setup_template_to_tasks()
        self._move_checkboxes_comments_into_tasks()
        self._inject_extra_checkboxes()
        self._update_checkboxes_status()
        self._move_completed_tasks()
        self._process_links()
        self._trim_lines()

        if self._changed:
            self._make_defensive_copy()
            write_lines(dst=self._config_file, lines=self._lines)

    def _insert(self, index: int, line: str):
        self._lines.insert(index, line)
        self._changed = True

    def _insert_all(self, index: int, lines: [str]):
        for l in reversed(lines):
            self._lines.insert(index, l)
        self._changed = True

    def _make_defensive_copy(self):
        dst = HISTORY_DIR + '/' + str(uuid.uuid4())
        os.makedirs(dst, exist_ok=True)
        shutil.copy(self._config_file, dst + '/' + os.path.basename(self._config_file))
        pass

    def _parse_check_groups(self) -> []:
        def parse_nested_groups(start: int, end: int) -> None:
            g = None
            root_padding = len(get_padding(self._lines[start]))
            group_padding = len(get_padding(self._lines[start]))
            for i, line in enumerate(self._lines[start:end + 1]):
                new_padding = len(get_padding(line))
                if new_padding > group_padding:
                    if not g:
                        g = {'start': start + i}
                        group_padding = new_padding
                    parse_nested_groups(start + i, end)
                if new_padding < group_padding:
                    if g:
                        g['end'] = start + i - 1
                        nested_groups.append(g)
                        group_padding = root_padding
                    g = None
                if new_padding < root_padding:
                    return

        check_groups = []
        check_group = {}
        for i, line in enumerate(self._lines):
            if is_checkbox(line) and 'start' not in check_group:
                check_group['start'] = i

            end_of_file = i == len(self._lines) - 1
            if 'start' in check_group and (not is_checkbox(line) or end_of_file):
                if end_of_file:
                    check_group['end'] = i
                else:
                    check_group['end'] = i - 1

                check_groups.append(check_group)
                check_group = {}

        nested_groups = []
        for group in check_groups:
            start: int = group['start']
            parse_nested_groups(start, group['end'])

        check_groups.extend(nested_groups)
        return check_groups

    def _move_completed_tasks(self):
        if self._history_file == '':
            return

        tasks = self._parse_tasks()
        completed: [str] = []

        for t in sort_by_end(tasks):
            start = t['start']
            end = t['end']
            task_title = self._lines[start]
            if not task_title.startswith('# [x] '):
                continue
            raw_task_lines = self._lines[start:end + 1]
            trim_trailing_empty_lines(raw_task_lines)
            raw_task_lines.append('')
            for l in reversed(raw_task_lines):
                completed.insert(0, l)
            completed[0] = completed[0].replace('# [x] ', '# ')

            self._remove(start, end)

        trim_trailing_empty_lines(completed)

        if len(completed) == 0:
            return

        completed.append('')

        parent = os.path.dirname(self._history_file)
        os.makedirs(parent, exist_ok=True)
        lines = []
        if os.path.exists(self._history_file):
            lines = read_lines(self._history_file)

        for l in reversed(completed):
            lines.insert(0, l)

        write_lines(self._history_file, lines)

    def _gather_links(self, markdown_text: str) -> []:
        patterns = [
            r'(?:!)?\[([^\]]+)\]\(([^\]]+)\)',
            r'(?:!)?\[([^\]]+)\]\(\)',
            r'(?:!)?\[\]\(\)',
            r'(?:!)?\[\]\(([^\]]+)\)',
        ]
        hyperlink_matches = []
        for p in patterns:
            matches = list(re.finditer(p, markdown_text))
            hyperlink_matches.extend(matches)

        results = []

        for match in hyperlink_matches:
            start_position = match.start()
            end_position = match.end()
            full_link = markdown_text[start_position:end_position]
            title = full_link[full_link.index('[') + 1:full_link.index('](')]
            link = full_link[full_link.index('](') + 2:-1]
            results.append({
                'title': title,
                'link': link,
                'full_link': full_link,
                'start': start_position,
                'end': end_position,
            })
        return results

    def _process_links(self):
        def to_file_name(input_string: str) -> str:
            replacement_char = '_'
            # Remove leading and trailing whitespace
            filename = input_string.strip()
            filename = filename.replace(' ', replacement_char)
            illegal_chars = r'[\/:*?"<>|~]'
            filename = re.sub(illegal_chars, ' ', filename)
            filename = filename.strip().replace(' ', replacement_char)
            filename = re.sub(r'[_]+', replacement_char, filename)
            # Trim filename length to 255 characters (a common limit on many filesystems)
            filename = filename[:255]
            if filename == '':
                filename = 'untitled'
            return filename

        def increasing_index_file(dst: str) -> str:
            index = 0
            parent = os.path.dirname(dst)
            name, ext = os.path.splitext(os.path.basename(dst))
            candidate = dst
            while os.path.exists(candidate):
                candidate = parent + '/' + name + str(index) + ext
                index = index + 1

            return candidate

        def process_hyperlinks(hyperlinks: []):
            for match in hyperlinks:
                markdown_text = match['full_link']
                is_picture_ref = markdown_text.startswith('!')
                title = match['title']
                link = match['link']
                generate_file = len(link) == 0
                full_file_name = to_file_name(title)
                file_name, file_ext = os.path.splitext(full_file_name)
                _, suggested_file_ext = os.path.splitext(os.path.basename(link))
                if suggested_file_ext.startswith('.'):
                    file_ext = suggested_file_ext
                if is_picture_ref and generate_file and file_ext.lower() != '.png':
                    file_ext = '.png'
                abs_link = increasing_index_file(get_config_files(self._config_file) + '/' + file_name + file_ext)
                processed_link = '.' + abs_link.removeprefix(os.path.dirname(get_config_files(self._config_file)))

                if generate_file:
                    if is_picture_ref:
                        if not paste_image(abs_link):
                            processed_link = '<no image in clipboard>'
                    else:
                        clip = pyperclip.paste()
                        lines = []
                        if clip:
                            lines.append(clip)
                        write_lines(abs_link, lines)
                else:
                    origin_abs_link = to_abs_path(self._config_file, link)
                    new_parent_dir = os.path.dirname(abs_link)
                    origin_parent_dir = os.path.dirname(origin_abs_link)
                    # TODO no test-case for `file_already_at_dst_dir` :(
                    file_already_at_dst_dir = os.path.exists(new_parent_dir) and os.path.exists(
                        origin_parent_dir) and os.path.samefile(new_parent_dir, origin_parent_dir)
                    if os.path.exists(origin_abs_link) and not file_already_at_dst_dir:
                        os.makedirs(new_parent_dir, exist_ok=True)
                        shutil.copy(origin_abs_link, abs_link)
                    else:
                        processed_link = None

                if processed_link:
                    match['processed_link'] = processed_link

            return hyperlinks

        used_links = set()

        for i, line in enumerate(self._lines):
            line_links = process_hyperlinks(self._gather_links(line))

            for h in sort_by_end(line_links):
                new_link = h.get('processed_link', None)
                used_links.add(h.get('processed_link', h['link']))

                if new_link:
                    prefix = ''
                    is_picture_ref = h['full_link'].startswith('!')
                    if is_picture_ref:
                        prefix = '!'
                    full_link = prefix + '[' + h['title'] + '](' + new_link + ')'
                    line = line[:h['start']] + full_link + line[h['end']:]
                    self._update(i, line)

        existing_files: [str] = self._gather_existing_files()
        unused_files: [str] = list(filter(lambda f: f not in used_links, existing_files))
        self._update_unused(unused_files)

    def _update(self, i, line):
        self._lines[i] = line
        self._changed = True
        pass

    def _update_unused(self, unused: [str]):
        def get_unused_files_task() -> {}:
            tasks = self._parse_tasks()
            for t in tasks:
                if self._lines[t['start']] == UNUSED_FILES:
                    return t

            lines = [
                UNUSED_FILES,
                '',
            ]
            self._insert_all(0, lines)
            return {
                'start': 0,
                'end': len(lines),
            }

        if len(unused) == 0:
            return
        task = get_unused_files_task()
        for u in unused:
            self._insert(task['start'] + 1, '- [](' + u + ')')

    def _gather_existing_files(self) -> [str]:
        config_files = get_config_files(self._config_file)
        dir = os.path.basename(config_files)
        for root, _, files in os.walk(config_files):
            return list(map(lambda f: './' + dir + '/' + f, files))
        return []

    def _trim_lines(self):
        for t in sort_by_end(self._parse_tasks()):
            i = t['start'] - 1
            if i < 0:
                continue

            if len(self._lines[i].strip()) > 0:
                self._insert(i + 1, '')
        trim_trailing_empty_lines(self._lines)

    def _update_checkboxes_status(self):
        for i, line in enumerate(self._lines):
            index = checkbox_status_index(line)

            if index < 0 or line[index] != ' ':
                continue

            question = '? - '
            if question not in line:
                continue

            has_answer = line.index(question) + len(question) < len(line) - 1

            if not has_answer:
                continue

            self._update(i, line[:index] + 'x' + line[index + 1:])
        pass


def as_nested_dict(intervals: []) -> []:
    def find_parent(group: {}):
        candidate = None
        for g in intervals:
            if g == group:
                continue
            if g['start'] <= group['start'] and g['end'] >= group['end']:
                if not candidate or (g['end'] - g['start']) < (candidate['end'] - candidate['start']):
                    candidate = g

        return candidate

    root = []

    for interval in intervals:
        parent = find_parent(interval)
        if not parent and interval not in root:
            root.append(interval)
            continue
        children = parent.get('children', [])

        if interval not in children:
            children.append(interval)
            parent['children'] = children
    return root


def to_abs_path(config_file: str, src_path: str) -> str:
    if src_path.startswith('~'):
        return os.path.expanduser(src_path)
    elif src_path.startswith('./') or src_path.startswith('../'):
        return os.path.dirname(config_file) + '/' + src_path

    return src_path


def sort_by_end(a: []) -> []:
    return sorted(a, key=lambda x: x['end'], reverse=True)


def log(message: str) -> None:
    with open(LOG_FILE, mode='a') as log_file:
        print(message, file=log_file)


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 1:
        args.append('')
    TaskMaster(taskflow_file=args[0], history_file=args[1]).execute()
