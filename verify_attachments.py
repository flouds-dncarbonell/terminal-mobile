"""Uploads are private, bounded, transactional and tied to a live agent tab."""
import base64
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from aiohttp import FormData, web
from aiohttp.test_utils import TestClient, TestServer
import attachments
from mobile_server import authenticated


class AttachmentAPI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = Path(self.temporary.name) / 'uploads'
        self.window = {'id': '@1', 'agent': 'codex', 'path': '/tmp/project', 'dead': False, 'pid': 10}
        self.patches = [patch.object(attachments, 'STORE', self.store),
                        patch.object(attachments, 'process_tree', return_value=({}, {})),
                        patch.object(attachments, 'agent_process', return_value=(10, 'S')),
                        patch.object(attachments, 'windows', side_effect=lambda: [self.window])]
        for item in self.patches:
            item.start()
        app = web.Application(middlewares=[authenticated], client_max_size=1024 * 1024)
        app['credential'] = 'test:password'
        attachments.register(app)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.headers = {'Authorization': 'Basic ' + base64.b64encode(b'test:password').decode(),
                        'Origin': str(self.client.make_url('')).rstrip('/')}

    async def asyncTearDown(self):
        await self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    async def upload(self, files, headers=None, identity='@1'):
        data = FormData()
        for name, value in files:
            data.add_field('files', value, filename=name, content_type='application/octet-stream')
        return await self.client.post(f'/api/windows/{identity}/attachments', data=data,
                                      headers=self.headers if headers is None else headers)

    async def test_preserves_files_for_both_agents(self):
        for agent in ('codex', 'claude'):
            self.window['agent'] = agent
            response = await self.upload([('same.png', b'image bytes'), ('same.png', b'other image'),
                                          ('notes.txt', b'document')])
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            body = await response.json()
            self.assertEqual(body['window'], '@1')
            self.assertEqual(body['agent'], agent)
            paths = [Path(file['path']) for file in body['files']]
            self.assertEqual(len(set(paths)), 3)
            self.assertEqual([path.read_bytes() for path in paths], [b'image bytes', b'other image', b'document'])
            self.assertTrue(all(path.is_relative_to(self.store) for path in paths))
            self.assertTrue(all(path.stat().st_mode & 0o777 == 0o600 for path in paths))
            self.assertEqual(paths[0].parent.stat().st_mode & 0o777, 0o700)

    async def test_names_cannot_escape_or_inject_terminal_input(self):
        for name in ('../../evil.png', 'C:\\temp\\photo.jpg', '$(touch pwn);`id`\n\x1b[201~.png', '.env', 'foto com acentuação.webp'):
            safe = attachments.safe_name(name, 1)
            self.assertRegex(safe, r'^[a-zA-Z0-9._-]+$')
            self.assertNotIn('/', safe)
        response = await self.upload([('../../escape.txt', b'private')])
        self.assertEqual(response.status, 200)
        path = Path((await response.json())['files'][0]['path'])
        self.assertTrue(path.is_relative_to(self.store))

    async def test_auth_origin_and_target(self):
        for headers, expected in [({}, 401), ({'Authorization': self.headers['Authorization']}, 403),
                                   ({**self.headers, 'Origin': 'https://elsewhere.invalid'}, 403)]:
            response = await self.upload([('image.png', b'test')], headers=headers)
            self.assertEqual(response.status, expected)
        response = await self.upload([('image.png', b'test')], identity='@999')
        self.assertEqual(response.status, 400)
        for field, value in [('agent', 'shell'), ('dead', True)]:
            original = self.window[field]
            self.window[field] = value
            response = await self.upload([('image.png', b'test')])
            self.assertEqual(response.status, 400)
            self.window[field] = original
        self.assertFalse(self.store.exists())

    async def test_agent_exited_or_suspended(self):
        for process in (None, (10, 'T')):
            with patch.object(attachments, 'agent_process', return_value=process):
                response = await self.upload([('image.png', b'test')])
            self.assertEqual(response.status, 400)
        self.assertFalse(self.store.exists())

    async def test_large_upload_and_stream_limit(self):
        response = await self.upload([('large.txt', b'x' * (2 * 1024 * 1024))])
        self.assertEqual(response.status, 200)  # Multipart is streamed past the normal JSON body limit.
        path = Path((await response.json())['files'][0]['path'])
        self.assertEqual(path.stat().st_size, 2 * 1024 * 1024)
        existing = set(self.store.iterdir())
        with patch.object(attachments, 'MAX_BYTES', 1024):
            response = await self.upload([('first.txt', b'a' * 512), ('oversize.txt', b'b' * 1024)])
            self.assertEqual(response.status, 413)
            response = await self.upload([('oversize.txt', b'b' * 70000)])
            self.assertEqual(response.status, 413)
        self.assertEqual(set(self.store.iterdir()), existing)

    async def test_failed_batch_leaves_no_partial_uploads(self):
        for files in [[('ok.txt', b'ok'), ('empty.txt', b'')], [(f'{i}.txt', b'x') for i in range(9)]]:
            response = await self.upload(files)
            self.assertEqual(response.status, 400)
            self.assertEqual(list(self.store.iterdir()), [])
        response = await self.client.post('/api/windows/@1/attachments', json={}, headers=self.headers)
        self.assertEqual(response.status, 400)

    async def test_conversation_closed_during_upload(self):
        with patch.object(attachments, 'windows', side_effect=[[self.window], []]):
            response = await self.upload([('image.png', b'image')])
        self.assertEqual(response.status, 400)
        self.assertEqual(list(self.store.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
