"""Shared tmux operations for the mobile UI and interactive shell commands."""
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
from router_dependency import ensure_router

BASE = Path(__file__).resolve().parent
SOCKET = os.environ.get('TERMINAL_MOBILE_SOCKET', 'terminal-mobile')
SESSION = 'agentes'
DEFAULT_PROJECT = Path(os.environ.get('TERMINAL_MOBILE_PROJECT', str(Path.home()))).expanduser().resolve()


def tmux(*args, check=True):
    result = subprocess.run(['tmux', '-L', SOCKET, *map(str, args)], capture_output=True, text=True, check=check)
    return result.stdout.strip()


def project_path(value):
    result = Path(value).expanduser().resolve(strict=True)
    if not result.is_dir():
        raise ValueError('Escolha uma pasta válida.')
    return str(result)


def load_projects():
    try:
        return json.loads((BASE / 'projects.json').read_text())
    except (OSError, ValueError):
        return [str(DEFAULT_PROJECT)]


def save_project(value):
    value = project_path(value)
    with (BASE / 'projects.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        paths = list(dict.fromkeys([*load_projects(), value]))
        temporary = BASE / 'projects.json.tmp'
        temporary.write_text(json.dumps(paths))
        temporary.replace(BASE / 'projects.json')
    return value


def agent_executable(agent):
    if agent not in ('codex', 'claude', 'shell'):
        raise ValueError('Agente inválido.')
    if agent == 'shell':
        return '/bin/bash'
    candidates = []
    if agent == 'codex':
        versions = Path.home() / '.nvm/versions/node'
        if versions.exists():
            candidates += sorted(versions.glob('*/bin/codex'), key=lambda p: tuple(int(v) for v in p.parts[-3].lstrip('v').split('.')), reverse=True)
    candidates += [Path.home() / '.local/bin' / agent]
    found = shutil.which(agent)
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise ValueError(f'{agent} não está instalado.')


def managed_environment(source=None):
    environment = dict(os.environ if source is None else source)
    # Automation can export NO_COLOR. It must not leak into interactive panes.
    environment.pop('NO_COLOR', None)
    environment['COLORTERM'] = 'truecolor'
    # Claude Code drops to 256 colors inside tmux unless told the client copes.
    environment['CLAUDE_CODE_TMUX_TRUECOLOR'] = '1'
    return environment


def configure_session():
    tmux('set-option', '-s', 'default-terminal', 'tmux-256color')
    features = tmux('show-options', '-sv', 'terminal-features')
    if 'xterm-256color:RGB' not in features:
        tmux('set-option', '-as', 'terminal-features', ',xterm-256color:RGB')
    tmux('set-option', '-s', 'focus-events', 'on')
    tmux('set-option', '-s', 'escape-time', '10')
    tmux('set-environment', '-gu', 'NO_COLOR')
    tmux('set-environment', '-g', 'COLORTERM', 'truecolor')
    tmux('set-environment', '-g', 'CLAUDE_CODE_TMUX_TRUECOLOR', '1')
    for session in tmux('list-sessions', '-F', '#{session_name}').splitlines():
        tmux('set-environment', '-u', '-t', session, 'NO_COLOR')
        tmux('set-environment', '-t', session, 'COLORTERM', 'truecolor')
    # Global, so the per-client view sessions also turn swipes into scrolling.
    tmux('set-option', '-g', 'mouse', 'on')
    tmux('set-option', '-t', SESSION, 'mouse', 'on')
    tmux('set-option', '-t', SESSION, 'status', 'off')
    tmux('set-option', '-g', 'history-limit', '20000')
    tmux('set-option', '-gw', 'automatic-rename', 'off')
    tmux('set-option', '-gw', 'allow-rename', 'off')


def create_window(path, agent, args=(), cwd=None):
    path = save_project(path)
    agent_executable(agent)
    if agent in ('codex', 'claude'):
        ensure_router()
    label = {'codex': 'Codex', 'claude': 'Claude', 'shell': 'Terminal'}[agent]
    command = shlex.join([str(BASE / 'venv/bin/python'), str(BASE / 'launch_agent.py'), agent, *args])
    with (BASE / 'windows.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        exists = subprocess.run(['tmux', '-L', SOCKET, 'has-session', '-t', SESSION], capture_output=True).returncode == 0
        operation = ['new-window', '-d', '-t', SESSION] if exists else ['new-session', '-d', '-s', SESSION]
        window = tmux(*operation, '-P', '-F', '#{window_id}', '-n', label, '-c', cwd or path, command)
        tmux('set-option', '-w', '-t', window, '@project_path', path)
        tmux('set-option', '-w', '-t', window, '@agent', agent)
        configure_session()
    return window


def windows():
    raw = tmux('list-windows', '-t', SESSION, '-F', '#{window_id}\t#{window_name}\t#{@project_path}\t#{@agent}\t#{pane_current_path}\t#{pane_id}\t#{pane_pid}\t#{pane_dead}\t#{pane_dead_status}\t#{@mobile_exit_code}\t#{@mobile_exit_pid}\tEND', check=False)
    result = []
    for line in raw.splitlines():
        fields = line.split('\t')
        if len(fields) != 12:
            continue
        identity, name, path, agent, cwd, pane, pid, dead, dead_status, exit_code, exit_pid = fields[:-1]
        if not path:
            path = cwd
            tmux('set-option', '-w', '-t', identity, '@project_path', path)
        if not agent:
            agent = 'codex' if 'codex' in name.lower() else 'claude' if 'claude' in name.lower() else 'shell'
            tmux('set-option', '-w', '-t', identity, '@agent', agent)
        result.append({'id': identity, 'name': name, 'agent': agent, 'path': path,
                       'pane': pane, 'pid': int(pid or 0), 'dead': dead == '1',
                       'exit_code': exit_code or dead_status, 'exit_pid': int(exit_pid or 0)})
    return result


def state():
    running = windows()
    paths = list(dict.fromkeys([*load_projects(), *(w['path'] for w in running)]))
    return {'projects': [{'path': p, 'name': Path(p).name or p, 'windows': [w for w in running if w['path'] == p]} for p in paths if Path(p).is_dir()]}
