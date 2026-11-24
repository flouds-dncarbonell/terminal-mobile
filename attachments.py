"""Private uploads referenced by the existing agent's interactive composer."""
import asyncio
from pathlib import Path
import re
import shutil
import tempfile
import unicodedata

from aiohttp import web
from mobile_core import BASE, windows
from attention import agent_process, process_tree

STORE = BASE / 'attachments'
MAX_FILES = 8
MAX_BYTES = 20 * 1024 * 1024


def target(identity):
    window = next((row for row in windows() if row['id'] == identity), None)
    if not window or window['dead']:
        raise ValueError('Este terminal foi encerrado. Abra a conversa novamente.')
    if window['agent'] not in ('codex', 'claude'):
        raise ValueError('Abra uma conversa do Codex ou Claude para adicionar anexos.')
    process = agent_process(window['pid'], window['agent'], *process_tree())
    if not process or process[1].startswith(('T', 't')):
        raise ValueError('O agente está encerrado ou suspenso. Retome a conversa antes de anexar.')
    return window


def safe_name(value, index):
    # No whitespace, terminal control codes or shell syntax reaches the composer.
    value = unicodedata.normalize('NFKD', value.replace('\\', '/').split('/')[-1])
    value = value.encode('ascii', 'ignore').decode()
    value = re.sub(r'[^a-zA-Z0-9._-]+', '-', value).strip('.-') or 'arquivo'
    suffix = Path(value).suffix[:12]
    stem = value[:-len(suffix)] if suffix else value
    return f'{index:02d}-{stem[:70]}{suffix}'


async def upload(request):
    identity = request.match_info['window']
    window = await asyncio.to_thread(target, identity)
    if request.content_type != 'multipart/form-data':
        raise ValueError('Escolha pelo menos um arquivo para anexar.')
    if request.content_length and request.content_length > MAX_BYTES + 65536:
        return web.json_response({'error': 'Os anexos podem somar até 20 MB.'}, status=413)
    STORE.mkdir(mode=0o700, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='upload-', dir=STORE))
    committed = False
    total = 0
    files = []
    try:
        reader = await request.multipart()
        async for part in reader:
            if part.name != 'files' or part.filename is None:
                raise ValueError('Envio de arquivo inválido.')
            if len(files) >= MAX_FILES:
                raise ValueError('Adicione até 8 arquivos por vez.')
            name = safe_name(part.filename, len(files) + 1)
            path = folder / name
            size = 0
            with path.open('xb') as stream:
                path.chmod(0o600)
                while chunk := await part.read_chunk(65536):
                    total += len(chunk)
                    size += len(chunk)
                    if total > MAX_BYTES:
                        return web.json_response({'error': 'Os anexos podem somar até 20 MB.'}, status=413)
                    await asyncio.to_thread(stream.write, chunk)
            if not size:
                raise ValueError('Um dos arquivos está vazio. Escolha outro arquivo.')
            files.append({'name': part.filename, 'path': str(path), 'size': size})
        if not files:
            raise ValueError('Escolha pelo menos um arquivo para anexar.')
        current = await asyncio.to_thread(target, identity)
        if current['agent'] != window['agent'] or current['path'] != window['path']:
            raise ValueError('A conversa mudou durante o envio. Abra os anexos novamente.')
        committed = True
        return web.json_response({'window': identity, 'agent': window['agent'], 'files': files})
    finally:
        if not committed:
            await asyncio.to_thread(shutil.rmtree, folder, True)


def register(app):
    app.router.add_post('/api/windows/{window}/attachments', upload)
