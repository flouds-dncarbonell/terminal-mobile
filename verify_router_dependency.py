"""Dependency checks use isolated HTTP fixtures; existing agents stay untouched."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from aiohttp import BasicAuth, web
from aiohttp.test_utils import TestClient, TestServer
import mobile_core
from mobile_server import authenticated, new_window
import router_dependency as router


class DependencyTests(unittest.TestCase):
    def test_running_router_is_reused(self):
        with patch.object(router, 'router_ready', return_value=True), patch.object(router, 'start_router') as start:
            router.ensure_router()
            start.assert_not_called()

    def test_failure_prevents_agent_window(self):
        for agent in ('codex', 'claude'):
            with self.subTest(agent=agent), patch.object(mobile_core, 'save_project', return_value='/tmp'), patch.object(mobile_core, 'agent_executable'), patch.object(mobile_core, 'ensure_router', side_effect=router.RouterUnavailable('9router indisponível')), patch.object(mobile_core, 'tmux') as tmux:
                with self.assertRaises(router.RouterUnavailable):
                    mobile_core.create_window('/tmp', agent)
                tmux.assert_not_called()

    def test_shell_does_not_depend_on_router(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(mobile_core, 'BASE', Path(directory)), patch.object(mobile_core, 'save_project', return_value='/tmp'), patch.object(mobile_core, 'ensure_router') as ensure, patch.object(mobile_core, 'tmux', return_value='@fixture'), patch.object(mobile_core, 'configure_session'):
            self.assertEqual(mobile_core.create_window('/tmp', 'shell'), '@fixture')
            ensure.assert_not_called()

    def test_parallel_launches_wait_for_one_server(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        # A delayed fixture verifies actual HTTP readiness and cross-thread locking.
        script = '''import time,sys
from http.server import BaseHTTPRequestHandler,HTTPServer
time.sleep(.4)
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(b'{"ok":true}')
 def log_message(self,*args):pass
HTTPServer(('127.0.0.1',int(sys.argv[1])),Handler).serve_forever()
'''
        processes = []
        def start():
            process = subprocess.Popen([sys.executable, '-c', script, str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(process)
            return process
        try:
            with tempfile.TemporaryDirectory() as directory, patch.object(router, 'BASE', Path(directory)), patch.object(router, 'PORT', port), patch.object(router, 'start_router', side_effect=start) as launch:
                with ThreadPoolExecutor(max_workers=4) as executor:
                    list(executor.map(lambda _: router.ensure_router(timeout=5), range(4)))
                self.assertTrue(router.router_ready())
                self.assertEqual(launch.call_count, 1)
        finally:
            for process in processes:
                process.terminate(); process.wait(timeout=5)

    def test_http_response_must_confirm_health(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200); self.end_headers()
                self.wfile.write(b'{"ok":false}')
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory, patch.object(router, 'BASE', Path(directory)), patch.object(router, 'PORT', server.server_port), patch.object(router, 'start_router') as start:
                self.assertFalse(router.router_ready())
                with self.assertRaises(router.RouterUnavailable):
                    router.ensure_router(timeout=.1)
                start.assert_not_called()
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_timeout_stops_only_our_failed_startup(self):
        process = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(60)'])
        try:
            with tempfile.TemporaryDirectory() as directory, patch.object(router, 'BASE', Path(directory)), patch.object(router, 'router_ready', return_value=False), patch.object(router, 'port_open', return_value=False), patch.object(router, 'start_router', return_value=process):
                with self.assertRaises(router.RouterUnavailable):
                    router.ensure_router(timeout=.1)
                self.assertIsNotNone(process.poll())
        finally:
            if process.poll() is None: process.kill()
            process.wait()


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_unavailable_dependency_returns_actionable_503(self):
        app = web.Application(middlewares=[authenticated])
        app['credential'] = 'fixture:fixture'
        app.router.add_post('/api/windows', new_window)
        async with TestClient(TestServer(app)) as client:
            with patch.object(mobile_core, 'save_project', return_value='/tmp'), patch.object(mobile_core, 'agent_executable'), patch.object(mobile_core, 'ensure_router', side_effect=router.RouterUnavailable('9router indisponível')), patch.object(mobile_core, 'tmux') as tmux:
                response = await client.post('/api/windows', json={'path':'/tmp', 'agent':'codex'}, auth=BasicAuth('fixture', 'fixture'), headers={'Origin':str(client.make_url('/')).rstrip('/')})
                self.assertEqual(response.status, 503)
                self.assertIn('9router', (await response.json())['error'])
                tmux.assert_not_called()


if __name__ == '__main__':
    unittest.main()
