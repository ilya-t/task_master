import os
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


def _get_link_with_retcode(src: str, retcode: str) -> str:
    name, ext = os.path.splitext(os.path.basename(src))
    new_name = f'{name}-retcode={retcode}{ext}'
    parent = os.path.dirname(src)
    index = ''
    while os.path.exists(parent + '/' + new_name):
        if len(index) == 0:
            index = '0'
        else:
            index = str(int(index) + 1)
        new_name = f'{name}{index}-retcode={retcode}{ext}'

    return parent + '/' + new_name
