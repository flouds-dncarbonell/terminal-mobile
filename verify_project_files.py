"""File API: containment, previews and real streamed transfers."""
import base64
import asyncio
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiohttp import web, FormData
from aiohttp.test_utils import TestClient, TestServer
import project_files as files
from mobile_server import authenticated


class FileAPI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / 'project'
        self.root.mkdir()
        (self.root / 'docs').mkdir()
        (self.root / 'README.md').write_text('# Olá\n\n**Leitura**', encoding='utf-8')
        (self.root / '.hidden').write_text('hidden')
        (self.root / 'binary').write_bytes(b'\0\x01')
        (self.root / 'large.txt').write_bytes(b'x' * (files.TEXT_LIMIT + 1))
        (self.root / 'index.html').write_text('<h1>Preview</h1><script>alert(1)</script>')
        (self.root / 'style.css').write_text('h1 {color: red}')
        (self.root / 'script.js').write_text('window.bad = true')
        outside = Path(self.temporary.name) / 'outside.txt'
        outside.write_text('private')
        (self.root / 'escape').symlink_to(outside)
        (self.root / 'internal.md').symlink_to(self.root / 'README.md')
        os.mkfifo(self.root / 'pipe')
        self.patches = [patch.object(files, 'load_projects', return_value=[str(self.root)]),
                        patch.object(files, 'windows', return_value=[])]
        for item in self.patches:
            item.start()
        app = web.Application(middlewares=[authenticated])
        app['credential'] = 'test:password'
        files.register(app)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.headers = {'Authorization': 'Basic ' + base64.b64encode(b'test:password').decode()}

    async def asyncTearDown(self):
        await self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    async def get(self, endpoint='/api/files', **query):
        return await self.client.get(endpoint, params={'project': str(self.root), **query}, headers=self.headers)

    async def test_listing_and_hidden(self):
        response = await self.get()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        info = await response.json()
        self.assertIsNone(info['parent'])
        self.assertEqual(info['entries'][0]['name'], 'docs')
        names = [row['name'] for row in info['entries']]
        self.assertNotIn('.hidden', names)
        self.assertNotIn('escape', names)
        self.assertNotIn('pipe', names)
        self.assertIn('internal.md', names)
        response = await self.get(hidden='1')
        self.assertIn('.hidden', [row['name'] for row in (await response.json())['entries']])
        response = await self.get(path='docs')
        self.assertEqual((await response.json())['parent'], '.')

    async def test_formats_and_errors(self):
        for path, kind in [('README.md', 'markdown'), ('index.html', 'html'), ('style.css', 'text')]:
            response = await self.get('/api/files/read', path=path)
            self.assertEqual(response.status, 200)
            self.assertEqual((await response.json())['kind'], kind)
        for path in ['binary', 'large.txt', 'pipe', 'docs', 'missing.txt']:
            response = await self.get('/api/files/read', path=path)
            self.assertEqual(response.status, 400, path)

    async def test_project_boundaries(self):
        for path in ['../outside.txt', str(self.root / 'README.md'), 'escape']:
            response = await self.get('/api/files/read', path=path)
            self.assertEqual(response.status, 400, path)
        response = await self.get(project=self.temporary.name)
        self.assertEqual(response.status, 400)
        response = await self.client.get('/api/files', params={'project': str(self.root)})
        self.assertEqual(response.status, 401)

    async def test_raw_preview_policy_and_boundaries(self):
        prefix = '/api/files/raw/' + files.token(self.root) + '/'
        for path, content_type in [('index.html', 'text/html'), ('style.css', 'text/css'), ('script.js', 'text/javascript')]:
            response = await self.client.get(prefix + path, headers=self.headers)
            self.assertEqual(response.status, 200)
            self.assertEqual(response.content_type, content_type)
            policy = response.headers['Content-Security-Policy']
            self.assertIn("script-src 'self' https: 'unsafe-inline'", policy)
            self.assertIn("style-src 'self' https: 'unsafe-inline'", policy)
            self.assertIn("font-src 'self' https: data:", policy)
            self.assertIn('sandbox allow-scripts', policy)
            self.assertNotIn('allow-same-origin', policy)
            self.assertIn("connect-src 'none'", policy)
            self.assertIn("form-action 'none'", policy)
            self.assertEqual(response.headers['X-Frame-Options'], 'SAMEORIGIN')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
        response = await self.client.get(prefix + 'escape', headers=self.headers)
        self.assertEqual(response.status, 400)
        response = await self.client.get('/api/files/raw/invalid/index.html', headers=self.headers)
        self.assertEqual(response.status, 400)

    async def test_raw_utf8_without_meta_and_binary_preservation(self):
        prefix = '/api/files/raw/' + files.token(self.root) + '/'
        for name, content in [
            ('fragment.html', '<h1>Ação · cartão do robô — próximas conversas</h1>'),
            ('legacy.htm', '<meta charset="windows-1252"><p>Configurações</p>'),
            ('accent.css', 'h1::after { content: "Prévia"; }'),
            ('accent.txt', 'Olá, não está desligado.'),
        ]:
            with self.subTest(name=name):
                data = content.encode('utf-8')
                (self.root / name).write_bytes(data)
                response = await self.client.get(prefix + name, headers=self.headers)
                self.assertEqual(response.charset, 'utf-8')
                self.assertEqual(await response.read(), data)
                self.assertEqual(await response.text(), content)
        image = b'\x89PNG\r\n\x1a\n\x00\xff'
        (self.root / 'image.png').write_bytes(image)
        response = await self.client.get(prefix + 'image.png', headers=self.headers)
        self.assertEqual(response.content_type, 'image/png')
        self.assertIsNone(response.charset)
        self.assertEqual(await response.read(), image)

    async def test_media_inline_and_ranges(self):
        payload = bytes(range(256)) * 40
        (self.root / 'clip.mp4').write_bytes(payload)
        (self.root / 'pic.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
        response = await self.get('/api/files/media', path='clip.mp4')
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers['Content-Type'], 'video/mp4')
        self.assertEqual(response.headers['Accept-Ranges'], 'bytes')
        self.assertTrue(response.headers['Content-Disposition'].startswith('inline'))
        self.assertEqual(await response.read(), payload)
        response = await self.client.get('/api/files/media', params={'project': str(self.root), 'path': 'clip.mp4'},
                                         headers={**self.headers, 'Range': 'bytes=100-199'})
        self.assertEqual(response.status, 206)
        self.assertEqual(response.headers['Content-Range'], f'bytes 100-199/{len(payload)}')
        self.assertEqual(await response.read(), payload[100:200])
        response = await self.client.get('/api/files/media', params={'project': str(self.root), 'path': 'clip.mp4'},
                                         headers={**self.headers, 'Range': 'bytes=10000-'})
        self.assertEqual(await response.read(), payload[10000:])
        response = await self.client.get('/api/files/media', params={'project': str(self.root), 'path': 'clip.mp4'},
                                         headers={**self.headers, 'Range': 'bytes=-16'})
        self.assertEqual(await response.read(), payload[-16:])
        response = await self.client.get('/api/files/media', params={'project': str(self.root), 'path': 'clip.mp4'},
                                         headers={**self.headers, 'Range': 'bytes=99999-'})
        self.assertEqual(response.status, 416)
        response = await self.get('/api/files/media', path='pic.svg')
        self.assertIn('sandbox', response.headers['Content-Security-Policy'])
        self.assertEqual((await self.get('/api/files/media', path='README.md')).status, 400)
        self.assertEqual((await self.get('/api/files/media', path='escape')).status, 400)
        (self.root / 'link.mp4').symlink_to(Path(self.temporary.name) / 'outside.txt')
        self.assertEqual((await self.get('/api/files/media', path='link.mp4')).status, 400)
        anonymous = await self.client.get('/api/files/media', params={'project': str(self.root), 'path': 'clip.mp4'})
        self.assertEqual(anonymous.status, 401)

    async def post_upload(self, data=b'new contents', name='relatório final.pdf', path='docs', headers=None):
        form = FormData(quote_fields=False)
        form.add_field('file', io.BytesIO(data), filename=name, content_type='application/octet-stream')
        return await self.client.post('/api/files/upload', params={'project': str(self.root), 'path': path},
                                      data=form, headers=headers if headers is not None else {
                                          **self.headers, 'Origin': str(self.client.make_url('/')).rstrip('/')})

    async def test_upload_and_download_exact_binary_and_unicode(self):
        data = bytes(range(256)) * 9000
        response = await self.post_upload(data)
        self.assertEqual(response.status, 201, await response.text())
        result = await response.json()
        self.assertEqual(result['name'], 'relatório final.pdf')
        self.assertEqual((self.root / result['path']).read_bytes(), data)
        response = await self.get('/api/files/download', path=result['path'])
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.read(), data)
        self.assertEqual(response.content_type, 'application/octet-stream')
        self.assertEqual(response.content_disposition.filename, result['name'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn('sandbox', response.headers['Content-Security-Policy'])
        # Downloads do not inherit the preview's 2 MB restriction.
        response = await self.get('/api/files/download', path='large.txt')
        self.assertEqual(len(await response.read()), files.TEXT_LIMIT + 1)

    async def test_collision_preserves_originals_and_symlinks(self):
        for name in ['README.md', 'internal.md', 'docs']:
            response = await self.post_upload(b'copy', name=name, path='.')
            self.assertEqual(response.status, 201, await response.text())
            result = await response.json()
            self.assertNotEqual(result['name'], name)
            self.assertEqual((self.root / result['name']).read_bytes(), b'copy')
        self.assertTrue((self.root / 'README.md').read_text().startswith('# Olá'))
        self.assertTrue((self.root / 'internal.md').is_symlink())
        for index in (2, 3):
            response = await self.post_upload(b'copy', name='README.md', path='.')
            self.assertEqual((await response.json())['name'], f'README ({index}).md')

    async def test_transfer_security(self):
        for path in ['../outside.txt', 'escape', 'pipe', 'docs', str(self.root / 'README.md')]:
            response = await self.get('/api/files/download', path=path)
            self.assertEqual(response.status, 400, path)
        response = await self.post_upload(headers=self.headers)
        self.assertEqual(response.status, 403)
        response = await self.post_upload(headers={'Origin': str(self.client.make_url('/')).rstrip('/')})
        self.assertEqual(response.status, 401)
        for path in ['..', 'missing', 'README.md']:
            response = await self.post_upload(path=path)
            self.assertEqual(response.status, 400, path)
        for name in ['../outside.txt', '/tmp/outside.txt', 'bad\\name.txt', '..']:
            response = await self.post_upload(name=name)
            self.assertEqual(response.status, 400, name)
        with self.assertRaises(ValueError):
            files.upload_name('bad\x01.txt')
        self.assertFalse(list(self.root.rglob('.terminal-upload-*')))

    async def test_upload_limit_empty_files_and_failed_batch_cleanup(self):
        with patch.object(files, 'UPLOAD_LIMIT', 4):
            response = await self.post_upload(b'12345', name='too-large')
            self.assertEqual(response.status, 413, await response.text())
        self.assertFalse((self.root / 'docs/too-large').exists())
        response = await self.post_upload(b'', name='empty.txt')
        self.assertEqual(response.status, 201)
        self.assertEqual((self.root / 'docs/empty.txt').stat().st_size, 0)
        body = FormData()
        for name in ('first', 'second'):
            body.add_field('file', b'body', filename=name)
        response = await self.client.post('/api/files/upload', params={'project': str(self.root)}, data=body,
            headers={**self.headers, 'Origin': str(self.client.make_url('/')).rstrip('/')})
        self.assertEqual(response.status, 400)
        self.assertFalse((self.root / 'first').exists())
        self.assertFalse(list(self.root.rglob('.terminal-upload-*')))

    async def test_interrupted_upload_removes_partial_file(self):
        address = self.client.make_url('/api/files/upload').with_query(project=str(self.root), path='docs')
        reader, writer = await asyncio.open_connection(address.host, address.port)
        body = b'--upload-test\r\nContent-Disposition: form-data; name="file"; filename="interrupted.bin"\r\nContent-Type: application/octet-stream\r\n\r\n' + b'x' * 100000
        headers = (f'POST {address.raw_path_qs} HTTP/1.1\r\nHost: {address.host}:{address.port}\r\n'
                   f'Authorization: {self.headers["Authorization"]}\r\nOrigin: {address.origin()}\r\n'
                   f'Content-Type: multipart/form-data; boundary=upload-test\r\nContent-Length: 1000000\r\n\r\n')
        writer.write(headers.encode() + body)
        await writer.drain()
        for _ in range(100):
            if list((self.root / 'docs').glob('.terminal-upload-*')):
                break
            await asyncio.sleep(.01)
        self.assertTrue(list((self.root / 'docs').glob('.terminal-upload-*')))
        writer.close()
        await writer.wait_closed()
        for _ in range(100):
            if not list((self.root / 'docs').glob('.terminal-upload-*')):
                break
            await asyncio.sleep(.01)
        self.assertFalse(list(self.root.rglob('.terminal-upload-*')))
        self.assertFalse((self.root / 'docs/interrupted.bin').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
