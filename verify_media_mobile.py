"""Browser check for inline image/video/audio viewing in the files sheet."""
import asyncio
import os
from pathlib import Path
import subprocess
import tempfile

from playwright.async_api import async_playwright, expect
from mobile_core import BASE, DEFAULT_PROJECT

URL = os.environ.get('TERMINAL_FILES_TEST_URL', 'http://127.0.0.1:17781/')

def make(fixture):
    ff = ['ffmpeg', '-loglevel', 'error', '-y']
    subprocess.run(ff + ['-f', 'lavfi', '-i', 'testsrc=size=320x240:rate=10', '-t', '3', '-c:v', 'libvpx-vp9', '-b:v', '200k', str(fixture / 'clip.webm')], check=True)
    subprocess.run(ff + ['-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-c:a', 'libopus', str(fixture / 'tone.ogg')], check=True)
    subprocess.run(ff + ['-f', 'lavfi', '-i', 'testsrc=size=1600x1200', '-frames:v', '1', str(fixture / 'foto grande.png')], check=True)
    (fixture / 'broken.mov').write_bytes(b'not a movie')

async def main():
    username, password = (BASE / 'credentials').read_text().strip().split(':', 1)
    with tempfile.TemporaryDirectory(prefix='terminal-media-qa-', dir=DEFAULT_PROJECT) as temporary:
        fixture = Path(temporary)
        make(fixture)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--autoplay-policy=no-user-gesture-required'])
            for width, height, shot in ((390, 844, 'media-mobile'), (1280, 800, 'media-desktop')):
                context = await browser.new_context(viewport={'width': width, 'height': height}, is_mobile=width < 500, has_touch=True,
                                                    http_credentials={'username': username, 'password': password})
                await context.add_init_script('if (window === window.top) localStorage.setItem("project", ' + repr(str(DEFAULT_PROJECT)) + ')')
                page = await context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                await page.goto(URL)
                await page.wait_for_function('currentProject() && terminalReady')
                await page.get_by_role('button', name='Arquivos do projeto', exact=True).click()
                await page.locator('#files-filter').fill(fixture.name)
                await page.locator('.file-row').filter(has_text=fixture.name).click()
                await expect(page.locator('.file-row .media-icon')).to_have_count(4)
                # Image
                await page.locator('.file-row').filter(has_text='foto grande.png').click()
                await page.wait_for_function('document.querySelector("#file-media img")?.naturalWidth === 1600')
                await expect(page.locator('#file-meta')).to_contain_text('1600×1200')
                box = await page.locator('#file-media img').bounding_box()
                assert box['width'] <= width, box
                await page.screenshot(path=str(BASE / f'{shot}-image.png'))
                await page.locator('#file-media img').click()
                await expect(page.locator('#file-media')).to_have_class('file-media zoomed')
                assert (await page.locator('#file-media img').bounding_box())['width'] == 1600
                # Video (seek forces a Range request)
                if width < 500: await page.locator('#file-back').click()
                await page.locator('.file-row').filter(has_text='clip.webm').click()
                await page.wait_for_function('document.querySelector("#file-media video")?.readyState >= 1')
                await expect(page.locator('#file-meta')).to_contain_text('320×240')
                await page.evaluate('(() => { const v = document.querySelector("#file-media video"); v.currentTime = 2; })()')
                await page.wait_for_function('(() => { const v = document.querySelector("#file-media video"); return v.readyState >= 2 && v.currentTime >= 1.9; })()')
                await page.screenshot(path=str(BASE / f'{shot}-video.png'))
                # Audio
                if width < 500: await page.locator('#file-back').click()
                await page.locator('.file-row').filter(has_text='tone.ogg').click()
                await page.wait_for_function('document.querySelector("#file-media audio")?.readyState >= 1')
                await expect(page.locator('#file-meta')).to_contain_text('0:02')
                video_gone = await page.locator('#file-media video').count()
                assert video_gone == 0
                # Unsupported data -> friendly error, download still offered
                if width < 500: await page.locator('#file-back').click()
                await page.locator('.file-row').filter(has_text='broken.mov').click()
                await expect(page.locator('#file-status')).to_contain_text('Use ↓ para baixar')
                assert await page.locator('#file-download').get_attribute('href')
                # Closing the sheet stops playback
                await page.locator('#files-dialog [data-close]').click()
                await page.wait_for_function('!document.querySelector("#file-media *")')
                assert not errors, errors
                await context.close()
            await browser.close()
    print('media ok')

asyncio.run(main())
