import os
import re
import typing

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
UNUSED_FILES = '# unused local files'


def get_config_files(config_file: str) -> str:
    name, _ = os.path.splitext(os.path.basename(config_file))
    return os.path.dirname(config_file) + '/' + name + '.files'


def get_padding(line: str) -> str:
    if len(line) == 0:
        return ''
    try:
        return line[:line.index('- [')]
    except ValueError:
        return ''



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


def is_checkbox(line: str, status: str = None) -> bool:
    l = line.lstrip()
    is_checkbox = len(l) >= 4 and l.startswith('- [') and l[4] == ']'

    if not is_checkbox:
        return False

    if status:
        return line[len(get_padding(line)) + 3] == status

    return True


def checkbox_status_index(line) -> int:
    if not is_checkbox(line):
        return -1

    return len(get_padding(line)) + 3


def distinct_ranges_list(ranges: [{}]) -> [{}]:
    keys = set()
    results = []

    for r in ranges:
        key = f'{r["start"]}/{r["end"]}'
        if key in keys:
            continue
        keys.add(key)
        results.append(r)
    return results


class TaskMaster:
    def __init__(self,
                 taskflow_file: str,
                 history_file: str,
                 timestamp_provider: Callable[[], int] = current_timestamp,
                 executions_logfile: str = python_script_path + '/executions.log') -> None:
        super().__init__()
        self._changed = False
        self._timestamp_provider = timestamp_provider
        self._config_file = taskflow_file
        self._history_file = history_file
        self._lines: [str] = read_lines(self._config_file)
        self._memories_dir = HISTORY_DIR + '/' + str(uuid.uuid4())
        self._executions_logfile = executions_logfile
        self._cached_executions = None

    def _untitled_to_tasks(self) -> None:
        if self._lines[0].startswith('# '):
            return

        datetime_obj = datetime.fromtimestamp(self._timestamp_provider())
        current_time = datetime_obj.strftime('%Y.%m.%d ')

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
        def can_add_trailing_checkbox(start: int, end: int) -> bool:
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

            if all_completed:
                return False

            already_has_trailing_checkbox = self._lines[end].rstrip() == group_padding + '- [ ]'
            if already_has_trailing_checkbox:
                return False

            if self._lines[start-1] == UNUSED_FILES:
                return False

            return True

        def try_insert_checkboxes(groups: []) -> None:
            for group in sort_by_end(groups):
                start: int = group['start']
                end: int = group['end']
                if can_add_trailing_checkbox(start, end):
                    line = self._lines[start]
                    padding = line[:line.index('- [')]
                    self._insert(end + 1, padding + '- [ ] ')

                children = group.get('children', None)
                if children:
                    try_insert_checkboxes(children)

        check_groups = as_nested_dict(self._parse_check_groups())
        try_insert_checkboxes(check_groups)

    def _parse_topics(self) -> {}:
        check_groups = self._parse_check_groups()
        topics = []
        topic = {}
        for i, line in enumerate(self._lines):
            line_is_topic = line.startswith('#')
            if line_is_topic and 'start' not in topic:
                topic['start'] = i
                continue

            end_of_file = i == len(self._lines) - 1
            if 'start' in topic and (line_is_topic or end_of_file):
                if end_of_file:
                    topic['end'] = i
                else:
                    topic['end'] = i - 1
                topic_groups = filter(lambda g: g['start'] >= topic['start'] and g['start'] <= topic['end'], check_groups)
                topic['check_groups'] = distinct_ranges_list(topic_groups)

                topics.append(topic)
                topic = {
                    'start': i
                }

        return topics

    def _move_checkboxes_comments_into_tasks(self):
        def fix_space_groups_bounds(sg: []) -> []:
            for s in sg:
                i: int = s['start']

                while i <= s['end']:
                    if self._lines[i].startswith('#'):
                        s['end'] = i - 1
                        break
                    i += 1
            return sg

        def add_space_groups(target_tasks: []):
            for t in target_tasks:
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
                t['space_groups'] = fix_space_groups_bounds(space_groups)
            pass

        tasks = self.exclude_unused_files_topic(self._parse_topics())
        add_space_groups(tasks)
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

                if len(get_line_title(self._lines[subtask_index]).strip()) == 0:
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
            task = get_line_title(insertion['task_line'])
            subtask = get_line_title(insertion['subtask_line'])
            new_task_lines.insert(0, '# [ ] ' + task + ' -> ' + subtask)
            if new_task_lines[-1].strip() != '':
                new_task_lines.append('')
            self._insert_all(index=task_start, lines=new_task_lines)
        pass

    def _remove_line(self, index: int):
        self._lines.pop(index)
        self._changed = True

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
        self._move_checkboxes_subtasks_into_tasks()
        self._inject_extra_checkboxes()
        self._move_completed_tasks()
        self._update_checkboxes_status()
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
        os.makedirs(self._memories_dir, exist_ok=True)
        shutil.copy(self._config_file, self._memories_dir + '/' + os.path.basename(self._config_file))
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
        def get_level(line: str) -> int:
            level = 0
            while line.startswith('#'):
                line = line.removeprefix('#')
                level += 1
            return level

        def get_parents(subtask: {}, tasks: [{}]):
            subtask_lvl = get_level(self._lines[subtask['start']])
            results = []
            for t in sort_by_end(tasks):
                is_below_subtask = t['end'] > subtask['start']
                if is_below_subtask:
                    continue
                lvl = get_level(self._lines[t['start']])

                if lvl < subtask_lvl:
                    results.append(self._lines[t['start']])

                if lvl == 1:
                    break

            return results

        def split_title_to_address(title: str) -> [str]:
            return list(map(lambda part: part.strip(), title.split('->')))

        def get_insertion_specs(task: {}) -> {}:
            start = task['start']
            end = task['end']
            lines: [] = self._lines[start + 1:end + 1]
            trim_trailing_empty_lines(lines)
            address = [self._lines[start]]

            for p in get_parents(task, tasks):
                address.insert(0, p)
            address = list(map(lambda e: get_line_title(e), address))
            if len(address) == 1:
                address = split_title_to_address(get_line_title(self._lines[start]))
            return {
                'lines': lines,
                'address': address,
            }
        if self._history_file == '':
            return

        tasks = self._parse_topics()
        insertions = []

        for t in sort_by_end(tasks):
            start = t['start']
            end = t['end']
            task_title = self._lines[start]

            if not is_task(task_title, status='x'):
                continue

            specs = get_insertion_specs(t)
            insertions.append(specs)
            checkbox_line = self._find_checkbox_by_address(specs['address'])
            if checkbox_line >= 0:
                index = checkbox_status_index(self._lines[checkbox_line])
                if self._lines[checkbox_line][index] == '^':
                    self._update(checkbox_line, self._lines[checkbox_line][:index] + 'x' + self._lines[checkbox_line][index + 1:])

            self._remove(start, end)

        overall_insertions = 0
        for insertion in insertions:
            overall_insertions += len(insertion['lines'])

        if overall_insertions == 0:
            return

        history_lines = self._read_history_file()

        for insertion in insertions:
            history_lines = self.insert_topic_to_history(history_lines, insertion)

        write_lines(self._history_file, history_lines)

    @staticmethod
    def insert_topic_to_history(history_lines: [str], topic_insertion: [{}]) -> [str]:
        address = topic_insertion['address']

        def get_title(address_index: int) -> str:
            return '#' * (address_index + 1) + ' ' + address[address_index]

        def get_existing_topic_positions() -> [int]:
            lvl = 0
            positions = []
            title = get_title(lvl)
            for i, l in enumerate(history_lines):
                if l.rstrip() != title:
                    continue

                positions.append(i)
                if len(positions) == len(address):
                    break
                lvl += 1
                title = get_title(lvl)
            return positions

        topic_positions = get_existing_topic_positions()

        # add non-existent topics
        if len(topic_positions) < len(address):
            last_existing_topic_lvl = len(topic_positions)

            new_topics = []
            while last_existing_topic_lvl < len(address):
                new_topics.append(get_title(last_existing_topic_lvl))
                last_existing_topic_lvl += 1

            if len(topic_positions) == 0:
                existing_topic_line = 0
            else:
                existing_topic_line = topic_positions[-1] + 1
            _insert_all(history_lines, existing_topic_line, new_topics)

        # add topic content
        topic_positions = get_existing_topic_positions()
        content_insertion_line = topic_positions[-1] + 1
        lines: [str] = topic_insertion['lines']
        if len(lines[-1].strip()) > 0 and len(history_lines[content_insertion_line].strip()) > 0:
            lines.append('')

        _insert_all(history_lines, content_insertion_line, lines)
        return history_lines

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

        def process_hyperlinks(line_index: int, hyperlinks: []):
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

                if not is_picture_ref and title.startswith('`') and title.endswith('`'):
                    processed_link = self._process_shell_request(line_index, title, link)
                elif generate_file:
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
                    processed_link = None

                if processed_link:
                    match['processed_link'] = processed_link

            return hyperlinks

        used_links = set()

        for i, line in enumerate(self._lines):
            line_links = process_hyperlinks(i, self._gather_links(line))

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
        self._prepare_unused(unused_files)
        self._process_unused()

    def _update(self, i, line):
        self._lines[i] = line
        self._changed = True
        pass

    def get_unused_files_topic(self) -> {}:
        result = {}
        for i, line in enumerate(self._lines):
            if line == UNUSED_FILES:
                result['start'] = i
                continue

            if 'start' in result and line.startswith('#'):
                result['end'] = i - 1
                break

        if 'start' not in result:
            return None
        if 'end' not in result:
            result['end'] = len(self._lines) - 1
        return result

    def _prepare_unused(self, unused: [str]):
        if len(unused) == 0:
            return

        topic = self.get_unused_files_topic()
        if not topic:
            lines = [
                UNUSED_FILES,
                '',
            ]
            self._insert_all(0, lines)
            start = 0
        else:
            start = topic['start']

        for u in unused:
            self._insert(start + 1, '- [ ] [complete to delete](' + u + ')')

    def _process_unused(self):
        topic = self.get_unused_files_topic()
        if not topic:
            return

        config_files = get_config_files(self._config_file)
        for i in reversed(range(topic['start'], topic['end'] + 1)):
            line = self._lines[i]
            status = checkbox_status_index(line)
            if status < 0:
                continue

            if line[status] != 'x':
                continue

            links = self._gather_links(line)

            if len(links) == 0:
                continue

            link = links[0]['link']
            src = to_abs_path(self._config_file, link)
            is_local_config_file = os.path.basename(os.path.dirname(src)) == os.path.basename(config_files) # TODO improve check
            if is_local_config_file and os.path.exists(src):
                mem_dir = self._memories_dir + '/deleted_files'

                os.makedirs(mem_dir, exist_ok=True)
                dst = mem_dir + '/' + os.path.basename(src)
                shutil.move(src, dst)
                log(f'moving: {link} -> {dst}')
            self._remove_line(i)


    def _gather_existing_files(self) -> [str]:
        config_files = get_config_files(self._config_file)
        dir = os.path.basename(config_files)
        for root, _, files in os.walk(config_files):
            return list(map(lambda f: './' + dir + '/' + f, files))
        return []

    def _trim_lines(self):
        for t in sort_by_end(self._parse_topics()):
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

    def _read_history_file(self) -> []:
        parent = os.path.dirname(self._history_file)
        os.makedirs(parent, exist_ok=True)
        history_lines = []
        if os.path.exists(self._history_file):
            history_lines = read_lines(self._history_file)
        if len(history_lines) == 0:
            history_lines.append('')
        return history_lines

    def _find_checkbox_by_address(self, address: []) -> int:
        checkbox_topics = list(address[0:-1])
        checkbox_title = address[-1]
        parent_topic_start = -1
        parent_topic_end = -1
        topics = self._parse_topics()

        while len(checkbox_topics) > 0:
            target = checkbox_topics.pop(0)
            for t in topics:
                start = t['start']
                if get_line_title(self._lines[start]) == target and start > parent_topic_start:
                    parent_topic_start = start
                    parent_topic_end = t['end']
                    break

        if len(checkbox_topics) > 0:
            return -1

        for i in range(parent_topic_start, parent_topic_end + 1):
            line = self._lines[i]
            if is_checkbox(line) and get_line_title(line) == checkbox_title:
                return i
        return 0

    def exclude_unused_files_topic(self, topics: [{}]) -> [{}]:
        results = []
        for t in topics:
            if self._lines[t['start']] == UNUSED_FILES:
                continue
            results.append(t)
        return results

    def _move_checkboxes_subtasks_into_tasks(self):
        tasks = self.exclude_unused_files_topic(self._parse_topics())

        for t in sort_by_start(tasks):
            nested_groups = as_nested_dict(t['check_groups'])
            if len(nested_groups) == 0:
                continue

            root_group = nested_groups[0]
            start = root_group['start']
            end = root_group['end']

            extract_start = None
            extract_end = None
            extract_group_padding = None

            for i in range(start, end+1):
                if extract_start:
                    subtasks_stopped = len(get_padding(self._lines[i])) <= len(extract_group_padding)

                    if subtasks_stopped:
                        break

                    extract_end = i
                else:
                    line = self._lines[i]
                    if not is_checkbox(line, status='^'):
                        continue

                    if len(self._lines) - 1 < i + 1:
                        continue

                    extract_group_padding = get_padding(self._lines[i])
                    no_need_to_extract = len(get_padding(self._lines[i + 1])) <= len(extract_group_padding)

                    if no_need_to_extract:
                        continue

                    extract_start = i + 1

            if extract_start and extract_end:
                insertion_lines = [
                    '# [ ] ' + get_line_title(self._lines[t['start']]) + ' -> ' + get_line_title(self._lines[extract_start - 1]),
                ]
                padding = get_padding(self._lines[extract_start])
                insertion_lines.extend(map(lambda e: e.removeprefix(padding), self._lines[extract_start:extract_end+1]))
                self._remove(extract_start, extract_end)
                self._insert_all(t['start'], insertion_lines)
                self._move_checkboxes_subtasks_into_tasks()
                return

    def _process_shell_request(self, line_index: int, title: str, link: str) -> str:
        if len(link.strip()) == 0:
            dst = increasing_index_file(get_config_files(self._config_file) + '/cmd.log')
            write_lines(dst, lines=['<waiting for output>'])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            raw_cmd = title.removeprefix('`').removesuffix('`')
            script_path = self._memories_dir + '/' + os.path.basename(dst) + '.sh'
            script_lines = []

            bashrc = python_script_path + './bashrc'
            if os.path.exists(bashrc):
                script_lines.extend(read_lines(bashrc))

            # TODO: lines.extend(find_dive_in_block(line_index))
            script_lines.append(raw_cmd)
            script_lines.append(f'echo "{dst}:$?" >> {self._executions_logfile}')
            write_lines(script_path, script_lines)
            cmd = f'/bin/bash {script_path} &> {dst} &'
            os.system(cmd)
            return './' + os.path.basename(os.path.dirname(dst)) + '/' + os.path.basename(dst)
        else:
            executions = self._get_shell_executions()
            for e in reversed(executions):
                if e['file'].endswith(link.removeprefix('.')): # TODO: not precise file detection
                    status: str = e['status']
                    if not status.isdigit():
                        continue

                    name, ext = os.path.splitext(os.path.basename(link))
                    new_name = f'{name}-retcode={status}{ext}'

                    src = to_abs_path(self._config_file, link)
                    dst = os.path.dirname(src) + '/' + new_name
                    shutil.move(src, dst)
                    self._remove_execution_results(link)
                    return link.removesuffix(os.path.basename(link)) + new_name
            return link

    def _get_shell_executions(self) -> [{}]:
        if self._cached_executions:
            return self._cached_executions
        abs_path = to_abs_path(self._config_file, self._executions_logfile)
        if not os.path.exists(abs_path):
            return []

        def parse_line(s: str) -> {}:
            file_and_status = s.split(':')
            return {
                'file': file_and_status[0],
                'status': file_and_status[1],
            }

        self._cached_executions = list(map(parse_line, read_lines(abs_path)))
        return self._cached_executions

    def _remove_execution_results(self, link: str):
        abs_path = to_abs_path(self._config_file, self._executions_logfile)
        if not os.path.exists(abs_path):
            return

        def keep_execution(s: str) -> bool:
            is_same = s.split(':')[0].endswith(link.removeprefix('.'))
            return not is_same

        lines = list(filter(keep_execution, read_lines(abs_path)))
        write_lines(abs_path, lines)


