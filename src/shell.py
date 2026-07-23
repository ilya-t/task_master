import json
import os
import shutil
import subprocess
from typing import Optional, Union

import document


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


def spawned_executions_logfile(executions_dir: str) -> str:
    return os.path.join(executions_dir, 'spawned_executions.log')


def record_spawned_execution(
    executions_dir: str,
    cmd: str,
    pid: int,
    dst: str,
    exec_dir: str,
):
    path = spawned_executions_logfile(executions_dir)
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'a') as f:
        f.write(json.dumps({
            'cmd': cmd,
            'pid': pid,
            'dst': dst,
            'exec_dir': exec_dir,
        }) + '\n')


def iter_spawned_execution_entries(executions_dir: str) -> list:
    path = spawned_executions_logfile(executions_dir)
    if not os.path.exists(path):
        return []
    entries = []
    for line in document.read_lines(path):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def is_process_alive(pid: int, proc: Optional[subprocess.Popen] = None) -> bool:
    if proc is not None and proc.poll() is not None:
        return False
    try:
        # Reap our own zombie children so kill(pid, 0) does not keep seeing them.
        waited_pid, _ = os.waitpid(pid, os.WNOHANG)
        if waited_pid == pid:
            return False
    except (ChildProcessError, OSError):
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # Process table entry may still be a zombie owned by another parent.
    try:
        state = subprocess.check_output(
            ['ps', '-p', str(pid), '-o', 'state='],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return bool(state) and 'Z' not in state.upper()
    except (subprocess.CalledProcessError, FileNotFoundError, PermissionError):
        return False


def is_dst_spawn_alive(
    executions_dir: str,
    dst: str,
    shell_launches: Optional[list] = None,
) -> bool:
    shell_launches = shell_launches or []
    for entry in iter_spawned_execution_entries(executions_dir):
        if entry.get('dst') != dst:
            continue
        pid = entry.get('pid')
        if pid is None:
            continue
        proc = None
        for sl in shell_launches:
            if sl.get('output') == dst:
                proc = sl.get('proc')
                break
        if is_process_alive(pid, proc=proc):
            return True
    return False


def drop_executions_claiming_path(executions_dir: str, dst: str) -> list:
    """
    Remove finished/stale exec dirs whose output path matches dst.
    Returns the list of removed exec_dir paths.
    """
    living_dirs = set()
    for entry in iter_spawned_execution_entries(executions_dir):
        if entry.get('dst') != dst:
            continue
        pid = entry.get('pid')
        if pid is None:
            continue
        if is_process_alive(pid):
            living_dirs.add(entry.get('exec_dir'))

    # Uncached read: callers often invoke this before creating a new exec_dir.
    executions = get_shell_executions(executions_dir) if os.path.exists(executions_dir) else []
    to_drop = []
    for e in executions:
        if e['file'] == dst or e['file'].endswith(dst) or dst.endswith(e['file']):
            if e['exec_dir'] in living_dirs:
                continue
            to_drop.append(e['exec_dir'])
    for exec_dir in to_drop:
        if exec_dir and os.path.isdir(exec_dir):
            shutil.rmtree(exec_dir)
    return to_drop
