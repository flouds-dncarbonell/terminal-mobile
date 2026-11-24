"""Browser and native composer checks in explicitly supplied disposable agent tabs."""
import asyncio
import base64
import json
import os
import re
from pathlib import Path

from playwright.async_api import async_playwright, expect
from mobile_core import BASE, tmux

URL = os.environ.get('TERMINAL_ATTACHMENTS_TEST_URL', 'http://127.0.0.1:17781/')
FIXTURE = Path(os.environ.get('TERMINAL_ATTACHMENTS_FIXTURE', '/tmp/terminal-attachment-qa'))


async def main():
    tabs = json.loads((FIXTURE / 'windows.json').read_text())
    assert all('anexos-QA' in tmux('display-message', '-p', '-t', tab['id'], '#{window_name}') for tab in tabs)
    user, password = (BASE / 'credentials').read_text().strip().split(':', 1)
    png = (FIXTURE / 'test.png').read_bytes()
    uploaded = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True,
            http_credentials={'username': user, 'password': password}, permissions=['clipboard-read', 'clipboard-write'])
        await context.add_init_script('if (window === window.top) localStorage.setItem("project", ' + json.dumps(str(FIXTURE)) + ')')
        page = await context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        async def track(response):
            if response.request.method == 'POST' and response.url.endswith('/attachments') and response.ok:
                uploaded.extend(file['path'] for file in (await response.json())['files'])
        page.on('response', track)
        try:
            await page.goto(URL)
            await page.wait_for_function('terminalReady && currentProject()')
            for tab in tabs:
                await page.evaluate('(id) => selectWindow(id)', tab['id'])
                await page.wait_for_function('(id) => selectedWindow === id && terminalReady && !opening', arg=tab['id'])
                await expect(page.locator('#attachment-toggle')).to_be_enabled()
                tmux('send-keys', '-t', tab['id'], '-l', 'Analise estas imagens ')
                await page.locator('#attachment-toggle').click()
                await expect(page.locator('#attachment-target')).to_contain_text(tab['agent'])
                assert await page.evaluate('terminal.options.disableStdin')
                await page.locator('#attachment-input').set_input_files([
                    {'name': 'foto com espaço.png', 'mimeType': 'image/png', 'buffer': png},
                    {'name': 'segunda.png', 'mimeType': 'image/png', 'buffer': png},
                    {'name': 'anotações.txt', 'mimeType': 'text/plain', 'buffer': b'Anexo de teste.'}])
                await expect(page.locator('.attachment-row')).to_have_count(3)
                await expect(page.locator('.attachment-row img')).to_have_count(2)
                for width in (320, 390, 1280):
                    await page.set_viewport_size({'width': width, 'height': 844})
                    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    assert await page.locator('#attachment-dialog').evaluate('(d) => d.scrollWidth <= d.clientWidth')
                await page.set_viewport_size({'width': 390, 'height': 844})
                await page.screenshot(path=str(BASE / f'attachments-{tab["agent"]}-mobile.png'))
                await page.locator('#attachment-insert').click()
                await expect(page.locator('#attachment-dialog')).not_to_be_visible()
                await page.wait_for_function('!terminal.options.disableStdin')
                await page.wait_for_timeout(200)
                capture = tmux('capture-pane', '-p', '-t', tab['id'])
                images = re.findall(r'\[Image #(\d+)\]', capture)
                assert len(images) >= 2 and int(images[-1]) == int(images[-2]) + 1, capture
                assert 'Analise estas imagens' in capture, capture
                assert '03-anotacoes.txt' in ''.join(capture.split()), capture
                tmux('send-keys', '-t', tab['id'], 'C-u')

            # Actual browser Clipboard API, rather than a server clipboard.
            await page.locator('#attachment-toggle').click()
            await page.evaluate('''async (png) => {
              const blob = await (await fetch('data:image/png;base64,' + png)).blob();
              await navigator.clipboard.write([new ClipboardItem({'image/png': blob})]);
            }''', base64.b64encode(png).decode())
            await page.locator('#attachment-paste').click()
            await expect(page.locator('.attachment-row')).to_have_count(1)
            await page.locator('.attachment-row button').click()
            await expect(page.locator('.attachment-row')).to_have_count(0)
            await expect(page.locator('#attachment-insert')).to_be_disabled()

            # A denied read still offers a native paste target and the file picker.
            await page.evaluate('() => { navigator.clipboard.read = async () => { throw new DOMException("Denied", "NotAllowedError"); }; }')
            await page.locator('#attachment-paste').click()
            await expect(page.locator('#attachment-clipboard')).to_be_visible()
            await expect(page.locator('#attachment-status')).to_contain_text('não liberou')
            await page.get_by_role('button', name='Fechar anexos', exact=True).click()

            # Native paste event over xterm is intercepted before xterm drops its image.
            await page.evaluate('''(png) => {
              const data = Uint8Array.from(atob(png), c => c.charCodeAt(0));
              const transfer = new DataTransfer();
              transfer.items.add(new File([data], 'imagem-colada.png', {type:'image/png'}));
              terminal.textarea.dispatchEvent(new ClipboardEvent('paste', {clipboardData: transfer, bubbles:true, cancelable:true}));
            }''', base64.b64encode(png).decode())
            await expect(page.locator('#attachment-dialog')).to_be_visible()
            await expect(page.locator('.attachment-row')).to_have_count(1)

            async def fail(route):
                await route.fulfill(status=503, json={'error': 'Falha de envio no teste.'})
            await page.route('**/api/windows/*/attachments', fail)
            await page.locator('#attachment-insert').click()
            await expect(page.locator('#attachment-status')).to_contain_text('Falha de envio')
            await expect(page.locator('.attachment-row')).to_have_count(1)
            await expect(page.locator('#attachment-insert')).to_be_enabled()
            await page.unroute('**/api/windows/*/attachments', fail)
            await page.locator('#attachment-insert').click()
            await expect(page.locator('#attachment-dialog')).not_to_be_visible()
            assert re.search(r'\[Image #\d+\]', tmux('capture-pane', '-p', '-t', tabs[-1]['id']))
            tmux('send-keys', '-t', tabs[-1]['id'], 'C-u')

            # Normal text paste remains the terminal's responsibility.
            await page.evaluate('''() => {
              const transfer = new DataTransfer();
              transfer.setData('text/plain', 'TEXTO_COLADO_QA');
              terminal.textarea.dispatchEvent(new ClipboardEvent('paste', {clipboardData: transfer, bubbles:true, cancelable:true}));
            }''')
            await page.wait_for_timeout(300)
            assert not await page.locator('#attachment-dialog').is_visible()
            assert 'TEXTO_COLADO_QA' in tmux('capture-pane', '-p', '-t', tabs[-1]['id'])
            tmux('send-keys', '-t', tabs[-1]['id'], 'C-u')
            await page.wait_for_timeout(300)

            # A transport change after upload must not insert into a new connection;
            # retry reuses the saved files and adds the image exactly once.
            images_before = len(re.findall(r'\[Image #\d+\]', tmux('capture-pane', '-p', '-t', tabs[-1]['id'])))
            await page.locator('#attachment-toggle').click()
            await page.locator('#attachment-input').set_input_files({'name': 'reconexao.png', 'mimeType': 'image/png', 'buffer': png})
            posts = []
            async def disconnect(route):
                posts.append(route.request.url)
                await page.evaluate('socket.close()')
                await route.continue_()
            await page.route('**/api/windows/*/attachments', disconnect)
            await page.locator('#attachment-insert').click()
            await expect(page.locator('#attachment-status')).to_contain_text('conexão mudou')
            await page.unroute('**/api/windows/*/attachments', disconnect)
            await page.wait_for_function('terminalReady && !opening')
            await page.locator('#attachment-insert').click()
            await expect(page.locator('#attachment-dialog')).not_to_be_visible()
            capture = tmux('capture-pane', '-p', '-t', tabs[-1]['id'])
            assert len(re.findall(r'\[Image #\d+\]', capture)) == images_before + 1, capture
            assert len(posts) == 1
            tmux('send-keys', '-t', tabs[-1]['id'], 'C-u')
            assert not errors, errors
            print('OK: Codex e Claude reconhecem duas imagens nativas, preservam rascunho e documento; Clipboard API; colar no terminal; fallback; erro/retry e reconexão sem duplicar; 320/390/1280 px.')
        finally:
            await context.close()
            await browser.close()
            for path in uploaded:
                item = Path(path)
                item.unlink(missing_ok=True)
                try:
                    item.parent.rmdir()
                except OSError:
                    pass


if __name__ == '__main__':
    asyncio.run(main())
