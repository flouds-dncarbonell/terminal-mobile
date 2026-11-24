import os
import subprocess
import sys
from mobile_core import BASE, SESSION, SOCKET, agent_executable, create_window, managed_environment
from router_dependency import ensure_router, RouterUnavailable

agent, *arguments = sys.argv[1:]
executable = agent_executable(agent)
management = {'exec', 'e', 'login', 'logout', 'mcp', 'mcp-server', 'app-server', 'completion', 'features', 'debug', 'cloud', 'apply', 'help', 'install', 'update', 'doctor', 'auth', 'plugin', 'plugins', 'setup-token'}
passthrough = {'--help', '-h', '--version', '-V', '--print', '-p'}
inside = os.environ.get('TERMINAL_MOBILE_MANAGED') == '1' or 'terminal-mobile-test' in os.environ.get('TMUX', '')
interactive = sys.stdin.isatty() and not any(arg in passthrough for arg in arguments) and not (arguments and arguments[0] in management)
if inside and interactive and agent in ('codex', 'claude'):
    try:
        ensure_router()
    except RouterUnavailable as error:
        sys.exit(str(error))
if inside or not sys.stdin.isatty() or any(arg in passthrough for arg in arguments) or (arguments and arguments[0] in management):
    os.execve(executable, [executable, *arguments], managed_environment() if inside else os.environ)
cwd = os.getcwd()
git = subprocess.run(['git', '-C', cwd, 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
project = git.stdout.strip() if git.returncode == 0 else cwd
try:
    window = create_window(project, agent, arguments, cwd=cwd)
except RouterUnavailable as error:
    sys.exit(str(error))
print('Sessão disponível também no painel do celular. Para sair sem encerrar: Ctrl+B, depois D.', flush=True)
os.execv('/bin/bash', ['bash', str(BASE / 'attach.sh'), window])
