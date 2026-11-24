"""Browser checks with temporary real files; existing projects and terminals stay intact."""
import asyncio
import os
from pathlib import Path
import tempfile

from playwright.async_api import async_playwright, expect
from mobile_core import BASE, DEFAULT_PROJECT

URL = os.environ.get('TERMINAL_FILES_TEST_URL', 'http://127.0.0.1:17781/')


async def main():
    username, password = (BASE / 'credentials').read_text().strip().split(':', 1)
    with tempfile.TemporaryDirectory(prefix='terminal-files-qa-', dir=DEFAULT_PROJECT) as temporary:
        fixture = Path(temporary)
        (fixture / 'docs').mkdir()
        (fixture / 'docs' / 'other.md').write_text('# Outro documento\n\nOlá do projeto.')
        (fixture / 'README.md').write_text('# Olá, projeto\n\n**Texto formatado**\n\n| A | B |\n|---|---|\n| um | dois |\n\n[Outro arquivo](docs/other.md)\n\n![Ícone](icon.svg)\n\n<script>window.markdownUnsafe=true</script>\n<img src=x onerror="window.markdownUnsafe=true">\n')
        (fixture / 'index.html').write_text('<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="style.css"></head><body><h1>Prévia do projeto</h1><img src="icon.svg"><script>window.previewUnsafe=true;try { parent.previewUnsafe=true; } catch { window.parentBlocked=true; }</script></body></html>')
        (fixture / 'style.css').write_text('h1 { color: rgb(12, 123, 45); }')
        (fixture / 'icon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><rect width="24" height="24" fill="green"/></svg>')
        (fixture / 'binary.bin').write_bytes(b'\0\x01\x02')
        (fixture / '.hidden.md').write_text('# Oculto')
        longname = 'arquivo-com-nome-muito-longo-' * 5 + '.md'
        (fixture / longname).write_text('# Longo')
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
            context = await browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True,
                http_credentials={'username': username, 'password': password})
            await context.add_init_script('if (window === window.top) localStorage.setItem("project", ' + repr(str(DEFAULT_PROJECT)) + ')')
            page = await context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(URL)
            await page.wait_for_function('currentProject() && terminalReady')
            generation = await page.evaluate('terminalGeneration')
            await page.get_by_role('button', name='Arquivos do projeto', exact=True).click()
            await expect(page.locator('#files-path')).to_have_text(DEFAULT_PROJECT.name)
            await page.locator('#files-filter').fill(fixture.name)
            await page.locator('.file-row').filter(has_text=fixture.name).click()
            await page.locator('.file-row').filter(has_text='README.md').click()
            await page.locator('#file-markdown h1').wait_for()
            assert await page.locator('#file-markdown h1').inner_text() == 'Olá, projeto'
            assert await page.locator('#file-markdown table').count() == 1
            assert await page.locator('#file-markdown script, #file-markdown [onerror]').count() == 0
            assert not await page.evaluate('Boolean(window.markdownUnsafe)')
            await page.wait_for_function('document.querySelector("#file-markdown img").naturalWidth === 24')
            await page.screenshot(path=str(BASE / 'files-mobile.png'))
            await page.locator('#file-mode').click()
            assert '# Olá, projeto' in await page.locator('#file-source').inner_text()
            await page.locator('#file-mode').click()
            await page.locator('#file-markdown a').click()
            await page.wait_for_function('document.querySelector("#file-markdown h1")?.textContent === "Outro documento"')
            await page.locator('#file-back').click()
            await page.locator('.file-row').filter(has_text='index.html').click()
            frame = page.frame_locator('#file-html')
            await frame.locator('h1').wait_for()
            assert await frame.locator('h1').evaluate('(element) => getComputedStyle(element).color') == 'rgb(12, 123, 45)'
            assert await frame.locator('img').evaluate('(image) => image.complete && image.naturalWidth') == 24
            assert not await page.evaluate('Boolean(window.previewUnsafe)')
            assert await frame.locator('body').evaluate('() => Boolean(window.previewUnsafe)')
            assert await frame.locator('body').evaluate('() => Boolean(window.parentBlocked)')
            await page.locator('#file-mode').click()
            assert '<!doctype html>' in await page.locator('#file-source').inner_text()
            await page.locator('#file-back').click()
            await page.locator('.file-row').filter(has_text='binary.bin').click()
            await expect(page.locator('#file-status')).to_contain_text('formato')
            async with page.expect_download() as download:
                await page.locator('#file-download').click()
            result = await download.value
            assert result.suggested_filename == 'binary.bin'
            assert Path(await result.path()).read_bytes() == b'\0\x01\x02'
            await page.locator('#file-back').click()
            payloads = [
                {'name': 'relatório do celular.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.7\n\0binary'},
                {'name': 'README.md', 'mimeType': 'text/markdown', 'buffer': b'# Copia enviada'},
            ]
            async with page.expect_file_chooser() as picker:
                await page.locator('#files-upload').click()
            await (await picker.value).set_files(payloads)
            await expect(page.locator('#files-transfer-status')).to_contain_text('2 de 2 arquivo(s) enviado(s)')
            await expect(page.locator('#files-transfer-status')).to_contain_text('README (1).md')
            assert (fixture / payloads[0]['name']).read_bytes() == payloads[0]['buffer']
            assert (fixture / 'README.md').read_text().startswith('# Olá, projeto')
            assert (fixture / 'README (1).md').read_bytes() == b'# Copia enviada'
            async with page.expect_download() as download:
                await page.get_by_role('link', name='Baixar relatório do celular.pdf', exact=True).click()
            result = await download.value
            assert result.suggested_filename == payloads[0]['name']
            assert Path(await result.path()).read_bytes() == payloads[0]['buffer']
            # Failed transfers keep a useful error; a fresh selection can retry.
            async def upload_failed(route):
                await route.fulfill(status=413, json={'error': 'Limite de envio no teste.'})
            await page.route('**/api/files/upload?**', upload_failed)
            async with page.expect_file_chooser() as picker:
                await page.locator('#files-upload').click()
            await (await picker.value).set_files([payloads[0]])
            await expect(page.locator('#files-transfer-status')).to_contain_text('Limite de envio no teste.')
            await expect(page.locator('#files-upload')).to_be_enabled()
            await page.unroute('**/api/files/upload?**', upload_failed)
            await page.locator('#files-hidden').click()
            await page.locator('.file-row').filter(has_text='.hidden.md').wait_for()
            await page.locator('.file-row').filter(has_text='docs').click()
            await page.locator('.file-row').filter(has_text='other.md').wait_for()
            await page.locator('#files-up').click()
            await page.locator('.file-row').filter(has_text='README.md').wait_for()
            await page.locator('#files-filter').fill('sem-resultados')
            assert await page.locator('#files-list .file-row').count() == 0
            assert 'Nenhum arquivo' in await page.locator('#files-status').inner_text()
            await page.locator('#files-filter').fill('')
            for width in (320, 390, 1280):
                await page.set_viewport_size({'width': width, 'height': 844})
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                await page.locator('.file-row').filter(has_text='README.md').click()
                await page.locator('#file-markdown h1').wait_for()
                assert await page.locator('#files-dialog').evaluate('(element) => element.scrollWidth <= element.clientWidth')
                await page.locator('#file-back').click()
            await page.set_viewport_size({'width': 1280, 'height': 844})
            async def unavailable(route):
                await route.fulfill(status=503, json={'error': 'Computador indisponível no teste.'})
            await page.route('**/api/files?**', unavailable)
            await page.locator('#files-refresh').click()
            await expect(page.locator('#files-status')).to_contain_text('indisponível')
            await page.unroute('**/api/files?**', unavailable)
            await page.locator('#files-refresh').click()
            await page.locator('.file-row').filter(has_text='README.md').wait_for()
            await page.locator('.file-row').filter(has_text='README.md').click()
            await page.locator('#file-markdown h1').wait_for()
            await page.screenshot(path=str(BASE / 'files-desktop.png'))
            await page.get_by_role('button', name='Fechar arquivos', exact=True).click()
            await page.wait_for_function('!terminal.options.disableStdin')
            assert await page.evaluate('terminalReady && terminalGeneration') == generation
            assert not await page.evaluate('terminal.options.disableStdin')
            assert not await page.locator('#files-dialog').is_visible()
            # Reopening after a project switch must query only the new root.
            other = await page.evaluate('projects.find(project => project.path !== selectedProject)')
            if other:
                await page.evaluate('(path) => selectProject(path)', other['path'])
                async with page.expect_response(lambda response: '/api/files?' in response.url) as next_listing:
                    await page.get_by_role('button', name='Arquivos do projeto', exact=True).click()
                info = await (await next_listing.value).json()
                assert info['project'] == other['path'], info['project']
                await expect(page.locator('#files-project')).to_have_text(other['name'])
                await expect(page.locator('#files-path')).to_have_text(other['name'])
                assert fixture.name not in [entry['name'] for entry in info['entries']]
                await page.get_by_role('button', name='Fechar arquivos', exact=True).click()
                await page.evaluate('(path) => selectProject(path)', str(DEFAULT_PROJECT))
            assert not errors, errors
            await context.close()
            await browser.close()
    print('OK: upload múltiplo, cópias sem sobrescrita, downloads binários e Unicode, falhas; prévias; 320/390/1280 px; terminal preservado.')


if __name__ == '__main__':
    asyncio.run(main())
