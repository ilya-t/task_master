import argparse
import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import uuid
from datetime import datetime
from typing import Callable

from clipboard import ClipboardCompanion, build_clipboard_companion

import document
import shell
from document import get_padding
from document import is_checkbox
from document import sort_by_end, get_line_title
from document import sort_by_start

python_script_path = os.path.dirname(__file__)
execution_location_path = os.path.abspath('')

LOG_FILE = python_script_path + '/operations.log'
DIVE_TEMPLATE_INTRO = 'dive-in:'
DIVE_TEMPLATE_SCRIPT_BODY = 'git checkout branch_name'
HISTORY_DIR = '/tmp/task_master_memories'
UNUSED_FILES_TOPIC = 'unused local files (complete to delete all)'
UNUSED_FILES = f'# [ ] {UNUSED_FILES_TOPIC}'
ACTIVE_TASKS_OVERVIEW_TOPIC = '>>> (Active) <<<'
ACTIVE_TASKS_OVERVIEW = f'# {ACTIVE_TASKS_OVERVIEW_TOPIC}'
REMINDERS_TOPIC = '>>> (Reminders) <<<'
WAIT_EXECUTIONS_ENV = 'TASK_MASTER_WAIT_ALL_EXECUTIONS'
ERROR_NOTATION = '(GOT ERRORS AT COMPLETION)'


def get_config_files(config_file: str) -> str:
    name, _ = os.path.splitext(os.path.basename(config_file))
    path = os.path.dirname(config_file) + '/' + name + '.files'
    if path.startswith('~'):
        return os.path.expanduser(path)
    elif path.startswith('./'):
        return execution_location_path + path[1:]
    else:
        return path


def current_timestamp() -> int:
    return int(time.time())




