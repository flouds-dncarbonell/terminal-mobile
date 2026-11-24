"""Verify clean agent environments and rich output through tmux, ttyd and xterm."""
import asyncio
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import tempfile

from playwright.async_api import async_playwright
from mobile_core import BASE, create_window, managed_environment, tmux, windows


async def main():
    source = {'NO_COLOR': '1', 'TERM': 'tmux-256color', 'PATH': '/bin'}
    clean = managed_environment(source)
    assert 'NO_COLOR' not in clean and clean['COLORTERM'] == 'truecolor'
    assert source['NO_COLOR'] == '1'  # Never mutate the caller's environment.
    original = {window['id']: window['pid'] for window in windows()}
    credentials = (BASE / 'credentials').read_text().strip().split(':', 1)
    identities = []
    with tempfile.TemporaryDirectory(prefix='terminal-colors-qa-') as directory:
        project = Path(directory)
        async with async_playwright() as p:
            browser = await p.chromium.launch(args=['--no-sandbox', '--ignore-certificate-errors'])
            context = await browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,
                http_credentials={'username':credentials[0],'password':credentials[1]},ignore_https_errors=True)
            page = await context.new_page()
            try:
                shell = create_window(directory, 'shell'); identities.append(shell)
                for _ in range(60):
                    window = next(window for window in windows() if window['id'] == shell)
                    raw = Path(f"/proc/{window['pid']}/environ").read_bytes().split(b'\0')
                    environment = dict(item.split(b'=',1) for item in raw if b'=' in item)
                    if environment.get(b'TERMINAL_MOBILE_MANAGED') == b'1': break
                    await asyncio.sleep(.1)
                assert b'NO_COLOR' not in environment
                assert environment[b'TERM'] == b'tmux-256color'
                assert environment[b'COLORTERM'] == b'truecolor'
                await page.goto('https://127.0.0.1:7682')
                await page.wait_for_function('terminalReady')
                await page.get_by_role('button', name='Trocar de projeto').click()
                await page.locator('.project-row').filter(has_text=project.name).click()
                await page.wait_for_function('(id)=>terminalReady&&selectedWindow===id', arg=shell)
                probe = project / 'probe.py'
                probe.write_text('import os,json,subprocess\n'
                    + 'open(' + repr(str(project / 'report.json')) + ',"w").write(json.dumps(dict(no_color="NO_COLOR" in os.environ,term=os.environ.get("TERM"),colorterm=os.environ.get("COLORTERM"),tty=os.isatty(1),colors=subprocess.check_output(["tput","colors"],text=True).strip())))\n'
                    + 'print("\\033[38;2;17;123;231mTRUECOLOR\\033[0m \\033[1mBOLD\\033[0m \\033[3mITALIC\\033[0m \\033[4mUNDERLINE\\033[0m \\033[31mANSI_RED\\033[0m")\n')
                tmux('send-keys', '-t', shell, '-l', shlex.join([str(BASE / 'venv/bin/python'), str(probe)]))
                tmux('send-keys', '-t', shell, 'Enter')
                await page.wait_for_function("Array.from({length:terminal.buffer.active.length},(_,i)=>terminal.buffer.active.getLine(i)).some(line=>line?.translateToString().startsWith('TRUECOLOR'))")
                report = json.loads((project / 'report.json').read_text())
                assert report == dict(no_color=False,term='tmux-256color',colorterm='truecolor',tty=True,colors='256'), report
                attributes = await page.evaluate('''() => {
                    const line = Array.from({length:terminal.buffer.active.length},(_,i)=>terminal.buffer.active.getLine(i)).find(line=>line?.translateToString().startsWith('TRUECOLOR'));
                    const text = line.translateToString();
                    return {rgb:line.getCell(0).isFgRGB(),color:line.getCell(0).getFgColor(),bold:!!line.getCell(text.indexOf('BOLD')).isBold(),italic:!!line.getCell(text.indexOf('ITALIC')).isItalic(),underline:!!line.getCell(text.indexOf('UNDERLINE')).isUnderline()};
                }''')
                assert attributes == dict(rgb=True,color=0x117be7,bold=True,italic=True,underline=True), attributes
                await page.screenshot(path=str(BASE / 'mobile-colors.png'))
                print('OK: shell TTY sem NO_COLOR, TERM/COLORTERM corretos, 256 cores, RGB exato, negrito, itálico e sublinhado no celular.')
                # Real CLI help is safe: no conversation or model request is started.
                for agent in ('codex','claude'):
                    identity = create_window(directory, agent, args=['--help']); identities.append(identity)
                    for _ in range(200):
                        if tmux('show-options','-w','-t',identity,'-v','@mobile_exit_code',check=False) == '0': break
                        await asyncio.sleep(.1)
                    else: raise AssertionError(agent + ' --help did not exit normally')
                    capture = tmux('capture-pane','-p','-e','-S','-2000','-t',identity)
                    plain = re.sub(r'\x1b\[[0-9;]*m', '', capture)
                    assert 'Usage:' in plain or 'Options:' in plain, agent + ' help output missing'
                    if agent == 'codex':
                        assert any('\x1b[' in line and ('Usage:' in line or 'Options:' in line) for line in capture.splitlines()), 'Codex help headers lost styling'
                print('OK: cabeçalhos do Codex com estilos, ajuda real de ambos os CLIs e sessões anteriores preservadas. A ajuda do Claude é monocromática por padrão.')
                current = {window['id']: window['pid'] for window in windows()}
                assert all(current.get(identity) == pid for identity,pid in original.items())
            finally:
                await context.close(); await browser.close()
                for identity in identities: tmux('kill-window','-t',identity,check=False)
                with (BASE / 'projects.lock').open('w') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX)
                    path = BASE / 'projects.json'
                    path.write_text(json.dumps([value for value in json.loads(path.read_text()) if value != directory]))


if __name__ == '__main__':
    asyncio.run(main())
