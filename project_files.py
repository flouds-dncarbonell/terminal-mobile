"""Project browsing, isolated previews and streamed file transfers."""
import asyncio
import base64
import os
from pathlib import Path
import stat
import secrets
import unicodedata
from urllib.parse import quote

from aiohttp import web
from aiohttp.helpers import content_disposition_header
from mobile_core import load_projects, windows

TEXT_LIMIT = 2 * 1024 * 1024
ASSET_LIMIT = 16 * 1024 * 1024
LIST_LIMIT = 2000
UPLOAD_LIMIT = 100 * 1024 * 1024
ASSET_TYPES = {
    '.js': 'text/javascript', '.mjs': 'text/javascript',
    '.css': 'text/css', '.png': 'image/png', '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp',
    '.avif': 'image/avif', '.ico': 'image/x-icon', '.svg': 'image/svg+xml',
    '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf',
    '.otf': 'font/otf',
}
MEDIA_TYPES = {
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
    '.webp': 'image/webp', '.avif': 'image/avif', '.svg': 'image/svg+xml', '.bmp': 'image/bmp',
    '.ico': 'image/x-icon', '.heic': 'image/heic', '.heif': 'image/heif',
    '.mp4': 'video/mp4', '.m4v': 'video/mp4', '.mov': 'video/quicktime', '.webm': 'video/webm',
    '.ogv': 'video/ogg', '.mkv': 'video/x-matroska', '.3gp': 'video/3gpp',
    '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.aac': 'audio/aac', '.wav': 'audio/wav',
    '.ogg': 'audio/ogg', '.oga': 'audio/ogg', '.opus': 'audio/ogg', '.flac': 'audio/flac',
    '.weba': 'audio/webm',
}
PREVIEW_POLICY = (
    "default-src 'none'; script-src 'self' https: 'unsafe-inline'; connect-src 'none'; "
    "style-src 'self' https: 'unsafe-inline'; img-src 'self' https: data:; font-src 'self' https: data:; "
    "form-action 'none'; base-uri 'none'; frame-ancestors 'self'; sandbox allow-scripts"
)


def project_root(value):
    if not value:
        raise ValueError('Escolha um projeto primeiro.')
    root = Path(value).resolve(strict=True)
    known = {*load_projects(), *(row['path'] for row in windows())}
    if not root.is_dir() or not any(root == Path(path).resolve() for path in known):
        raise PermissionError('Escolha um projeto cadastrado no app.')
    return root


def resolve_path(root, value):
    relative = Path(value or '.')
    if relative.is_absolute():
        raise PermissionError('O caminho precisa estar dentro do projeto.')
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root):
        raise PermissionError('Este arquivo está fora do projeto.')
    return path


def token(root):
    return base64.urlsafe_b64encode(str(root).encode()).decode().rstrip('=')


def read_bytes(path, limit):
    if not path.is_file():
        raise ValueError('Apenas arquivos comuns podem ser visualizados.')
    # Do not block on pipes/devices, or follow a final symlink swapped after resolve.
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Apenas arquivos comuns podem ser visualizados.')
        if info.st_size > limit:
            raise ValueError(f'Arquivo muito grande para visualizar (limite de {limit // 1024 // 1024} MB).')
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError('Arquivo muito grande para visualizar.')
    return data


def listing(project, relative, hidden):
    root = project_root(project)
    folder = resolve_path(root, relative)
    if not folder.is_dir():
        raise NotADirectoryError('Esta pasta não está disponível.')
    rows = []
    truncated = False
    for child in folder.iterdir():
        if not hidden and child.name.startswith('.'):
            continue
        try:
            resolved = child.resolve(strict=True)
            if not resolved.is_relative_to(root):
                continue
            info = resolved.stat()
            directory = stat.S_ISDIR(info.st_mode)
            if not directory and not stat.S_ISREG(info.st_mode):
                continue
            rows.append({'name': child.name, 'path': child.relative_to(root).as_posix(),
                         'directory': directory, 'size': None if directory else info.st_size})
            if len(rows) >= LIST_LIMIT:
                truncated = True
                break
        except OSError:
            continue
    rows.sort(key=lambda row: (not row['directory'], row['name'].casefold()))
    return {'project': str(root), 'name': root.name, 'token': token(root),
            'path': folder.relative_to(root).as_posix(),
            'parent': None if folder == root else folder.parent.relative_to(root).as_posix(),
            'entries': rows, 'truncated': truncated, 'uploadLimit': UPLOAD_LIMIT}


