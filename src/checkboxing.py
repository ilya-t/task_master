import document
from document import Document, get_padding, sort_by_end


def index_after_blank_run(lines: [str], start: int) -> int:
    index = start
    while index < len(lines) and lines[index].strip() == '':
        index += 1
    return index


def should_convert_subtask_placeholder(lines: [str], index: int) -> bool:
    line = lines[index]
    if document.is_checkbox(line) or line.startswith('#'):
        # Already structured content.
        return False

    prev = lines[index - 1]
    if not document.is_checkbox(prev):
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
    if not document.is_checkbox(next_line):
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
    group_padding = start_line[:start_line.index('- [')]
    all_completed = True
    if len(group_padding) > 0 and start > 0:
        # Nested groups need a completed parent before trailing slots make sense.
        nested_group_parent_completed = lines[start - 1].strip().startswith('- [x]')
        if not nested_group_parent_completed:
            all_completed = False

    for gl in lines[start:end + 1]:
        if not document.is_checkbox(gl, status='x'):
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
            and document.is_checkbox(end_line, status=' ')
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
