import os
from pathlib import Path
import shlex
import sys
from mobile_core import agent_executable, managed_environment
from router_dependency import ensure_router, RouterUnavailable

agent = sys.argv[1]
executable = agent_executable(agent)
if agent in ('codex', 'claude'):
    try:
        ensure_router()
    except RouterUnavailable as error:
        sys.exit(str(error))
environment = managed_environment()
environment['TERMINAL_MOBILE_MANAGED'] = '1'
if agent == 'codex':
    environment['PATH'] = str(Path(executable).parent) + os.pathsep + environment.get('PATH', '')
if agent == 'shell':
    os.execve(executable, [executable, '--noprofile', '--rcfile', str(Path(__file__).parent / 'managed-shell.bash'), '-i'], environment)
# The agent runs as a job of an interactive shell so Ctrl+Z can suspend it.
# agent-shell.bash records its exit code and keeps the shell open afterwards.
arguments = sys.argv[2:]
if agent == 'codex' and '--no-alt-screen' not in arguments:
    # Inline mode keeps the conversation in tmux history, so it can be scrolled.
    arguments = ['--no-alt-screen', *arguments]
environment['TERMINAL_MOBILE_AGENT'] = shlex.join([executable, *arguments])
os.execve('/bin/bash', ['bash', '--noprofile', '--rcfile', str(Path(__file__).parent / 'agent-shell.bash'), '-i'], environment)
