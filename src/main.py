import argparse
import os
import re
import shutil
import time
import uuid
from datetime import datetime
from typing import Callable

import pyperclip
from PIL import ImageGrab  # pip install pillow==10.0.0

import document
import shell
from document import get_padding
from document import is_checkbox
from document import sort_by_end
from document import sort_by_start

python_script_path = os.path.dirname(__file__)
LOG_FILE = python_script_path + '/operations.log'
DIVE_TEMPLATE_INTRO = 'dive-in:'
DIVE_TEMPLATE_SCRIPT_BODY = 'git checkout branch_name'
HISTORY_DIR = '/tmp/task_master_memories'
UNUSED_FILES = '# unused local files'
WAIT_EXECUTIONS_ENV = 'TASK_MASTER_WAIT_ALL_EXECUTIONS'

def get_config_files(config_file: str) -> str:
    name, _ = os.path.splitext(os.path.basename(config_file))
    return os.path.dirname(config_file) + '/' + name + '.files'


def current_timestamp() -> int:
    return int(time.time())


def paste_image(file_path: str) -> bool:
    image = ImageGrab.grabclipboard()

    if image is not None:
        parent = os.path.dirname(file_path)
        os.makedirs(parent, exist_ok=True)
        image.save(file_path, 'PNG')
        return True

    return False


