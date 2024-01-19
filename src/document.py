import os
import re

STATUS_IN_PROGRESS = '-'
STATUS_OPEN = ' '


def get_padding(line: str) -> str:
    if len(line) == 0:
        return ''
    try:
        return line[:line.index('- [')]
    except ValueError:
        return ''


def is_checkbox(line: str, status: str = None) -> bool:
    sl = line.lstrip()
    checkbox: bool = len(sl) >= 4 and sl.startswith('- [') and sl[4] == ']'

    if not checkbox:
        return False

    if status:
        return line[len(get_padding(line)) + 3] == status

    return True


class Document:
    def __init__(self, file: str):
        super().__init__()
        self._file: str = file
        if os.path.exists(self._file):
            self._lines: [str] = read_lines(self._file)
        else:
            self._lines: [str] = []
        self._changed = False

    def lines(self) -> [str]:
        return self._lines

    def insert(self, index: int, line: str):
        self._lines.insert(index, line)
        self._changed = True

    def insert_all(self, index: int, lines: [str]):
        for l in reversed(lines):
            self._lines.insert(index, l)
        self._changed = True

    def remove(self, start: int, end: int):
        new_lines = []
        new_lines.extend(self._lines[:start])
        new_lines.extend(self._lines[end + 1:])
        self._lines = new_lines
        self._changed = True

    def remove_line(self, index: int):
        self._lines.pop(index)
        self._changed = True

    def update(self, i, line):
        self._lines[i] = line
        self._changed = True
        pass

    def trim_trailing_empty_lines(self):
        if trim_trailing_empty_lines(self._lines):
            self._changed = True

    def has_changed(self):
        return self._changed

    def save(self):
        if not self.has_changed():
            return
        write_lines(dst=self._file, lines=self._lines)

    # deprecated use: get_check_groups_nested + flatten
    def get_check_groups(self) -> []:
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

        def remove_duplicates(data: [{}]) -> [{}]:
            seen = set()
            unique_data = []

            for item in data:
                # Convert the dictionary to a frozenset to make it hashable
                frozen_item = frozenset(item.items())

                if frozen_item not in seen:
                    seen.add(frozen_item)
                    unique_data.append(item)

            return unique_data

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
        check_groups = remove_duplicates(check_groups)
        return check_groups

    def _parse_nested_groups(self, dst: [], start: int, end: int) -> None:
        g = None
        root_padding = len(get_padding(self._lines[start]))
        group_padding = len(get_padding(self._lines[start]))
        for i, line in enumerate(self._lines[start:end + 1]):
            new_padding = len(get_padding(line))

            if new_padding > group_padding:
                if not g:
                    g = {'start': start + i}
                    g['line'] = self.line(start + i)
                    group_padding = new_padding
                children = []
                self._parse_nested_groups(children, start + i, end)
                g['children'] = children

            if new_padding < group_padding:
                if g:
                    g['end'] = start + i - 1
                    dst.append(g)
                    group_padding = root_padding
                g = None

            if new_padding < root_padding:
                return

    def get_check_groups_nested(self, start: int, end: int) -> []:
        check_groups = []
        check_group = {}
        for i, line in enumerate(self._lines[start:end + 1]):
            li = start + i
            if is_checkbox(line) and 'start' not in check_group:
                check_group['start'] = li

            end_of_file = li == len(self._lines) - 1
            if 'start' in check_group and (not is_checkbox(line) or end_of_file):
                if end_of_file:
                    check_group['end'] = li
                else:
                    check_group['end'] = li - 1

                check_groups.append(check_group)
                check_group = {}

        for group in check_groups:
            children = []
            self._parse_nested_groups(children, group['start'], group['end'])
            group['children'] = children

        return check_groups

    def get_topics(self) -> {}:
        check_groups = self.get_check_groups()
        topics = []
        topic = {}
        in_code_block = False
        for i, line in enumerate(self._lines):
            if line.startswith('```'):
                in_code_block = not in_code_block
            line_is_topic = line.startswith('#') and not in_code_block
            if line_is_topic and 'start' not in topic:
                topic['start'] = i
                continue

            end_of_file = i == len(self._lines) - 1
            if 'start' in topic and (line_is_topic or end_of_file):
                if end_of_file:
                    topic['end'] = i
                else:
                    topic['end'] = i - 1
                topic_groups = filter(lambda g: topic['start'] <= g['start'] <= topic['end'], check_groups)
                topic['check_groups'] = _distinct_ranges_list(topic_groups)

                topics.append(topic)
                topic = {
                    'start': i
                }

        return topics

    def get_topic_lines(self, topic: {}) -> [str]:
        return self._lines[topic['start']: topic['end'] + 1]

    def get_topic_by_line(self, index: int) -> {}:
        candidate = None
        for t in self.get_topics():

            if t['start'] > index:
                continue

            if not candidate:
                candidate = t
                continue
            offset_new = index - t['start']
            offset_old = index - candidate['start']

            if offset_new < offset_old:
                candidate = t

        return candidate

    def get_topic_by_title(self, title: str) -> {}:
        for t in self.get_topics():
            if get_line_title(self._lines[t['start']]) == title:
                return t

        return None

    def inspect_topic(self, topic: {}) -> {}:
        result = {}
        result.update(topic)
        root_start = topic['start']
        root_lvl = get_topic_level(self._lines[root_start])
        children = []
        for t in self.get_topics():
            if t['start'] <= root_start:
                continue

            current_lvl = get_topic_level(self._lines[t['start']])

            if current_lvl <= root_lvl:
                break

            children.append(t)

        children = sort_by_start(children)
        result['children'] = children
        return result

    def line(self, index: int) -> str:
        return self._lines[index]

    def extend(self, lines: [str]):
        if len(lines) == 0:
            return
        self._lines.extend(lines)
        self._changed = True
        pass

    def as_tasks_tree(self) -> []:
        def get_status(line: str) -> str:
            ci = checkbox_status_index(line)
            if ci >= 0:
                return line[ci]
            else:
                return STATUS_OPEN

        def to_tasks(check_group: {}) -> [{}]:
            results = []
            start_ = check_group['start']
            end_ = check_group['end']
            root_padding = get_padding(self._lines[start_])
            for i, l in enumerate(self._lines[start_: end_ + 1]):
                li = start_ + i
                subtasks = []
                for c in check_group['children']:
                    if c['start'] == li + 1:
                        subtasks = to_tasks(c)
                if get_padding(l) == root_padding:
                    results.append({
                        'title': get_line_title(l),
                        'status': get_status(l),
                        'children': subtasks,
                    })
            return results

        def first_task_with_address(tasks: []) -> {}:
            for t in tasks:
                if 'address' in t:
                    return t

        # if not self._file.endswith('main.md'):
        #     return {}

        result = []
        for topic in self.get_topics():
            start = topic['start']
            end = topic['end']
            title = get_line_title(self.line(start))
            task = {
                'title': title,
                'status': get_status(self.line(start)),
                'children': [],
            }

            address = split_title_to_address(title)
            if len(address) > 1:
                task['address'] = address

            result.append(task)

            check_groups: [{}] = self.get_check_groups_nested(start, end)

            if len(check_groups) == 0:
                continue

            for group in check_groups:
                task['children'] = to_tasks(group)

        task_with_parent = first_task_with_address(result)
        while task_with_parent:
            result.remove(task_with_parent)
            address: [str] = task_with_parent['address']
            task_with_parent['title'] = address[-1]
            task_with_parent.pop('address')
            address.pop(len(address) - 1)
            parent_task = self._generate_task_by_address(address, result)
            parent_task['children'].append(task_with_parent)

            task_with_parent = first_task_with_address(result)

        return result
        # {
        #     'root': {
        #         'active': {
        #             'one': {},
        #             'two': {},
        #         },
        #     }
        # }

    def _find_task_by_address(self, addr: [str], tasks: [{}]) -> {}:
        if len(addr) == 0:
            return None
        for t in tasks:
            if t['title'] == addr[0]:
                if len(addr) > 1:
                    return self._find_task_by_address(addr[1:], t['children'])
                else:
                    return t
        return None

    def _generate_task_by_address(self, addr: [str], tasks: [{}]) -> {}:
        existing_parent_addr = []
        nearest_existing_parent = None
        for part in addr:
            existing_parent_addr.append(part)
            parent = self._find_task_by_address(existing_parent_addr, tasks)
            if parent:
                nearest_existing_parent = parent
            else:
                break

        if nearest_existing_parent:
            addr = addr[len(existing_parent_addr):]

        if len(addr) == 0:
            return nearest_existing_parent

        last = None
        result = None

        for title in reversed(addr):
            new = {
                'title': title,
                'status': STATUS_OPEN,
                'children': [],
            }

            if last:
                last['children'].append(new)

            if not result:
                result = new
            last = new

        if nearest_existing_parent:
            nearest_existing_parent['children'].append(last)
        else:
            tasks.append(last)
        return result


