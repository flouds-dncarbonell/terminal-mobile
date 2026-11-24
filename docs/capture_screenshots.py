"""Capture the real UI with fictional data, without reading local accounts or agents.

Run: venv/bin/python docs/capture_screenshots.py
Requires requirements-dev.txt and `playwright install chromium`.
"""
import asyncio
from pathlib import Path

from aiohttp import web
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/screenshots'
PROJECT = '/workspace/terminal-mobile'
STAMP = '2026-11-24T12:00:00Z'
MARKDOWN = '''# Seu terminal, no celular

Continue o trabalho de qualquer lugar da sua rede.

## Tudo na mesma interface

- **Codex e Claude Code** em abas independentes
- Sessões persistentes com **tmux**
- Anexos, upload e download de arquivos
- Prévia de Markdown, HTML e mídia
- Quotas e notificações dos agentes

## Comece pelo projeto

Escolha uma pasta, abra um terminal e continue de onde parou.

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.lock.txt
./serve.sh
```

> Demonstração com dados fictícios.
'''
TERMINAL = '\r\n'.join([
    '\x1b[1;38;5;179m>_ Codex\x1b[0m',
    '\x1b[2m  /workspace/terminal-mobile\x1b[0m', '',
    '\x1b[1m› Prepare o projeto para publicar.\x1b[0m',
    '  Inclua requisitos e créditos.', '',
    '\x1b[38;5;150m• Projeto pronto para compartilhar.\x1b[0m', '',
    '  Revisei a instalação e organizei',
    '  a documentação para quem quiser',
    '  reproduzir o ambiente.', '',
    '\x1b[1m  Arquivos preparados\x1b[0m',
    '  \x1b[38;5;150m+\x1b[0m README.md',
    '  \x1b[38;5;150m+\x1b[0m requirements.lock.txt',
    '  \x1b[38;5;150m+\x1b[0m .env.example',
    '  \x1b[38;5;150m+\x1b[0m THIRD_PARTY_NOTICES.md', '',
    '\x1b[1m  Validação\x1b[0m',
    '  \x1b[38;5;150m✓\x1b[0m Testes isolados passaram',
    '  \x1b[38;5;150m✓\x1b[0m Credenciais fora do Git',
    '  \x1b[38;5;150m✓\x1b[0m Créditos incluídos', '',
    '\x1b[2m  Conteúdo de demonstração.\x1b[0m', '',
    '\x1b[1m›\x1b[0m ',
])


def account(identity, provider, name, priority, session, weekly):
    return dict(id=identity, providerId=provider, provider='Claude' if provider == 'claude' else 'Codex',
                name=name, priority=priority, strategy='priority', active=True, plan='Demonstração', error=None,
                quotas=[dict(name=label, remainingPercent=percent, resetAt=None, unlimited=False,
                             neverExpires=False, recurring=True) for label, percent in
                        [('Sessão · 5 horas', session), ('Semana · 7 dias', weekly)]])


async def api(request):
    if request.path == '/api/state':
        return web.json_response(dict(projects=[dict(path=PROJECT, name='terminal-mobile', windows=[
            dict(id='@1', name='Codex', agent='codex', path=PROJECT),
            dict(id='@2', name='Claude', agent='claude', path=PROJECT),
            dict(id='@3', name='Terminal', agent='shell', path=PROJECT)])], alerts=[]))
    if request.path == '/api/quotas':
        return web.json_response(dict(updatedAt=STAMP, accounts=[
            account('demo-codex-1', 'codex', 'Principal', 1, 86, 72),
            account('demo-codex-2', 'codex', 'Alternativa', 2, 54, 91),
            account('demo-claude-1', 'claude', 'Desenvolvimento', 1, 68, 83)]))
    if request.path == '/api/files':
        entries = [dict(name=name, path=name, directory=directory, size=None if directory else 2048)
                   for name, directory in [('docs', True), ('web', True), ('README.md', False),
                                           ('mobile_server.py', False), ('requirements.txt', False)]]
        return web.json_response(dict(project=PROJECT, name='terminal-mobile', token='demo', path='.',
                                      parent=None, entries=entries, truncated=False, uploadLimit=104857600))
    if request.path == '/api/files/read':
        return web.json_response(dict(path='README.md', name='README.md', content=MARKDOWN,
                                      kind='markdown', size=len(MARKDOWN.encode()), token='demo'))
    if request.path == '/api/config':
        return web.json_response(dict(ip='127.0.0.1', tls_port=7682))
    return web.json_response({})


async def websocket(request):
    socket = web.WebSocketResponse()
    await socket.prepare(request)
    await socket.receive()
    await socket.send_bytes(b'0' + TERMINAL.encode())
    async for _ in socket:
        pass
    return socket


async def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    app = web.Application()
    app.router.add_get('/terminal/ws', websocket)
    app.router.add_get('/api/{path:.*}', api)
    app.router.add_get('/', lambda _: web.FileResponse(ROOT / 'web/index.html'))
    app.router.add_get('/manifest.webmanifest', lambda _: web.FileResponse(ROOT / 'web/manifest.webmanifest'))
    app.router.add_static('/assets/', ROOT / 'web')
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(args=['--no-sandbox'])
            context = await browser.new_context(viewport=dict(width=430, height=900),
                                                device_scale_factor=2, is_mobile=True, has_touch=True,
                                                locale='pt-BR', timezone_id='UTC', service_workers='block')
            await context.add_init_script("if (window === window.top) localStorage.setItem('terminalFontSize', '13')")
            page = await context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(f'http://127.0.0.1:{port}/')
            await page.wait_for_function('terminalReady')
            await page.evaluate('document.fonts.ready')
            await page.evaluate('''async () => {
                terminal.options.fontSize = 13;
                terminal.options.cursorBlink = false;
                fitTerminal();
                await new Promise(resolve => terminal.write('\\x1b[?25l', resolve));
            }''')
            await page.screenshot(path=OUTPUT / 'terminal-mobile.png', animations='disabled')
            await page.get_by_role('button', name='Quotas', exact=True).click()
            await page.wait_for_function('quotaSnapshot !== null && !quotaBusy')
            await page.screenshot(path=OUTPUT / 'quotas-mobile.png', animations='disabled')
            await page.locator('.tab-list .tab').first.click()
            await page.get_by_role('button', name='Arquivos do projeto', exact=True).click()
            await page.locator('.file-row').filter(has_text='README.md').click()
            await page.locator('#file-markdown h1').wait_for()
            await page.screenshot(path=OUTPUT / 'files-mobile.png', animations='disabled')
            assert not errors, errors
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await browser.close()
            print('Captured terminal, quotas and files from the real UI using fictional fixtures.')
    finally:
        await runner.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