def increasing_index_file(dst: str) -> str:
    index = 0
    parent = os.path.dirname(dst)
    name, ext = os.path.splitext(os.path.basename(dst))
    candidate = dst
    while os.path.exists(candidate):
        candidate = parent + '/' + name + str(index) + ext
        index = index + 1

    return candidate


def _insert_all(dst: [str], index: int, lines: [str]):
    for l in reversed(lines):
        dst.insert(index, l)


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


def sort_by_start(ranges: [{}]) -> [{}]:
    return sorted(ranges, key=lambda x: x['start'])


def log(message: str) -> None:
    with open(LOG_FILE, mode='a') as log_file:
        print(message, file=log_file)


def is_task(line, status: str = None) -> bool:
    line = line.lstrip()

    while line.startswith('#'):
        line = line.removeprefix('#')
    line = '-' + line
    index = checkbox_status_index(line)

    if index < 0:
        return False

    if status and line[index] != status:
        return False
    return True


def get_line_title(s: str) -> str:
    if is_task(s) or is_checkbox(s):
        t_symbol = ']'
    else:
        t_symbol = '#'
        while s.startswith('##'):
            s = s.removeprefix('#')

    return s[s.index(t_symbol) + 1:].strip()



if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 1:
        args.append('')
    TaskMaster(taskflow_file=args[0], history_file=args[1]).execute()