class TaskMaster:
    def __init__(self,
                 taskflow_file: str,
                 history_file: str,
                 archived_links_processor: str = None,
                 timestamp_provider: Callable[[], int] = current_timestamp,
                 executions_logfile: str = None,
                 memories_dir: str = None,
                 configs_file: str = None,
                 clipboard: ClipboardCompanion | None = None,
                 ) -> None:
        super().__init__()
        self._timestamp_provider = timestamp_provider
        self._config_file = taskflow_file
        self._configs_file = configs_file
        self._history_file = history_file
        self._doc = document.Document(self._config_file)
        if memories_dir:
            self._memories_dir = memories_dir
        else:
            self._memories_dir = HISTORY_DIR + '/' + str(uuid.uuid4())
        if not executions_logfile:
            executions_logfile = python_script_path + '/executions.log'
        self._executions_logfile = executions_logfile
        self._cached_executions = None
        self._archived_links_processor = archived_links_processor
        self._shell_launches = []
        self._shell_path = self._determine_shell()
        if clipboard:
            self._clipboard = clipboard
        else:
            self._clipboard = build_clipboard_companion()

    def _determine_shell(self) -> str:
        for candidate in ['/bin/zsh', '/bin/bash', '/bin/sh']:
            if os.path.exists(candidate):
                return candidate
        return 'sh'

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
            parent = document.split_title_to_address(document.get_line_title(title))[0]
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
                if not document.is_checkbox(gl, status='x'):
                    all_completed = False

            if all_completed:
                return False

            already_has_trailing_checkbox = self._doc.lines()[end].rstrip() == group_padding + '- [ ]'
            if already_has_trailing_checkbox:
                return False

            if document.get_line_title(self._doc.line(start - 1)) == UNUSED_FILES_TOPIC:
                return False

            return True

        def try_insert_checkboxes(dst: [], groups: []) -> None:
            for group in sort_by_end(groups):
                start: int = group['start']
                end: int = group['end']
                if can_add_trailing_checkbox(start, end):
                    line = self._doc.line(start)
                    padding = get_padding(line)
                    dst.append(
                        {
                            'end': end + 1,
                            'line': padding + '- [ ] '
                        }
                    )

        check_groups = self._doc.get_check_groups_at_range(
            start=0,
            end=len(self._doc.lines()) - 1,
        )
        insertions = []
        try_insert_checkboxes(insertions, check_groups)
        for insertion in sort_by_end(insertions):
            self._doc.insert(insertion['end'], insertion['line'])

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
                check_groups = sorted(self._doc.get_check_groups(t), key=lambda x: x['start'])
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

        tasks = self.exclude_generated_topics(self._doc.get_topics())
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

    def _prepare_reminders_topic_lines(self, reminders: []) -> [{}]:
        results = []

        if len(reminders) == 0:
            return results

        results.append({
            'title': f'# {REMINDERS_TOPIC}',
        })

        for r in reminders:
            results.append({
                'indent': '',
                'title': r['title'],
                'line_index': r['line_index'],
            })

        return results

    def _prepare_ongoing_topic_lines(self, tasks: [], level: int = 0) -> [{}]:
        def find_single_ongoing_checkbox_line(task: {}) -> int:
            candidate = -1
            for c in task['children']:
                li = c.get('line_index', -1)
                if li == -1:
                    continue
                l = self._doc.line(li)
                if not document.is_checkbox(l):
                    return -1

                if document.is_checkbox(l, status=document.STATUS_IN_PROGRESS):
                    if candidate != -1:
                        return -1

                    inner_checkbox = find_single_ongoing_checkbox_line(c)

                    if inner_checkbox >= 0:
                        candidate = inner_checkbox
                    else:
                        candidate = li

            return candidate

        results = []
        for task in tasks:
            indent = "    " * level
            topic_title = task['title'].strip()
            if topic_title.startswith('[[') and topic_title.endswith(']]'):
                topic_title = topic_title.removeprefix('[[').removesuffix(']]')

            if 'line_index' in task and document.is_task(self._doc.line(task['line_index'])):
                ongoing_checkbox_index = find_single_ongoing_checkbox_line(task)
                if ongoing_checkbox_index >= 0:
                    results.append(
                        {
                            'indent': indent,
                            'title': topic_title,
                            'line_index': ongoing_checkbox_index,
                        }
                    )
                    continue

            if len(task['children']) == 0:
                results.append(
                    {
                        'indent': indent,
                        'title': topic_title,
                        'line_index': task['line_index'],
                    }
                )

            else:
                results.append(
                    {
                        'indent': indent,
                        'title': topic_title,
                    }
                )
            results.extend(self._prepare_ongoing_topic_lines(tasks=task['children'], level=level + 1))
        return results

    def _process_and_extract_reminders(self, tasks_tree: [], active_only: bool) -> []:
        results = []
        today = datetime.fromtimestamp(self._timestamp_provider())

        for t in tasks_tree:
            if t['status'] == document.STATUS_URGENT:
                raw_line = self._doc.line(t['line_index'])
                formatted_line: str = document.format_reminder_date(raw_line, today)

                if formatted_line:
                    self._doc.update(t['line_index'], formatted_line)
                    raw_line = formatted_line

                date, error = document.extract_reminder_date(document.get_line_title(raw_line))

                if len(error) > 0:
                    self._doc.update(t['line_index'], self._doc.line(t['line_index']) + f' **({error})**')

                if date and (not active_only or date <= today):
                    results.append(t)

            results.extend(self._process_and_extract_reminders(t['children'], active_only))

        return results

    def _sort_reminders(self, reminders: []) -> []:
        reminders.sort(key=lambda r: document.extract_reminder_date(r['title'])[0] or datetime.max)
        return reminders

    def get_reminders(self, active_only: bool = True) -> [dict]:
        """Return reminders filtered by due date if ``active_only`` is True."""
        all_reminders = document.filter_tasks_tree(
            self._doc.as_tasks_tree(), status=document.STATUS_URGENT)
        reminders = self._sort_reminders(
            self._process_and_extract_reminders(all_reminders, active_only))
        result = []
        for r in reminders:
            title = r['title']
            date, _ = document.extract_reminder_date(title)
            timestamp = int(date.timestamp())
            if ': ' in title:
                title = title.split(': ', 1)[1]
            entry = {
                'title': title,
                'line': r['line_index'] + 1,
            }
            if timestamp:
                entry['timestamp'] = str(timestamp)
            result.append(entry)
        return result


    def _inject_ongoing_overview(self):
        existing = self._doc.get_topic_by_title(ACTIVE_TASKS_OVERVIEW_TOPIC)

        if existing:
            self._doc.remove(existing['start'], existing['end'])

        existing = self._doc.get_topic_by_title(REMINDERS_TOPIC)

        if existing:
            self._doc.remove(existing['start'], existing['end'])

        ongoing_tasks = document.filter_tasks_tree(self._doc.as_tasks_tree(), status=document.STATUS_IN_PROGRESS)
        all_reminders = document.filter_tasks_tree(self._doc.as_tasks_tree(), status=document.STATUS_URGENT)
        active_reminders = self._sort_reminders(
            self._process_and_extract_reminders(all_reminders, True))

        if len(ongoing_tasks) == 0 and len(active_reminders) == 0:
            # Not so much is going on!
            return

        start = 0

        unused = self._doc.get_topic_by_title(UNUSED_FILES_TOPIC)
        if unused:
            start = unused['end']

        raw_lines: [{}] = self._prepare_ongoing_topic_lines(ongoing_tasks)
        if len(raw_lines) > 0:
            raw_lines.insert(0, {
                'title': f'# {ACTIVE_TASKS_OVERVIEW_TOPIC}',
            })
        raw_lines.extend(self._prepare_reminders_topic_lines(active_reminders))

        lines: [str] = []
        space_after_ongoing = 1 if len(ongoing_tasks) > 0 else 0
        space_after_reminders = 1 if len(active_reminders) > 0 else 0

        ongoing_topic_height: int = len(raw_lines) + space_after_ongoing + space_after_reminders + 1
        # +1 for static shift cause file first line is not 0
        for r in raw_lines:
            if 'line_index' in r:
                shifted_index = r['line_index'] + ongoing_topic_height
                lines.append(
                    f"{r['indent']}- [{r['title']}]({os.path.basename(self._config_file)}#L{shifted_index})"
                )
            else:
                if 'indent' in r:
                    lines.append(f"{r['indent']}- {r['title']}")
                else:
                    lines.append(r['title'])
        self._doc.insert_all(start, lines)
        pass

    def _fix_typos(self):
        if not self._configs_file:
            return

        if not os.path.exists(self._configs_file):
            return

        with open(self._configs_file, 'r') as file:
            configs = json.load(file)

        typos: {} = configs.get('typos', {})

        if len(typos) == 0:
            return

        for i, line in enumerate(self._doc.lines()):
            for wrong, correct in typos.items():
                if wrong in line:
                    self._doc.update(i, line.replace(wrong, correct))

    def execute(self):
        self._execute()
        self._try_wait_executions()
        if self._doc.has_changed():
            self._make_defensive_copy()
            self._doc.save()

    def _execute(self):
        self._fix_typos()
        self._untitled_to_tasks()
        self._insert_setup_template_to_tasks()
        self._move_checkboxes_comments_into_tasks()
        self._move_checkboxes_subtasks_into_tasks()
        self._inject_extra_checkboxes()
        self._move_completed_tasks()
        self._update_checkboxes_status()
        self._generate_new_links()
        self._process_unused_files()
        self._inject_ongoing_overview()
        self._trim_lines()

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
                address = document.split_title_to_address(document.get_line_title(self._doc.lines()[start]))

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
        processed_links = {}

        for t in sort_by_end(tasks):
            start = t['start']
            task_title = self._doc.lines()[start]

            if not document.is_task(task_title, status='x'):
                continue

            if document.get_line_title(task_title) == UNUSED_FILES_TOPIC:
                continue

            removed_lines = self._remove_trailing_checkboxes(t)
            t['end'] = t['end'] - removed_lines
            self._remove_task_checkboxes(t)
            prepared = self._prepare_task_links_for_archive(task=t, processed_links=processed_links)

            if not prepared:
                continue

            specs = get_insertion_specs(t)
            insertions.append(specs)
            checkbox_line = self._find_checkbox_by_address(specs['address'])
            if checkbox_line >= 0:
                index = document.checkbox_status_index(self._doc.lines()[checkbox_line])
                if self._doc.lines()[checkbox_line][index] == '^':
                    self._doc.update(checkbox_line,
                                     self._doc.lines()[checkbox_line][:index] + 'x' + self._doc.lines()[checkbox_line][
                                                                                      index + 1:])

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
    def insert_topic_to_history(d: document.Document, topic_insertion: {}) -> None:
        address = topic_insertion['address']

        def get_title(address_index: int) -> str:
            if len(address) == 0:
                return None
            return '#' * (address_index + 1) + ' ' + address[address_index]

        def get_existing_topic_positions() -> [int]:
            """Return line indexes for headings that already exist in ``d``."""
            lvl = 0
            positions: [int] = []
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

        topic_positions: [int] = get_existing_topic_positions()

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
                insertion_line = existing_topic_line
                insertion_line = insertion_line + get_topic_text_height(d, start=insertion_line)
                if insertion_line > 0 and len(d.line(insertion_line-1).strip()) != 0:
                    new_topics.insert(0, '')
                d.insert_all(insertion_line, new_topics)

        # add topic content
        topic_positions = get_existing_topic_positions()
        if len(topic_positions) == 0:
            content_insertion_line = 0
        else:
            content_insertion_line = topic_positions[-1] + 1
            content_insertion_line = content_insertion_line + get_topic_text_height(d, start=content_insertion_line)

            while len(d.lines()[content_insertion_line - 1].strip()) == 0:
                content_insertion_line = content_insertion_line - 1

        lines: [str] = list(topic_insertion['lines'])

        lines = TaskMaster._remove_duplicate_prefix(lines, d, topic_positions)

        if len(lines) == 0:
            return

        not_ending_with_blank = len(lines[-1].strip()) > 0

        if not_ending_with_blank and (
                len(d.lines()) - 1 < content_insertion_line or len(d.lines()[content_insertion_line].strip()) > 0):
            lines.append('')

        if content_insertion_line > len(d.lines()) - 1:
            d.extend(lines)
        else:
            d.insert_all(content_insertion_line, lines)

    @staticmethod
    def _remove_duplicate_prefix(lines: [str], d: document.Document, topic_positions: [int]) -> [str]:
        """Return ``lines`` minus any portion already stored under the target topic."""
        existing_lines: [str] = []
        if len(topic_positions) > 0:
            # start of the text section for the deepest subtopic
            existing_start = topic_positions[-1] + 1
            existing_height = get_topic_text_height(d, start=existing_start)
            existing_lines = d.lines()[existing_start:existing_start + existing_height]

        document.trim_trailing_empty_lines(lines)
        document.trim_trailing_empty_lines(existing_lines)

        if len(existing_lines) > 0 and lines[:len(existing_lines)] == existing_lines:
            return lines[len(existing_lines):]
        return lines

    def _generate_new_links(self):
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
                        if not self._clipboard.paste_image(abs_link):
                            processed_link = '<no image in clipboard>'
                    else:
                        clip = self._clipboard.paste_text()
                        lines = []
                        if clip:
                            lines.append(clip)
                        document.write_lines(abs_link, lines)
                else:
                    processed_link = None

                if processed_link:
                    match['processed_link'] = processed_link

            return hyperlinks

        for i, line in enumerate(self._doc.lines()):
            line_links = process_hyperlinks(i, document.get_links(line))

            for h in sort_by_end(line_links):
                new_link = h.get('processed_link', None)

                if new_link:
                    prefix = ''
                    is_picture_ref = h['full_link'].startswith('!')
                    if is_picture_ref:
                        prefix = '!'
                    full_link = prefix + '[' + h['title'] + '](' + new_link + ')'
                    line = line[:h['start']] + full_link + line[h['end']:]
                    self._doc.update(i, line)

    def _process_unused_files(self):
        used_link_lines = {}

        for i, line in enumerate(self._doc.lines()):
            line_links = document.get_links(line)

            for h in sort_by_end(line_links):
                link = urllib.parse.unquote(h['link'])
                link_lines = used_link_lines.get(link, set())
                link_lines.add(i)
                used_link_lines[link] = link_lines

        self._move_unused_to_bin(used_link_lines)
        existing_files: [str] = self._gather_existing_files()
        existing_files = list(filter(lambda f: not f.endswith('/.DS_Store'), existing_files))

        def is_unused(f: str) -> bool:
            return f not in used_link_lines

        unused_files: [str] = list(filter(is_unused, existing_files))
        self._update_unused_topic(unused_files)

    def get_unused_files_topic(self) -> {}:
        return self._doc.get_topic_by_title(UNUSED_FILES_TOPIC)

    def _update_unused_topic(self, unused: [str]):
        if len(unused) == 0:
            return

        topic = self.get_unused_files_topic()
        if not topic:
            lines = [
                UNUSED_FILES,
                '',
            ]
            self._doc.insert_all(0, lines)
            topic = self.get_unused_files_topic()

        start = topic['start']
        existing_lines = self._doc.get_topic_lines(topic)
        for u in unused:
            encoded = urllib.parse.quote(u)
            l = f'- [ ] [complete to delete]({encoded})'
            if l not in existing_lines:
                self._doc.insert(start + 1, l)

    def _used_outside_unused_files_topic(self, used_links_topics: {}, link: str) -> bool:
        topic = self.get_unused_files_topic()
        used_in: set = used_links_topics.get(link, set())
        for used_link_line_index in used_in:
            if used_link_line_index < topic['start']:
                return True
            if used_link_line_index > topic['end']:
                return True
        return False

    def _move_unused_to_bin(self, used_links_topics: {}):
        topic = self.get_unused_files_topic()
        if not topic:
            return

        delete_all: bool = document.is_task(self._doc.line(topic['start']), status='x')
        config_files = get_config_files(self._config_file)
        for i in reversed(range(topic['start'], topic['end'] + 1)):
            line = self._doc.lines()[i]
            if not document.is_checkbox(line, 'x') and not delete_all:
                continue

            links = document.get_links(line)

            if len(links) == 0:
                continue

            link = links[0]['link']
            if self._used_outside_unused_files_topic(used_links_topics, link):
                self._doc.remove_line(i)
                continue

            decoded_link = urllib.parse.unquote(link)
            src = to_abs_path(self._config_file, decoded_link)
            is_local_config_file = os.path.basename(os.path.dirname(src)) == os.path.basename(config_files)
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

    def exclude_generated_topics(self, topics: [{}]) -> [{}]:
        results = []
        for t in topics:
            if self._doc.lines()[t['start']] == UNUSED_FILES:
                continue
            if self._doc.lines()[t['start']] == ACTIVE_TASKS_OVERVIEW:
                continue
            results.append(t)
        return results

    def _move_checkboxes_subtasks_into_tasks(self):
        tasks = self.exclude_generated_topics(self._doc.get_topics())

        for t in sort_by_start(tasks):
            nested_groups = document.as_nested_dict(self._doc.get_check_groups(t))
            if len(nested_groups) == 0:
                continue

            root_group = nested_groups[0]
            start = root_group['start']
            end = root_group['end']

            extract_start = None
            extract_end = None
            extract_group_padding = None

            for i in range(start, end + 1):
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
                    '# [ ] ' + document.get_line_title(
                        self._doc.lines()[t['start']]) + ' -> ' + document.get_line_title(
                        self._doc.lines()[extract_start - 1]),
                ]
                padding = get_padding(self._doc.lines()[extract_start])
                insertion_lines.extend(
                    map(lambda e: e.removeprefix(padding), self._doc.lines()[extract_start:extract_end + 1]))
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
            script_lines = [f'#!{self._shell_path}']

            rc_file = None
            if self._shell_path.endswith('zsh'):
                rc_file = os.path.expanduser('~/.zshrc')
            elif self._shell_path.endswith('bash'):
                rc_file = os.path.expanduser('~/.bashrc')

            if rc_file and os.path.exists(rc_file):
                script_lines.append(f'source {rc_file} > /dev/null')

            topic = self._doc.get_topic_by_line(line_index)
            # script_lines.append('set -e')
            if topic:
                block = self._find_dive_in_block(topic)
                if len(block) > 0:
                    script_lines.append('# TASK MASTER: dive-in (start)')
                    script_lines.extend(block)
                    script_lines.append('# TASK MASTER: dive-in (end)')

            script_lines.append('')
            script_lines.append('# TASK MASTER: actual command')
            script_lines.append(raw_cmd)
            document.write_lines(script_path, script_lines)
            os.system('chmod +x '+script_path)
            if self._shell_path.endswith('zsh'):
                cmd = f"{script_path} &> {dst}; echo \"{dst}:$?\" >> {self._executions_logfile}"
            else:
                sed_expr = "sed -E 's/: line ([0-9]+): ([^:]+): command not found/:\\1: command not found: \\2/'"
                cmd = f"{script_path} 2>&1 | {sed_expr} > {dst}; ret=${{PIPESTATUS[0]}}; echo \"{dst}:$ret\" >> {self._executions_logfile}"
            subprocess.Popen([self._shell_path, '-c', cmd])
            self._shell_launches.append({
                'cmd': raw_cmd,
                'output': dst,
                'script_path': script_path,
            })
            return './' + os.path.basename(os.path.dirname(dst)) + '/' + os.path.basename(dst)
        else:
            executions = self._get_shell_executions()
            for e in reversed(executions):
                if e['file'].endswith(link.removeprefix('.')):  # TODO: not precise file detection
                    status: str = e['status']
                    if not status.isdigit():
                        continue

                    src = to_abs_path(self._config_file, link)

                    if not os.path.exists(src):
                        continue

                    dst: str = shell._get_link_with_retcode(src, status)
                    shutil.move(src, dst)
                    self._remove_execution_results(link)
                    return link.removesuffix(os.path.basename(link)) + os.path.basename(dst)
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

    def _prepare_task_links_for_archive(self, task: {}, processed_links: {}) -> bool:
        if not self._archived_links_processor:
            return True

        def process_file(path: str) -> str | None:
            if path in processed_links:
                return processed_links[path]
            if not os.path.exists(path):
                return path
            processor_shell = '/bin/bash' if os.path.exists('/bin/bash') else self._shell_path
            cmd = f"{processor_shell} -c '{self._archived_links_processor} \"{path}\"'"
            output = shell.capture_output(cmd, ignore_errors=True)
            if not output:
                return None
            outline: str = document.remove_trailing_newline(''.join(output))
            processed_links[path] = outline
            return outline

        task_lines = self._doc.get_topic_lines(task)
        abs_files_dir = get_config_files(self._config_file)
        files_dir = './' + os.path.basename(abs_files_dir)
        for i, line in enumerate(task_lines):
            line_links = document.get_links(line)

            for h in sort_by_end(line_links):
                link: str = h['link']

                if not link.startswith(files_dir):
                    continue

                abs_link = abs_files_dir + link[len(files_dir):]
                new_link = process_file(abs_link)
                if abs_link == new_link:
                    continue

                if not new_link:
                    li = task['start']
                    self._doc.update(li, self._doc.line(li) + ' ' + ERROR_NOTATION)
                    return False

                prefix = ''
                is_picture_ref = h['full_link'].startswith('!')
                if is_picture_ref:
                    prefix = '!'
                full_link = prefix + '[' + h['title'] + '](' + new_link + ')'
                line = line[:h['start']] + full_link + line[h['end']:]
                self._doc.update(task['start'] + i, line)
        return True

    def _try_wait_executions(self):
        if len(self._shell_launches) == 0:
            return

        if os.environ.get(WAIT_EXECUTIONS_ENV, '') != 'true':
            return

        print('Blocking until all shell executions are completed!')

        def has_running_shells() -> bool:
            if not os.path.exists(self._executions_logfile):
                print(f'executions file yet not present: {self._executions_logfile}')
                return True
            executions = shell.get_shell_executions(self._executions_logfile)
            for e in executions:
                if e['status'] == '':
                    print(f'wait for execution: {e}')
                    return True

            for sl in self._shell_launches:
                abs_path = sl['output']

                if os.path.exists(abs_path):
                    print(f'file without retcode still exists: {abs_path} (script: {sl["script_path"]}')
                    return True

            return False

        timeout_sec = 5
        while has_running_shells() and timeout_sec >= 0:
            wait_step = .5
            timeout_sec = timeout_sec - wait_step
            time.sleep(wait_step)
        pass

        self._execute()

    def _remove_trailing_checkboxes(self, task: {}) -> int:
        def find_trailing_checkboxes(check_groups: [{}]) -> [int]:
            results = []
            for g in check_groups:
                if self._doc.line(g['end']).strip() == '- [ ]':
                    results.append(g['end'])
            return results

        trailing_checkbox_lines: [int] = find_trailing_checkboxes(
            check_groups=self._doc.get_check_groups(task))
        lines_to_remove = sorted(trailing_checkbox_lines, reverse=True)
        for i in lines_to_remove:
            self._doc.remove_line(i)
        return len(lines_to_remove)

    def _remove_task_checkboxes(self, task: {}):
        for group in sort_by_end(self._doc.get_check_groups(task)):
            for i in range(group['start'], group['end']+1, 1):
                line: str = self._doc.lines()[i]
                if not document.is_checkbox(line):
                    continue
                excluded_checkbox = document.get_padding(line) + '-' + line[line.index(']') + 1:]
                self._doc.update(i, excluded_checkbox)
        pass

    def _inject_reminders(self):
        existing = self._doc.get_topic_by_title(REMINDERS_TOPIC)

        if existing:
            self._doc.remove(existing['start'], existing['end'])

        urgent_tasks = document.filter_tasks_tree(self._doc.as_tasks_tree(), status=document.STATUS_URGENT)

        if len(urgent_tasks) == 0:
            # Not so much is going on!
            return

        start = 0

        unused = self._doc.get_topic_by_title(UNUSED_FILES_TOPIC)
        if unused:
            start = unused['end']

        raw_lines: [{}] = self.prepare_ongoing_topic_lines(urgent_tasks)
        lines: [str] = []
        ongoing_topic_height: int = len(raw_lines) + 3
        # static +3:
        # 1 for title,
        # 1 for space after topic,
        # 1 for static shift cause file first line is not 0
        for r in raw_lines:
            if 'line_index' in r:
                shifted_index = r['line_index'] + ongoing_topic_height
                lines.append(
                    f"{r['indent']}- [{r['title']}]({os.path.basename(self._config_file)}#L{shifted_index})"
                )
            else:
                lines.append(f"{r['indent']}- {r['title']}")

        lines.insert(0, f'# {ACTIVE_TASKS_OVERVIEW_TOPIC}')
        self._doc.insert_all(start, lines)
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


