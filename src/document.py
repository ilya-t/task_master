import os


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
        self._file = file
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


def read_lines(src) -> [str]:
    def remove_trailing_newline(l: str) -> str:
        if l.endswith('\n'):
            return l[:-1]
        return l

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