def document(project, relative):
    root = project_root(project)
    path = resolve_path(root, relative)
    data = read_bytes(path, TEXT_LIMIT)
    if b'\0' in data:
        raise ValueError('Este formato não tem visualização de texto.')
    try:
        content = data.decode('utf-8-sig')
    except UnicodeError:
        raise ValueError('Este arquivo não é um texto UTF-8.') from None
    suffix = path.suffix.lower()
    kind = 'markdown' if suffix in ('.md', '.markdown', '.mdown') else 'html' if suffix in ('.html', '.htm') else 'text'
    return {'path': path.relative_to(root).as_posix(), 'name': path.name,
            'content': content, 'kind': kind, 'size': len(data), 'token': token(root)}


async def list_files(request):
    result = await asyncio.to_thread(listing, request.query.get('project', ''),
                                     request.query.get('path', '.'), request.query.get('hidden') == '1')
    return web.json_response(result)


async def read_file(request):
    return web.json_response(await asyncio.to_thread(document, request.query.get('project', ''),
                                                     request.query.get('path', '')))


def raw_file(encoded, relative):
    try:
        project = base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True).decode()
    except (ValueError, UnicodeError):
        raise ValueError('Projeto inválido.') from None
    root = project_root(project)
    path = resolve_path(root, relative)
    suffix = path.suffix.lower()
    content_type = ASSET_TYPES.get(suffix)
    if not content_type:
        content_type = 'text/html' if suffix in ('.html', '.htm') else 'text/plain'
    data = read_bytes(path, ASSET_LIMIT if suffix in ASSET_TYPES else TEXT_LIMIT)
    return data, content_type


async def raw(request):
    data, content_type = await asyncio.to_thread(raw_file, request.match_info['project'], request.match_info['path'])
    # Preview documents use UTF-8, like the source reader. Without a transport
    # charset, browsers can interpret HTML fragments as Windows-1252.
    charset = 'utf-8' if content_type.startswith('text/') else None
    return web.Response(body=data, content_type=content_type, charset=charset, headers={
        'Content-Security-Policy': PREVIEW_POLICY,
        'Access-Control-Allow-Origin': '*',
        'Cross-Origin-Resource-Policy': 'cross-origin',
    })


def open_directory(root, folder):
    # Pin each directory without following links swapped after resolve_path.
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in folder.relative_to(root).parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def open_download(project, relative):
    root = project_root(project)
    path = resolve_path(root, relative)
    directory = open_directory(root, path.parent)
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory)
    finally:
        os.close(directory)
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode):
        os.close(descriptor)
        raise ValueError('Apenas arquivos comuns podem ser baixados.')
    return os.fdopen(descriptor, 'rb'), info.st_size, path.name


async def download(request):
    stream, length, name = await asyncio.to_thread(open_download, request.query.get('project', ''),
                                                  request.query.get('path', ''))
    # Explicit headers: a streaming response is prepared before middleware returns.
    response = web.StreamResponse(headers={
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': content_disposition_header('attachment', filename=name) + "; filename*=UTF-8''" + quote(name, safe=''),
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY', 'Referrer-Policy': 'same-origin',
        'Content-Security-Policy': "default-src 'none'; sandbox",
    })
    response.content_length = length
    try:
        await response.prepare(request)
        remaining = length
        while remaining:
            chunk = await asyncio.to_thread(stream.read, min(256 * 1024, remaining))
            if not chunk:
                response.force_close()
                break
            await response.write(chunk)
            remaining -= len(chunk)
        await response.write_eof()
    finally:
        stream.close()
    return response


def byte_range(header, length):
    """Single range only (what media elements send); None means the whole file."""
    if not header:
        return None
    unit, _, spec = header.partition('=')
    if unit.strip() != 'bytes' or ',' in spec:
        return None
    first, _, last = spec.strip().partition('-')
    try:
        if not first:
            count = int(last)
            if count <= 0:
                raise ValueError
            return max(length - count, 0), length - 1
        start = int(first)
        end = min(int(last), length - 1) if last else length - 1
    except ValueError:
        raise web.HTTPRequestRangeNotSatisfiable(headers={'Content-Range': f'bytes */{length}'}) from None
    if start >= length or end < start:
        raise web.HTTPRequestRangeNotSatisfiable(headers={'Content-Range': f'bytes */{length}'})
    return start, end