def to_abs_path(config_file: str, src_path: str) -> str:
    if src_path.startswith('~'):
        return os.path.expanduser(src_path)
    elif src_path.startswith('./') or src_path.startswith('../'):
        return os.path.dirname(config_file) + '/' + src_path

    return src_path


def log(message: str) -> None:
    with open(LOG_FILE, mode='a') as log_file:
        print(message, file=log_file)


def parse_args():
    parser = argparse.ArgumentParser(description='Captures and outputs all clipboard.')
    parser.add_argument('--archive', metavar='file', type=str,
                        help='Path to archive file that will be used by default when tasks are completed.')
    parser.add_argument('--config', metavar='file', type=str,
                        help='Path to config file with extra features like typos and etc..')
    parser.add_argument('--experimental-archived-links-processor', metavar='command_line', type=str,
                        help='specifies a links processor that will be triggered when tasks are archived')
    parser.add_argument('--reminders', action='store_true',
                        help='Print all reminders in JSON format and exit')
    parser.add_argument('task_file', help='Path to file for processing', type=str)
    parser.add_argument('--executions-log',
                        metavar='file', type=str, required=False,
                        help='Path to file where shell executions will be stored',
                        )
    parser.add_argument('--memories-dir',
                        metavar='file', type=str, required=False,
                        help='Path to file where temporary files will be stored (mostly should be used for testing)',
                        )
    return parser.parse_args()


def get_topic_text_height(d: document.Document, start: int) -> int:
    lines_below = d.lines()[start:]
    i = 0
    code_block = False
    for l in lines_below:
        if l.startswith('```'):
            code_block = not code_block

        if not code_block and l.startswith('#'):
            break
        i = i + 1
    return i


def main():
    args = parse_args()
    tm = TaskMaster(taskflow_file=args.task_file,
                    history_file=args.archive,
                    archived_links_processor=args.experimental_archived_links_processor,
                    executions_logfile=args.executions_log,
                    memories_dir=args.memories_dir,
                    configs_file=args.config,
                    clipboard=build_clipboard_companion(),
                    )
    if args.reminders:
        print(json.dumps(tm.get_reminders(active_only=False)))
        return
    tm.execute()


if __name__ == "__main__":
    main()
