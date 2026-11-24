"""Start the local 9router and wait for HTTP readiness before opening agents."""
import fcntl
from http.client import HTTPException
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler

BASE = Path(__file__).resolve().parent
PORT = 20128


class RouterUnavailable(Exception):
    pass


def router_ready():
    try:
        # The router is local even when the calling shell exports an HTTP proxy.
        with build_opener(ProxyHandler({})).open(f'http://127.0.0.1:{PORT}/api/health', timeout=1) as response:
            return response.status == 200 and json.loads(response.read(4096)).get('ok') is True
    except (OSError, HTTPException, ValueError, AttributeError):
        return False


def port_open():
    try:
        with socket.create_connection(('127.0.0.1', PORT), timeout=.2):
            return True
    except OSError:
        return False


def start_router():
    candidates = []
    found = shutil.which('9router')
    if found:
        candidates.append(Path(found))
    candidates.extend(sorted((Path.home() / '.nvm/versions/node').glob('*/bin/9router'), reverse=True))
    for executable in candidates:
        package = executable.resolve().parent
        node = executable.parent / 'node'
        server = package / 'app/custom-server.js'
        if not server.is_file():
            server = package / 'app/server.js'
        if not server.is_file() or not node.is_file():
            continue
        # This repair lives outside npm and validates the installed structure,
        # rather than relying on the version-specific chunk names.
        autopatch = BASE / 'patches/9router-autoping-persistent-20261026/apply.py'
        if autopatch.is_file():
            try:
                subprocess.run([sys.executable, str(autopatch), '--app', str(server.parent)],
                               check=True, capture_output=True, timeout=20)
            except (OSError, subprocess.SubprocessError):
                print('Auto-ping repair needs compatibility review; see terminal-mobile-autoping.service.', file=sys.stderr)
        # npm upgrades replace compiled bundles. Reapply only to the validated
        # build; other versions start normally and report the need for review.
        patch = BASE / 'patches/9router-claude-usage-20261025/apply.py'
        if patch.is_file():
            try:
                version = json.loads((package / 'package.json').read_text()).get('version')
                if version == '0.5.104':
                    subprocess.run([sys.executable, str(patch), '--app', str(server.parent)],
                                   check=True, capture_output=True, timeout=15)
                else:
                    print(f'Claude usage patch: 9router {version} needs compatibility review.', file=sys.stderr)
            except (OSError, ValueError, subprocess.SubprocessError):
                print('Claude usage patch could not be applied; starting the installed 9router normally.', file=sys.stderr)
        environment = dict(os.environ)
        environment['PORT'] = str(PORT)
        environment['HOSTNAME'] = '127.0.0.1'
        environment['TERMINAL_MOBILE_ROUTER_BOOTSTRAP'] = '1'
        data = Path(environment.get('DATA_DIR', str(Path.home() / '.9router')))
        environment['NODE_PATH'] = os.pathsep.join(filter(None, [str(data / 'runtime/node_modules'), str(package / 'app/node_modules'), environment.get('NODE_PATH')]))
        # The CLI launcher kills existing router processes on startup. Start its
        # bundled server directly so another session's connection is preserved.
        descriptor = os.open(BASE / '9router.log', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, 'ab') as output:
            return subprocess.Popen([str(node), '--dns-result-order=ipv4first', '--max-old-space-size=6144',
                                     '--require', str(BASE / 'router_autoping.cjs'), str(server)],
                                    cwd=server.parent, env=environment, stdin=subprocess.DEVNULL,
                                    stdout=output, stderr=output, start_new_session=True)
    raise RouterUnavailable('9router não está instalado. Instale-o antes de abrir Codex ou Claude.')


def ensure_router(timeout=30):
    if router_ready():
        return
    # Web requests, desktop shells and boot can all open agents concurrently.
    with (BASE / '9router.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if router_ready():
            return
        process = None
        ready = False
        try:
            if not port_open():
                process = start_router()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if router_ready():
                    ready = True
                    return
                if process is not None and process.poll() is not None:
                    break
                time.sleep(.2)
        except OSError as error:
            raise RouterUnavailable('Não foi possível iniciar o 9router. Verifique 9router.log.') from error
        finally:
            # Reap failed startups; a timeout must not leave a half-started copy.
            if process is not None and not ready:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                else:
                    process.wait()
        raise RouterUnavailable('O 9router não respondeu. Codex e Claude aguardam a conexão dele. Verifique 9router.log e tente novamente.')
