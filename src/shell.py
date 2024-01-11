import subprocess

import document


def get_shell_executions(executions_path: str) -> [{}]:
    def parse_line(s: str) -> {}:
        file_and_status = s.split(':')
        return {
            'file': file_and_status[0],
            'status': file_and_status[1].strip(),
        }

    return list(map(parse_line, document.read_lines(executions_path)))


def capture_output(cmd: str, ignore_errors=False) -> str | None:
    try:
        return subprocess.check_output(cmd, universal_newlines=True, shell=True)
    except subprocess.CalledProcessError as e:
        print(f'Command "{cmd}" failed with error:')
        print(e.output)
        if ignore_errors:
            return None
        raise e
