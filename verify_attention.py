"""Isolated process fixtures: no commands are sent to existing agent windows."""
import asyncio
import fcntl
import json
import os
from pathlib import Path
import shlex
import signal
import tempfile
import time
import unittest
from unittest.mock import patch

from attention import AttentionMonitor, agent_process, confirmation_visible
from mobile_core import BASE, create_window, tmux
from playwright.async_api import async_playwright

MENU = 'Would you like to run the following command?\n  1. Yes, proceed (y)\n  2. No, cancel (n)\nPress enter to confirm or esc to cancel'


class DetectionTests(unittest.TestCase):
    def test_confirmation_is_specific_to_visible_menu(self):
        self.assertTrue(confirmation_visible(MENU))
        self.assertTrue(confirmation_visible('Do you want to proceed?\n❯ 1. Yes\n  2. No\nEnter to select · Esc to cancel'))
        self.assertTrue(confirmation_visible('Do you want to make this edit to app.py?\n❯ 1. Yes\n  2. No\nEsc to cancel · Tab to amend'))
        self.assertFalse(confirmation_visible('Agent working silently for 20 minutes'))
        self.assertFalse(confirmation_visible('A paragraph discussing approval requested and errors.'))
        self.assertFalse(confirmation_visible(MENU + '\n' + '\n'.join(['Working...'] * 21)))
        self.assertFalse(confirmation_visible('Would you like to run the following command?\n1. Yes\n2. No'))

    def test_process_is_found_below_launcher(self):
        processes = {1: ('Ss', 'bash'), 2: ('S', 'python'), 3: ('Sl', 'codex'), 4: ('S', 'claude')}
        children = {1: [2], 2: [3]}
        self.assertEqual(agent_process(1, 'codex', processes, children), (3, 'Sl'))
        self.assertIsNone(agent_process(1, 'claude', processes, children))
        processes[3] = ('Z', 'codex')
        self.assertIsNone(agent_process(1, 'codex', processes, children))

    def test_reopened_agent_takes_precedence_over_stopped_job(self):
        for agent in ('claude', 'codex'):
            with self.subTest(agent=agent):
                processes = {1: ('Ss', 'bash'), 2: ('Tl', agent), 3: ('Sl+', agent)}
                children = {1: [2, 3]}
                self.assertEqual(agent_process(1, agent, processes, children), (3, 'Sl+'))
                processes[3] = ('Sl', agent)
                self.assertEqual(agent_process(1, agent, processes, children), (3, 'Sl'))
                processes[3] = ('Z', agent)
                self.assertEqual(agent_process(1, agent, processes, children), (2, 'Tl'))

    def test_foreground_agent_is_found_beyond_background_agent(self):
        processes = {1: ('Ss', 'bash'), 2: ('Sl', 'claude'),
                     3: ('S', 'bash'), 4: ('Sl+', 'claude')}
        children = {1: [2, 3], 3: [4]}
        self.assertEqual(agent_process(1, 'claude', processes, children), (4, 'Sl+'))

    def test_reopened_agent_clears_suspension_and_survives_monitor_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            window = dict(id='@fixture', pane='%fixture', pid=1, agent='claude',
                          name='Claude', path=directory, dead=False,
                          exit_code='0', exit_pid=2)
            processes = {1: ('Ss', 'bash'), 2: ('Tl', 'claude')}
            children = {1: [2]}
            with patch('attention.windows', return_value=[window]), \
                    patch('attention.process_tree', return_value=(processes, children)), \
                    patch('attention.tmux', return_value='Claude is idle'):
                monitor = AttentionMonitor(path)
                monitor.scan()
                self.assertEqual(monitor.snapshot()[0]['kind'], 'suspended')
                processes[3] = ('Sl+', 'claude')
                children[1].append(3)
                monitor.scan()
                self.assertEqual(monitor.snapshot(), [])
                self.assertEqual(monitor.entries['@fixture:%fixture']['agent_pid'], 3)
                restored = AttentionMonitor(path)
                restored.scan()
                self.assertEqual(restored.snapshot(), [])
                # The remaining old job is still reported if it is all that is left.
                del processes[3]
                restored.scan()
                self.assertEqual(restored.snapshot()[0]['kind'], 'suspended')

    def test_transition_deduplication_and_gateway_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            window = dict(id='@fixture', pane='%fixture', pid=1, agent='codex', name='Codex', path=directory, dead=False, exit_code='')
            with patch('attention.windows', return_value=[window]), patch('attention.process_tree', return_value=({1: ('Sl', 'codex')}, {})), patch('attention.tmux', return_value=MENU):
                monitor = AttentionMonitor(path)
                with patch('attention.time.time', return_value=100): monitor.scan()
                self.assertEqual(monitor.snapshot(), [])
                with patch('attention.time.time', return_value=103): monitor.scan()
                event = monitor.snapshot()[0]['id']
                with patch('attention.time.time', return_value=106): monitor.scan()
                self.assertEqual(monitor.snapshot()[0]['id'], event)
                restored = AttentionMonitor(path)
                with patch('attention.time.time', return_value=107): restored.scan()
                self.assertEqual(restored.snapshot()[0]['id'], event)
                with patch('attention.process_tree', return_value=({}, {})), patch('attention.time.time', return_value=110): monitor.scan()
                self.assertEqual(monitor.snapshot()[0]['kind'], 'exited')
                with patch('attention.time.time', return_value=113): monitor.scan()
                self.assertEqual(monitor.snapshot(), [])
                with patch('attention.time.time', return_value=116): monitor.scan()
                self.assertNotEqual(monitor.snapshot()[0]['id'], event)
                with patch('attention.windows', return_value=[]), patch('attention.time.time', return_value=118): monitor.scan()
                self.assertEqual(monitor.snapshot()[0]['kind'], 'closed')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