class TaskMaster:
    def __init__(self,
                 taskflow_file: str,
                 history_file: str,
                 archived_links_processor: str = None,
                 timestamp_provider: Callable[[], int] = current_timestamp,
                 executions_logfile: str = python_script_path + '/executions.log') -> None:
        super().__init__()
        self._timestamp_provider = timestamp_provider
        self._config_file = taskflow_file
        self._history_file = history_file
        self._doc = document.Document(self._config_file)
        self._memories_dir = HISTORY_DIR + '/' + str(uuid.uuid4())
        self._executions_logfile = executions_logfile
        self._cached_executions = None
        self._archived_links_processor = archived_links_processor
        self._shell_launches = 0

    def _untitled_to_tasks(self) -> None:
        if self._doc.lines()[0].startswith('# '):
            return

        datetime_obj = datetime.fromtimestamp(self._timestamp_provider())
        current_time = datetime_obj.strftime('%Y.%m.%d ')

        self._doc.insert(0, '# [ ] ' + current_time)

    def _insert_setup_template_to_tasks(self):
        def find_parent_dive_in_block(index: int) -> []:
            topic = self._doc.get_topic_by_line(index)
            if not topic:
                return None

            title = self._doc.lines()[topic['start']]
            parent = split_title_to_address(document.get_line_title(title))[0]
            parent_topic = self._doc.get_topic_by_title(parent)

            if not parent_topic:
                return None

            return self._find_dive_in_block(parent_topic)

        for topic in sort_by_end(self._doc.get_topics()):
            if self._doc.lines()[topic['start']] == UNUSED_FILES:
                continue

            i = topic['start'] + 1
            line = self._doc.lines()[i]

            if line.strip() != '':
                continue

            self._doc.remove(start=i, end=i)
            template = [
                DIVE_TEMPLATE_INTRO,
                '```sh',
            ]

            parent_dive_in = find_parent_dive_in_block(i)
            if parent_dive_in:
                template.extend(parent_dive_in)
            else:
                template.append(DIVE_TEMPLATE_SCRIPT_BODY)
            template.append('```')

            self._doc.insert_all(i, template)
        pass

    def _inject_extra_checkboxes(self):
        def can_add_trailing_checkbox(start: int, end: int) -> bool:
            start_line = self._doc.lines()[start]
            group_padding = start_line[:start_line.index('- [')]
            all_completed = True
            if len(group_padding) > 0 and start > 0:
                nested_group_parent_completed = self._doc.lines()[start - 1].strip().startswith('- [x]')
                if not nested_group_parent_completed:
                    all_completed = False

            for gl in self._doc.lines()[start:end + 1]:
                if gl.startswith(group_padding + '- [ ]'):
                    all_completed = False

            if all_completed:
                return False

            already_has_trailing_checkbox = self._doc.lines()[end].rstrip() == group_padding + '- [ ]'
            if already_has_trailing_checkbox:
                return False

            if self._doc.lines()[start-1] == UNUSED_FILES:
                return False

            return True

        def try_insert_checkboxes(groups: []) -> None:
            for group in sort_by_end(groups):
                start: int = group['start']
                end: int = group['end']
                if can_add_trailing_checkbox(start, end):
                    line = self._doc.lines()[start]
                    padding = line[:line.index('- [')]
                    self._doc.insert(end + 1, padding + '- [ ] ')

                children = group.get('children', None)
                if children:
                    try_insert_checkboxes(children)

        groups = self._doc.get_check_groups()
        check_groups = as_nested_dict(groups)
        try_insert_checkboxes(check_groups)

    def _move_checkboxes_comments_into_tasks(self):
        def fix_space_groups_bounds(sg: []) -> []:
            for s in sg:
                i: int = s['start']

                while i <= s['end']:
                    if self._doc.lines()[i].startswith('#'):
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

        tasks = self.exclude_unused_files_topic(self._doc.get_topics())
        add_space_groups(tasks)
        insertions = []

        for t in sort_by_end(tasks):
            space_groups = sort_by_end(t['space_groups'])

            if len(space_groups) == 0:
                continue

            for s in space_groups:
                subtask_index = s['start'] - 1
                group_padding = get_padding(self._doc.lines()[subtask_index])
                lines = list(map(lambda s: s.removeprefix(group_padding), self._doc.lines()[s['start']:s['end'] + 1]))
                if len(''.join(lines).strip()) == 0:
                    continue

                if len(document.get_line_title(self._doc.lines()[subtask_index]).strip()) == 0:
                    continue

                insertions.append({
                    'task_line': self._doc.lines()[t['start']],
                    'subtask_line': self._doc.lines()[subtask_index],
                    'lines': lines,
                    'start': s['start'],
                    'end': s['end'],
                })
                self._doc.lines()[subtask_index] = self._doc.lines()[subtask_index].replace('- [ ]', '- [^]')
                self._doc.remove(s['start'], s['end'])

        for insertion in sort_by_end(insertions):
            task_start: int = self._doc.lines().index(insertion['task_line'])
            new_task_lines: [str] = insertion['lines']
            task = document.get_line_title(insertion['task_line'])
            subtask = document.get_line_title(insertion['subtask_line'])
            new_task_lines.insert(0, '# [ ] ' + task + ' -> ' + subtask)
            if new_task_lines[-1].strip() != '':
                new_task_lines.append('')
            self._doc.insert_all(index=task_start, lines=new_task_lines)
        pass

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

        if self._doc.has_changed():
            self._make_defensive_copy()
            self._doc.save()

        self._try_wait_executions()

    def _make_defensive_copy(self):
        os.makedirs(self._memories_dir, exist_ok=True)
        shutil.copy(self._config_file, self._memories_dir + '/' + os.path.basename(self._config_file))
        pass

    def _move_completed_tasks(self):
        def get_parents(subtask: {}, tasks: [{}]):
            subtask_lvl = document.get_topic_level(self._doc.lines()[subtask['start']])
            results = []
            for t in sort_by_end(tasks):
                is_below_subtask = t['end'] > subtask['start']
                if is_below_subtask:
                    continue
                lvl = document.get_topic_level(self._doc.lines()[t['start']])

                if lvl < subtask_lvl:
                    results.append(self._doc.lines()[t['start']])

                if lvl == 1:
                    break

            return results

        def get_insertion_specs(task: {}) -> {}:
            task = self._doc.inspect_topic(task)
            start = task['start']
            end = task['end']
            children = task['children']
            if len(children) > 0:
                end = children[-1]['end']

            address: [str] = [self._doc.line(start)]

            for p in get_parents(task, tasks):
                address.insert(0, p)
            address = list(map(lambda e: document.get_line_title(e), address))
            if len(address) == 1:
                address = split_title_to_address(document.get_line_title(self._doc.lines()[start]))

            root = address[0]
            dst = None
            if root.startswith('[[') and root.endswith(']]'):
                address.pop(0)
                dst = root[2:-2]
                if not dst.lower().endswith('.md'):
                    dst = dst + '.md'

            real_root_level = len(address)
            raw_root_level = document.get_topic_level(self._doc.line(start))
            level_inc = real_root_level - raw_root_level

            if level_inc > 0:
                extra_level = ('#' * level_inc)
                for c in children:
                    i = c['start']
                    self._doc.update(i, extra_level + self._doc.line(i))

            lines: [] = self._doc.lines()[start + 1:end + 1]
            document.trim_trailing_empty_lines(lines)
            return {
                'lines': lines,
                'address': address,
                'start': start,
                'end': end,
                'file_name': dst,
            }

        tasks = self._doc.get_topics()
        insertions = []

        for t in sort_by_end(tasks):
            start = t['start']
            end = t['end']
            task_title = self._doc.lines()[start]

            if not document.is_task(task_title, status='x'):
                continue

            self._prepare_task_links_for_archive(task=t)
            specs = get_insertion_specs(t)
            insertions.append(specs)
            checkbox_line = self._find_checkbox_by_address(specs['address'])
            if checkbox_line >= 0:
                index = document.checkbox_status_index(self._doc.lines()[checkbox_line])
                if self._doc.lines()[checkbox_line][index] == '^':
                    self._doc.update(checkbox_line, self._doc.lines()[checkbox_line][:index] + 'x' + self._doc.lines()[checkbox_line][index + 1:])

            if self._history_file or specs['file_name']:
                self._doc.remove(specs['start'], specs['end'])

        overall_insertions = 0
        for insertion in insertions:
            overall_insertions += len(insertion['lines'])

        if overall_insertions == 0:
            return

        for insertion in insertions:
            history_file = self._history_file
            custom_dst = insertion.get('file_name', None)
            if custom_dst:
                history_file = self._resolve_custom_history_file(custom_dst)

            if not history_file:
                continue

            d = document.Document(history_file)
            self.insert_topic_to_history(d, insertion)
            d.trim_trailing_empty_lines()
            d.save()

    @staticmethod
    def insert_topic_to_history(d: document.Document, topic_insertion: [{}]) -> None:
        address = topic_insertion['address']

        def get_title(address_index: int) -> str:
            if len(address) == 0:
                return None
            return '#' * (address_index + 1) + ' ' + address[address_index]

        def get_existing_topic_positions() -> [int]:
            lvl = 0
            positions = []
            title = get_title(lvl)
            for i, l in enumerate(d.lines()):
                if l.rstrip() != title:
                    continue

                positions.append(i)
                if len(positions) == len(address):
                    break
                lvl += 1
                title = get_title(lvl)
            return positions

        topic_positions = get_existing_topic_positions()

        # add non-existent topic titles
        if len(topic_positions) < len(address):
            last_existing_topic_lvl = len(topic_positions)

            new_topics = []
            while last_existing_topic_lvl < len(address):
                new_topics.append(get_title(last_existing_topic_lvl))
                last_existing_topic_lvl += 1

            if len(topic_positions) == 0:
                topics = d.get_topics()
                if len(topics) > 0:
                    existing_topic_line = topics[0]['start']
                else:
                    existing_topic_line = len(d.lines())
            else:
                existing_topic_line = topic_positions[-1] + 1

            if existing_topic_line > len(d.lines()) - 1:
                if len(d.lines()) > 0 and len(d.lines()[-1].strip()) > 0:
                    new_topics.insert(0, '')
                d.extend(new_topics)
            else:
                if not d.line(existing_topic_line - 1).startswith('#'):
                    new_topics.append('')
                d.insert_all(existing_topic_line, new_topics)

        # add topic content
        topic_positions = get_existing_topic_positions()
        if len(topic_positions) == 0:
            content_insertion_line = 0
        else:
            content_insertion_line = topic_positions[-1] + 1
        lines: [str] = topic_insertion['lines']
        not_ending_with_blank = len(lines[-1].strip()) > 0

        if not_ending_with_blank and (len(d.lines()) - 1 < content_insertion_line or len(d.lines()[content_insertion_line].strip()) > 0):
            lines.append('')

        if content_insertion_line > len(d.lines()) - 1:
            d.extend(lines)
        else:
            d.insert_all(content_insertion_line, lines)

    def _gather_links(self, markdown_text: str) -> []:
        patterns = [
            r'(?:!)?\[([^\]]+)\]\(([^\]]+)\)',
            r'(?:!)?\[([^\]]+)\]\(\)',
            r'(?:!)?\[\]\(\)',
            r'(?:!)?\[\]\(([^\]]+)\)',
        ]
        hyperlink_matches = []
        matches_keys = set()
        for p in patterns:
            matches = list(re.finditer(p, markdown_text))
            for m in matches:
                key: int = m.start()
                if key in matches_keys:
                    continue
                hyperlink_matches.append(m)
                matches_keys.add(key)

        results = []

        for match in hyperlink_matches:
            start_position = match.start()
            end_position = match.end()
            while end_position - 2 > start_position and markdown_text[end_position - 2] == ')':
                end_position = end_position - 1
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
                        document.write_lines(abs_link, lines)
                else:
                    processed_link = None

                if processed_link:
                    match['processed_link'] = processed_link

            return hyperlinks

        used_links = set()

        for i, line in enumerate(self._doc.lines()):
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
                    self._doc.update(i, line)

        existing_files: [str] = self._gather_existing_files()

        def is_unused(f: str) -> bool:
            return f not in used_links
        unused_files: [str] = list(filter(is_unused, existing_files))
        self._prepare_unused(unused_files)
        self._process_unused()

    def get_unused_files_topic(self) -> {}:
        result = {}
        for i, line in enumerate(self._doc.lines()):
            if line == UNUSED_FILES:
                result['start'] = i
                continue

            if 'start' in result and line.startswith('#'):
                result['end'] = i - 1
                break

        if 'start' not in result:
            return None
        if 'end' not in result:
            result['end'] = len(self._doc.lines()) - 1
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
            self._doc.insert_all(0, lines)
            start = 0
        else:
            start = topic['start']

        for u in unused:
            self._doc.insert(start + 1, '- [ ] [complete to delete](' + u + ')')

    def _process_unused(self):
        topic = self.get_unused_files_topic()
        if not topic:
            return

        config_files = get_config_files(self._config_file)
        for i in reversed(range(topic['start'], topic['end'] + 1)):
            line = self._doc.lines()[i]
            status = document.checkbox_status_index(line)
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
            self._doc.remove_line(i)
        topic = self.get_unused_files_topic()
        if topic['start'] == topic['end'] - 1:
            self._doc.remove(topic['start'], topic['end'])

    def _gather_existing_files(self) -> [str]:
        config_files = get_config_files(self._config_file)
        dir = os.path.basename(config_files)
        for root, _, files in os.walk(config_files):
            return list(map(lambda f: './' + dir + '/' + f, files))
        return []

    def _trim_lines(self):
        for t in sort_by_end(self._doc.get_topics()):
            i = t['start'] - 1
            if i < 0:
                continue

            if len(self._doc.lines()[i].strip()) > 0:
                self._doc.insert(i + 1, '')
        self._doc.trim_trailing_empty_lines()

    def _update_checkboxes_status(self):
        for i, line in enumerate(self._doc.lines()):
            index = document.checkbox_status_index(line)

            if index < 0 or line[index] != ' ':
                continue

            question = '? - '
            if question not in line:
                continue

            has_answer = line.index(question) + len(question) < len(line) - 1

            if not has_answer:
                continue

            self._doc.update(i, line[:index] + 'x' + line[index + 1:])
        pass

    @staticmethod
    def prepare_file(file: str) -> [str]:
        parent = os.path.dirname(file)
        os.makedirs(parent, exist_ok=True)
        history_lines = []
        if os.path.exists(file):
            history_lines = document.read_lines(file)
        if len(history_lines) == 0:
            history_lines.append('')
        return history_lines

    def _find_checkbox_by_address(self, address: []) -> int:
        if len(address) == 0:
            return -1
        checkbox_topics = list(address[0:-1])
        checkbox_title = address[-1]
        parent_topic_start = -1
        parent_topic_end = -1
        topics = self._doc.get_topics()

        while len(checkbox_topics) > 0:
            target = checkbox_topics.pop(0)
            for t in topics:
                start = t['start']
                if document.get_line_title(self._doc.lines()[start]) == target and start > parent_topic_start:
                    parent_topic_start = start
                    parent_topic_end = t['end']
                    break

        if len(checkbox_topics) > 0:
            return -1

        for i in range(parent_topic_start, parent_topic_end + 1):
            line = self._doc.lines()[i]
            if is_checkbox(line) and document.get_line_title(line) == checkbox_title:
                return i
        return 0

    def exclude_unused_files_topic(self, topics: [{}]) -> [{}]:
        results = []
        for t in topics:
            if self._doc.lines()[t['start']] == UNUSED_FILES:
                continue
            results.append(t)
        return results

    def _move_checkboxes_subtasks_into_tasks(self):
        tasks = self.exclude_unused_files_topic(self._doc.get_topics())

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
                    subtasks_stopped = len(get_padding(self._doc.lines()[i])) <= len(extract_group_padding)

                    if subtasks_stopped:
                        break

                    extract_end = i
                else:
                    line = self._doc.lines()[i]
                    if not is_checkbox(line, status='^'):
                        continue

                    if len(self._doc.lines()) - 1 < i + 1:
                        continue

                    extract_group_padding = get_padding(self._doc.lines()[i])
                    no_need_to_extract = len(get_padding(self._doc.lines()[i + 1])) <= len(extract_group_padding)

                    if no_need_to_extract:
                        continue

                    extract_start = i + 1

            if extract_start and extract_end:
                insertion_lines = [
                    '# [ ] ' + document.get_line_title(self._doc.lines()[t['start']]) + ' -> ' + document.get_line_title(self._doc.lines()[extract_start - 1]),
                ]
                padding = get_padding(self._doc.lines()[extract_start])
                insertion_lines.extend(map(lambda e: e.removeprefix(padding), self._doc.lines()[extract_start:extract_end+1]))
                self._doc.remove(extract_start, extract_end)
                self._doc.insert_all(t['start'], insertion_lines)
                self._move_checkboxes_subtasks_into_tasks()
                return

    def _process_shell_request(self, line_index: int, title: str, link: str) -> str:
        if len(link.strip()) == 0:
            dst = increasing_index_file(get_config_files(self._config_file) + '/cmd.log')
            document.write_lines(dst, lines=['<waiting for output>'])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            # TODO: now is a good time to open executions.log
            # and clean lines that look like /path/to.files/cmd.log:0
            raw_cmd = title.removeprefix('`').removesuffix('`')
            script_path = self._memories_dir + '/' + os.path.basename(dst) + '.sh'
            script_lines = []

            shell_rc = os.path.expanduser('~') + '/.zshrc'
            if os.path.exists(shell_rc):
                script_lines.extend(document.read_lines(shell_rc))

            topic = self._doc.get_topic_by_line(line_index)
            if topic:
                block = self._find_dive_in_block(topic)
                if len(block) > 0:
                    block.insert(0, 'set -e')
                    script_lines.extend(block)
                    script_lines.append('set +e')

            script_lines.append(raw_cmd)
            script_lines.append(f'echo "{dst}:$?" >> {self._executions_logfile}')
            document.write_lines(script_path, script_lines)
            cmd = f'/bin/zsh {script_path} &> {dst} &'
            self._shell_launches += 1
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
                    if not os.path.exists(src):
                        continue

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

        self._cached_executions = shell.get_shell_executions(abs_path)
        return self._cached_executions

    def _remove_execution_results(self, link: str):
        abs_path = to_abs_path(self._config_file, self._executions_logfile)
        if not os.path.exists(abs_path):
            return

        def keep_execution(s: str) -> bool:
            is_same = s.split(':')[0].endswith(link.removeprefix('.'))
            return not is_same

        lines = list(filter(keep_execution, document.read_lines(abs_path)))
        document.write_lines(abs_path, lines)

    def _find_dive_in_block(self, topic: {}) -> [str]:
        dive_line = topic['start'] + 1
        lines = self._doc.lines()
        if not lines[dive_line].startswith(DIVE_TEMPLATE_INTRO):
            return []
        if not lines[dive_line + 1].startswith('```sh'):
            return []

        result = []
        for l in lines[dive_line + 2:]:
            if l.startswith('```'):
                break
            result.append(l)

        return result

    def _resolve_custom_history_file(self, name: str) -> str:
        doc_dir = os.path.dirname(self._config_file)
        candidate = doc_dir + '/' + name
        if os.path.exists(candidate):
            return candidate

        for root, dirs, files in os.walk(doc_dir):
            for f in files:
                if f.lower() == name.lower():
                    return root + '/' + f
        return candidate

    def _prepare_task_links_for_archive(self, task: {}) -> None:
        if not self._archived_links_processor:
            return

        pass

    def _try_wait_executions(self):
        if self._shell_launches == 0:
            return

        if os.environ.get(WAIT_EXECUTIONS_ENV, '') != 'true':
            return

        print('Blocking until all shell executions are completed!')

        def has_running_shells() -> bool:
            if not os.path.exists(self._executions_logfile):
                return True
            executions = shell.get_shell_executions(self._executions_logfile)
            for e in executions:
                if e['status'] == '':
                    return True
            return False

        timeout_sec = 10
        while has_running_shells() and timeout_sec >= 0:
            wait_step = .1
            timeout_sec = timeout_sec - wait_step
            time.sleep(wait_step)
        pass


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
    def find_parent(group: {}, where: {}):
        if group['start'] >= where['start'] and group['end'] <= where['end']:
            for c in where.get('children', []):
                candidate = find_parent(group, c)
                if candidate:
                    return candidate
            return where
        return None

    def first_child(group: {}, where: [{}]) -> {}:
        for child in where:
            if child['start'] > group['start'] and child['end'] <= group['end']:
                return child

        return None

    roots = []

    for interval in intervals:
        parent = None
        for r in roots:
            parent = find_parent(interval, r)
            if parent:
                break

        if not parent:
            c = first_child(interval, roots)
            if c:
                roots.remove(c)
                children = interval.get('children', [])
                children.append(c)
                interval['children'] = children
            roots.append(interval)
            continue

        children = parent.get('children', [])
        children.append(interval)
        parent['children'] = children
        # re-balance tree
        parent['children'] = as_nested_dict(parent['children'])
    return roots


def to_abs_path(config_file: str, src_path: str) -> str:
    if src_path.startswith('~'):
        return os.path.expanduser(src_path)
    elif src_path.startswith('./') or src_path.startswith('../'):
        return os.path.dirname(config_file) + '/' + src_path

    return src_path


def log(message: str) -> None:
    with open(LOG_FILE, mode='a') as log_file:
        print(message, file=log_file)


def split_title_to_address(title: str) -> [str]:
    return list(map(lambda part: part.strip(), title.split('->')))


def parse_args():
    parser = argparse.ArgumentParser(description='Captures and outputs all clipboard.')
    parser.add_argument('--archive', metavar='file', type=str,
                        help='Path to archive file that will be used by default when tasks are completed.')
    parser.add_argument('--experimental-archived-links-processor', metavar='command_line', type=str,
                        help='specifies a links processor that will be triggered when tasks are archived')
    parser.add_argument('task_file', help='Path to file for processing', type=str)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    TaskMaster(taskflow_file=args.task_file,
               history_file=args.archive,
               archived_links_processor=args.experimental_archived_links_processor,
               ).execute()
