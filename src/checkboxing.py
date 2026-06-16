from __future__ import annotations

STATUS_IN_PROGRESS = '-'
STATUS_URGENT = '!'
STATUS_OPEN = ' '

# Hyphen-minus and en-dash are both treated as checkbox bullets.
CHECKBOX_BULLETS = ('-', '\u2013')


def _checkbox_marker_index(line: str) -> int:
    stripped = line.lstrip()
    if len(stripped) < 5:
        return -1

    if stripped[0] not in CHECKBOX_BULLETS or stripped[2] != '[' or stripped[4] != ']':
        return -1

    return len(line) - len(stripped)


def get_padding(line: str) -> str:
    if len(line) == 0:
        return ''

    index = _checkbox_marker_index(line)
    if index < 0:
        return ''
    return line[:index]


def is_checkbox(line: str, status: str = None) -> bool:
    marker_index = _checkbox_marker_index(line)
    if marker_index < 0:
        return False

    rest = line[marker_index:]
    if len(rest) < 5 or rest[0] not in CHECKBOX_BULLETS or rest[2] != '[' or rest[4] != ']':
        return False

    if status:
        return rest[3] == status

    return True


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
    ti = s.find(t_symbol)
    if ti < 0:
        return ''
    return s[ti + 1:].strip()


def index_after_blank_run(lines: [str], start: int) -> int:
    index = start
    while index < len(lines) and lines[index].strip() == '':
        index += 1
    return index


def should_convert_subtask_placeholder(lines: [str], index: int) -> bool:
    line = lines[index]
    if is_checkbox(line) or line.startswith('#'):
        # Already structured content.
        return False

    prev = lines[index - 1]
    if not is_checkbox(prev):
        # Placeholders must sit right under a checkbox.
        return False

    if len(get_line_title(prev).strip()) == 0:
        # Do not treat gaps after empty trailing checkboxes as subtasks.
        return False

    parent_padding = get_padding(prev)
    next_index = index_after_blank_run(lines, index)
    if next_index >= len(lines):
        # Nothing follows this gap.
        return False

    next_line = lines[next_index]
    if not is_checkbox(next_line):
        # Only fill gaps between checkboxes.
        return False

    if get_padding(next_line) != parent_padding:
        # Sibling checkboxes must share the same indent.
        return False

    return True

