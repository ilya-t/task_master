import os
import subprocess
import document
from typing import Union


def get_shell_executions(executions_dir: str) -> [{}]:
    if not os.path.isdir(executions_dir):
        return []

    results = []
    for name in os.listdir(executions_dir):
        exec_dir = os.path.join(executions_dir, name)
        if not os.path.isdir(exec_dir):
            continue

        output_path = os.path.join(exec_dir, 'output')
        if not os.path.exists(output_path):
            continue

        output_lines = document.read_lines(output_path)
        if len(output_lines) == 0:
            continue

        status = ''
        result_path = os.path.join(exec_dir, 'execution_result')
        if os.path.exists(result_path):
            result_lines = document.read_lines(result_path)
            if len(result_lines) > 0:
                status = result_lines[0].strip()

        results.append({
            'file': output_lines[0],
            'status': status,
            'exec_dir': exec_dir,
        })
    return results


def capture_output(cmd: str, ignore_errors=False) -> Union[str, None]:
    try:
        return subprocess.check_output(
            cmd, 
            universal_newlines=True, 
            shell=True, 
            stderr=subprocess.STDOUT,
        )
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