async def browser_test():
    credential = (BASE / 'credentials').read_text().strip().split(':', 1)
    with tempfile.TemporaryDirectory(prefix='terminal-alert-qa-') as directory:
        project = Path(directory)
        identities = []
        child_pid = None
        async with async_playwright() as p:
            browser = await p.chromium.launch(args=['--no-sandbox', '--ignore-certificate-errors'])
            context = await browser.new_context(viewport={'width':390,'height':844}, is_mobile=True, has_touch=True,
                http_credentials={'username':credential[0], 'password':credential[1]}, ignore_https_errors=True)
            page = await context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                # Only this shell receives fixture commands. prctl changes its child's
                # process name, without launching Codex or making any API requests.
                first = create_window(str(project), 'shell'); identities.append(first)
                second = create_window(str(project), 'shell'); identities.append(second)
                script = project / 'fixture.py'
                script.write_text('import ctypes,os,time\nctypes.CDLL(None).prctl(15,b"codex",0,0,0)\n'
                    + 'open(' + repr(str(project / 'pid')) + ',"w").write(str(os.getpid()))\n'
                    + 'print("\\033[2J\\033[H"+' + repr(MENU) + ',flush=True)\ntime.sleep(600)\n')
                tmux('send-keys', '-t', first, '-l', shlex.join([str(BASE / 'venv/bin/python'), str(script)]))
                tmux('send-keys', '-t', first, 'Enter')
                for _ in range(60):
                    if (project / 'pid').exists(): break
                    await asyncio.sleep(.1)
                child_pid = int((project / 'pid').read_text())
                tmux('set-option', '-w', '-t', first, '@agent', 'codex')
                tmux('rename-window', '-t', first, 'Codex')
                await page.goto('https://127.0.0.1:7682')
                await page.wait_for_function('terminalReady')
                await page.locator('#terminal').tap(position={'x':80, 'y':60})
                await page.wait_for_function('(id)=>alerts.some(a=>a.window===id&&a.kind==="attention")', arg=first, timeout=20000)
                # An alert from another project appears without stealing terminal focus.
                self_focused = await page.evaluate('document.activeElement===terminal.textarea')
                assert self_focused
                await page.locator('#attention-summary').click()
                row = page.locator('.attention-item').filter(has_text=project.name)
                await row.get_by_role('button', name='Abrir terminal').click()
                await page.wait_for_function('(id)=>terminalReady&&selectedWindow===id', arg=first)
                assert await page.locator('.tab.active .attention-dot').count() == 1
                await page.locator('#attention-summary').click()
                row = page.locator('.attention-item').filter(has_text=project.name)
                await row.get_by_role('button', name='Dispensar').click()
                await page.wait_for_timeout(6000)
                assert await page.locator('.attention-item').filter(has_text=project.name).count() == 0
                await page.reload()
                await page.wait_for_function('terminalReady')
                assert not await page.evaluate('(id)=>pendingAlerts().some(a=>a.window===id)', first)
                os.kill(child_pid, signal.SIGSTOP)
                await page.wait_for_function('(id)=>pendingAlerts().some(a=>a.window===id&&a.kind==="suspended")', arg=first, timeout=15000)
                os.kill(child_pid, signal.SIGCONT)
                await page.wait_for_function('(id)=>!alerts.some(a=>a.window===id&&a.kind==="suspended")', arg=first, timeout=15000)
                os.kill(child_pid, signal.SIGTERM)
                child_pid = None
                await page.wait_for_function('(id)=>alerts.some(a=>a.window===id&&a.kind==="exited")', arg=first, timeout=15000)
                # The shell and terminal connection remain alive after agent exit.
                assert await page.evaluate('terminalReady')
                for width, height in [(320,640),(390,420),(844,390)]:
                    await page.set_viewport_size({'width':width,'height':height})
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    assert (await page.locator('#terminal').bounding_box())['height'] > 100
                await page.set_viewport_size({'width':390,'height':844})
                await page.screenshot(path=str(BASE / 'mobile-alerts.png'))
                tmux('kill-window', '-t', first); identities.remove(first)
                await page.wait_for_function('(id)=>alerts.some(a=>a.window===id&&a.kind==="closed")', arg=first, timeout=15000)
                await page.wait_for_function("caches.keys().then(keys=>keys.includes('terminal-local-v4'))")
                assert not errors, errors
                print('OK: confirmação em outro projeto, foco, abrir aba, dispensar/recarregar, suspensão, retomada, saída com shell vivo, fechamento e PWA v4.')
            finally:
                if child_pid:
                    os.kill(child_pid, signal.SIGCONT)
                    os.kill(child_pid, signal.SIGTERM)
                await context.close()
                await browser.close()
                for identity in identities:
                    tmux('kill-window', '-t', identity, check=False)
                with (BASE / 'projects.lock').open('w') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    saved = BASE / 'projects.json'
                    saved.write_text(json.dumps([path for path in json.loads(saved.read_text()) if path != str(project)]))


if __name__ == '__main__':
    result = unittest.main(exit=False).result
    if not result.wasSuccessful():
        raise SystemExit(1)
    asyncio.run(browser_test())