async def media(request):
    relative = request.query.get('path', '')
    content_type = MEDIA_TYPES.get(Path(relative).suffix.lower())
    if not content_type:
        raise ValueError('Este formato não tem visualização de mídia.')
    stream, length, name = await asyncio.to_thread(open_download, request.query.get('project', ''), relative)
    try:
        selected = byte_range(request.headers.get('Range'), length)
        start, end = selected or (0, length - 1)
        response = web.StreamResponse(status=206 if selected else 200, headers={
            'Content-Type': content_type, 'Accept-Ranges': 'bytes',
            'Content-Disposition': content_disposition_header('inline', filename=name) + "; filename*=UTF-8''" + quote(name, safe=''),
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY', 'Referrer-Policy': 'same-origin',
            # SVG opened directly must not run scripts; <img> never runs them anyway.
            'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        })
        if selected:
            response.headers['Content-Range'] = f'bytes {start}-{end}/{length}'
        response.content_length = end - start + 1 if length else 0
        await response.prepare(request)
        if length:
            await asyncio.to_thread(stream.seek, start)
        remaining = end - start + 1 if length else 0
        while remaining:
            chunk = await asyncio.to_thread(stream.read, min(256 * 1024, remaining))
            if not chunk:
                response.force_close()
                break
            await response.write(chunk)
            remaining -= len(chunk)
        await response.write_eof()
        return response
    finally:
        stream.close()

def upload_name(value):
    if (not value or value in ('.', '..') or '/' in value or '\\' in value
            or any(unicodedata.category(char).startswith('C') for char in value)
            or len(value.encode('utf-8')) > 240):
        raise ValueError('Nome de arquivo inválido ou muito longo.')
    return value


def publish_upload(directory, temporary, name):
    original = Path(name)
    for index in range(10000):
        candidate = name if not index else f'{original.stem} ({index}){original.suffix}'
        try:
            # link() never replaces an existing file, directory or symlink.
            os.link(temporary, candidate, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            return candidate
        except FileExistsError:
            continue
    raise ValueError('Há muitas cópias com este nome. Renomeie o arquivo e tente novamente.')


async def upload(request):
    if request.content_type != 'multipart/form-data':
        raise ValueError('Escolha um arquivo para enviar.')
    if request.content_length and request.content_length > UPLOAD_LIMIT + 65536:
        return web.json_response({'error': 'Cada arquivo pode ter até 100 MB.'}, status=413)
    root = await asyncio.to_thread(project_root, request.query.get('project', ''))
    folder = await asyncio.to_thread(resolve_path, root, request.query.get('path', '.'))
    directory = open_directory(root, folder)
    temporary = '.terminal-upload-' + secrets.token_hex(16)
    try:
        reader = await request.multipart()
        part = await reader.next()
        if part is None or part.name != 'file' or part.filename is None:
            raise ValueError('Escolha um arquivo para enviar.')
        name = upload_name(part.filename)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        total = 0
        with os.fdopen(descriptor, 'wb') as stream:
            while chunk := await part.read_chunk(65536):
                total += len(chunk)
                if total > UPLOAD_LIMIT:
                    return web.json_response({'error': 'Cada arquivo pode ter até 100 MB.'}, status=413)
                await asyncio.to_thread(stream.write, chunk)
        if await reader.next() is not None:
            raise ValueError('Envie um arquivo por requisição.')
        name = publish_upload(directory, temporary, name)
        return web.json_response({'name': name, 'size': total,
                                  'path': (folder.relative_to(root) / name).as_posix()}, status=201)
    except PermissionError:
        raise PermissionError('Sem permissão para salvar arquivos nesta pasta.') from None
    except OSError as error:
        if error.errno == 28:
            raise ValueError('O computador está sem espaço para salvar o arquivo.') from None
        raise
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        finally:
            os.close(directory)


def register(app):
    app.router.add_get('/api/files', list_files)
    app.router.add_get('/api/files/read', read_file)
    app.router.add_get('/api/files/download', download, allow_head=False)
    app.router.add_get('/api/files/media', media, allow_head=False)
    app.router.add_post('/api/files/upload', upload)
    app.router.add_get('/api/files/raw/{project}/{path:.*}', raw)
