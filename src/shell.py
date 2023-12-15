import document


def get_shell_executions(executions_path: str) -> [{}]:
    def parse_line(s: str) -> {}:
        file_and_status = s.split(':')
        return {
            'file': file_and_status[0],
            'status': file_and_status[1].strip(),
        }

    return list(map(parse_line, document.read_lines(executions_path)))
