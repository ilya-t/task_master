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


import document
from document import Document, sort_by_end


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

    if len(document.get_line_title(prev).strip()) == 0:
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


def convert_subtask_placeholder_at(doc: Document, index: int) -> None:
    lines = doc.lines()
    prev = lines[index - 1]
    parent_padding = get_padding(prev)
    next_index = index_after_blank_run(lines, index)
    child_padding = parent_padding + '    '
    new_line = child_padding + '- [ ] '
    doc.update(index, new_line)
    if next_index > index + 1:
        # Collapse any extra blank lines in the same gap.
        doc.remove(index + 1, next_index - 1)


def maybe_insert_subtask_checkboxes(doc: Document) -> None:
    index = 1
    while index < len(doc.lines()):
        if should_convert_subtask_placeholder(doc.lines(), index):
            convert_subtask_placeholder_at(doc, index)
        index += 1


def can_add_trailing_checkbox(doc: Document, start: int, end: int, unused_files_topic: str) -> bool:
    lines = doc.lines()
    start_line = lines[start]
    group_padding = get_padding(start_line)
    all_completed = True
    if len(group_padding) > 0 and start > 0:
        # Nested groups need a completed parent before trailing slots make sense.
        nested_group_parent_completed = lines[start - 1].strip().startswith('- [x]')
        if not nested_group_parent_completed:
            all_completed = False

    for gl in lines[start:end + 1]:
        if not is_checkbox(gl, status='x'):
            # Any open checkbox means the group still needs a slot.
            all_completed = False

    if all_completed:
        return False

    already_has_trailing_checkbox = lines[end].rstrip() == group_padding + '- [ ]'
    if already_has_trailing_checkbox:
        # Group already ends with the auto-generated empty checkbox.
        return False

    end_line = lines[end]
    if (get_padding(end_line) == group_padding
            and is_checkbox(end_line, status=' ')
            and len(document.get_line_title(end_line).strip()) == 0):
        # Placeholder normalization already added the trailing slot at this level.
        return False

    if document.get_line_title(doc.line(start - 1)) == unused_files_topic:
        # Unused files are managed separately.
        return False

    return True


def inject_extra_checkboxes(doc: Document, unused_files_topic: str) -> None:
    insertions = []
    check_groups = doc.get_check_groups_at_range(
        start=0,
        end=len(doc.lines()) - 1,
    )
    for group in sort_by_end(check_groups):
        start: int = group['start']
        end: int = group['end']
        if can_add_trailing_checkbox(doc, start, end, unused_files_topic):
            line = doc.line(start)
            padding = get_padding(line)
            insertions.append(
                {
                    'end': end + 1,
                    'line': padding + '- [ ] '
                }
            )

    for insertion in sort_by_end(insertions):
        doc.insert(insertion['end'], insertion['line'])