def _distinct_ranges_list(ranges: [{}]) -> [{}]:
    keys = set()
    results = []

    for r in ranges:
        key = f'{r["start"]}/{r["end"]}'
        if key in keys:
            continue
        keys.add(key)
        results.append(r)
    return results


def trim_trailing_empty_lines(lines: [str]) -> bool:
    changed = False
    while len(lines) > 0 and lines[-1].strip() == '':
        lines.pop(-1)
        changed = True
    return changed


def write_lines(dst: str, lines: [str]) -> None:
    parent = os.path.dirname(dst)
    os.makedirs(parent, exist_ok=True)
    updated_content = ''.join(map(lambda l: l + '\n', lines))
    text_file = open(dst, "w")
    text_file.write(updated_content)
    text_file.close()


def remove_trailing_newline(s: str) -> str:
    if s.endswith('\n'):
        return s[:-1]
    return s


def read_lines(src) -> [str]:
    with open(src, 'r') as file:
        return list(map(remove_trailing_newline, file.readlines()))


def checkbox_status_index(line) -> int:
    if not is_checkbox(line):
        return -1

    return len(get_padding(line)) + 3


def is_task(line: str, status: str = None) -> bool:
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
    if len(s) == 0:
        return s
    return s[s.index(t_symbol) + 1:].strip()


def get_topic_level(line: str) -> int:
    level = 0
    while line.startswith('#'):
        line = line.removeprefix('#')
        level += 1
    return level


def sort_by_end(a: []) -> []:
    return sorted(a, key=lambda x: x['end'], reverse=True)


def sort_by_start(ranges: [{}]) -> [{}]:
    return sorted(ranges, key=lambda x: x['start'])


def get_links(markdown_text: str) -> []:
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


def split_title_to_address(title: str) -> [str]:
    return list(map(lambda part: part.strip(), title.split('->')))
