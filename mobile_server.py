import argparse
import asyncio
import base64
from datetime import datetime
import hmac
import json
import logging
import os
from pathlib import Path
import ssl
import subprocess
from urllib.parse import urlencode

from aiohttp import web, ClientSession, BasicAuth, WSMsgType
from mobile_core import BASE, DEFAULT_PROJECT, create_window, project_path, save_project, state, windows, configure_session, tmux
from attention import AttentionMonitor
from router_dependency import ensure_router, RouterUnavailable
from quota import QuotaService
import push
import project_files
import attachments

log = logging.getLogger('mobile')
WEB = BASE / 'web'


@web.middleware
async def authenticated(request, handler):
    encoded = request.headers.get('Authorization', '').removeprefix('Basic ')
    try:
        decoded = base64.b64decode(encoded, validate=True).decode()
    except (ValueError, UnicodeError):
        decoded = ''
    if not hmac.compare_digest(decoded.encode(), request.app['credential'].encode()):
        return web.Response(status=401, headers={'WWW-Authenticate': 'Basic realm="Terminal local", charset="UTF-8"'})
    if request.method != 'GET' or request.path == '/terminal/ws':
        origins = {f'{request.scheme}://{request.host}'}
        # `tailscale serve` terminates HTTPS and proxies plain HTTP to this server.
        if request.host.endswith('.ts.net'):
            origins.add(f'https://{request.host}')
        if request.headers.get('Origin') not in origins:
            raise web.HTTPForbidden(text='Origem inválida.')
    try:
        response = await handler(request)
    except RouterUnavailable as error:
        return web.json_response({'error': str(error)}, status=503, headers={'Cache-Control': 'no-store'})
    except (ValueError, FileNotFoundError, NotADirectoryError, PermissionError) as error:
        return web.json_response({'error': str(error)}, status=400)
    except subprocess.CalledProcessError as error:
        log.exception('tmux operation failed')
        return web.json_response({'error': 'Não foi possível abrir o terminal. Tente novamente.'}, status=500)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN' if request.path.startswith('/api/files/raw/') else 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    if request.path.startswith(('/api/', '/terminal/')):
        response.headers['Cache-Control'] = 'no-store'
    return response


async def get_state(request):
    result = await asyncio.to_thread(state)
    result['alerts'] = request.app['attention'].snapshot()
    return web.json_response(result)


async def get_quotas(request):
    result = await request.app['quotas'].snapshot(request.app['http'], force=request.query.get('refresh') == '1')
    return web.json_response(result)


async def reorder_accounts(request):
    body = await request.json()
    result = await request.app['quotas'].reorder(request.app['http'], body.get('provider'), body.get('order'), body.get('previous'))
    return web.json_response(result)


async def attention_monitor(app):
    monitor = AttentionMonitor()
    app['attention'] = monitor

    async def scan():
        try:
            await asyncio.to_thread(monitor.scan)
            # Codex has no trusted hook for a new prompt; a running turn clears its push.
            for window in monitor.working:
                await asyncio.to_thread(push.clear, f'term:{window}')
        except Exception:
            log.exception('Could not inspect terminal status')

    await scan()

    async def watch():
        while True:
            await asyncio.sleep(2)
            await scan()

    task = asyncio.create_task(watch())
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


QUOTA_PUSH_STATE = BASE / 'push-quota-state.json'

def quota_returned(snapshot):
    """Providers whose every account was out of quota and now has one back."""
    try:
        empty = set(json.loads(QUOTA_PUSH_STATE.read_text()))
    except (OSError, ValueError):
        empty = set()
    providers = {}
    for row in snapshot['accounts']:
        providers.setdefault(row['providerId'], []).append(row)
    returned = []
    for provider, rows in providers.items():
        states = [row['quotaState'] for row in rows]
        if all(state in ('session', 'total') for state in states):
            empty.add(provider)
        elif provider in empty and 'available' in states:
            # Unknown results (query errors) neither end nor confirm the outage.
            empty.discard(provider)
            returned.append((rows[0]['provider'], [row['name'] for row in rows if row['quotaState'] == 'available']))
    saved = json.dumps(sorted(empty))
    if not QUOTA_PUSH_STATE.exists() or QUOTA_PUSH_STATE.read_text() != saved:
        push.private_write(QUOTA_PUSH_STATE, saved)
    return returned

RESET_CREDIT_STATE = BASE / 'reset-credits-state.json'

async def reset_credit_automation(app):
    try:
        state = json.loads(RESET_CREDIT_STATE.read_text())
    except (OSError, ValueError):
        state = {}
    save = lambda: push.private_write(RESET_CREDIT_STATE, json.dumps(state))
    for event in await app['quotas'].due_reset_credits(app['http'], state, save):
        account, kind = event['account'], event['type']
        when = datetime.fromisoformat(event['expiresAt'].replace('Z', '+00:00')).astimezone().strftime('%d/%m às %H:%M')
        agent = 'claude' if account.get('providerId') == 'claude' else 'codex'
        name = account.get('provider') or agent.title()
        log.info('Crédito de redefinição do %s (%s): %s %s', name, account['name'], kind, event.get('message', ''))
        title, body = {
            'warning': (f'Crédito do {name} expira em {event.get("label")}',
                        f'{account["name"]}: expira {when}. Será usado automaticamente 5 minutos antes.'),
            'redeemed': (f'Crédito do {name} usado', f'{account["name"]}: limites redefinidos antes de o crédito expirar ({when}).'),
            'failed': (f'Crédito do {name} não foi usado', f'{account["name"]}: {event.get("message")} Expira {when}; nova tentativa em um minuto.'),
        }[kind]
        await asyncio.to_thread(push.send, title, body, tag='reset-credit:' + account['id'], url='/?view=quotas', icon=f'/assets/notify-{agent}.png')

async def quota_automation(app):
    async def watch():
        while True:
            try:
                await reset_credit_automation(app)
            except Exception:
                log.exception('Não foi possível verificar os créditos de redefinição')
            try:
                changes = await app['quotas'].reconcile(app['http'])
                if changes:
                    log.info('Automação de quotas: %s', changes)
                for provider, names in quota_returned(app['quotas'].cached):
                    log.info('Quota de %s voltou: %s', provider, names)
                    await asyncio.to_thread(push.send, f'Cota do {provider} voltou', 'Disponível: ' + ', '.join(names) + '.',
                                            tag='quota:' + provider, url='/?view=quotas', icon='/assets/notify-quota.png')
            except Exception:
                log.exception('Não foi possível aplicar a automação de quotas; nova tentativa em um minuto')
                app['quotas'].cached = None
            await asyncio.sleep(60)

    task = asyncio.create_task(watch())
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def push_key(request):
    endpoint = request.query.get('endpoint', '')
    return web.json_response({'key': await asyncio.to_thread(push.public_key),
                              'subscribed': bool(endpoint) and await asyncio.to_thread(push.subscribed, endpoint)})

async def push_subscribe(request):
    await asyncio.to_thread(push.subscribe, await request.json())
    return web.json_response({})

async def push_unsubscribe(request):
    await asyncio.to_thread(push.unsubscribe, (await request.json()).get('endpoint', ''))
    return web.json_response({})

async def push_seen(request):
    tags = (await request.json()).get('tags')
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise ValueError('Avisos inválidos.')
    await asyncio.to_thread(push.forget, tags)
    return web.json_response({})

async def push_test(request):
    sent = await asyncio.to_thread(push.send, 'Notificações ativas', 'Você receberá avisos dos agentes e das cotas.', tag='test')
    return web.json_response({'sent': sent})

async def directories(request):
    path = Path(project_path(request.query.get('path', str(Path.home()))))
    rows = []
    for child in sorted(path.iterdir(), key=lambda p: p.name.casefold()):
        try:
            if not child.name.startswith('.') and child.is_dir():
                rows.append({'name': child.name, 'path': str(child)})
        except OSError:
            pass
    return web.json_response({'path': str(path), 'parent': str(path.parent), 'directories': rows})


async def new_project(request):
    body = await request.json()
    path = await asyncio.to_thread(save_project, body.get('path', ''))
    return web.json_response({'path': path})


async def new_window(request):
    body = await request.json()
    agent = body.get('agent', '')
    # Agents opened from the phone start with full access and no approval prompts.
    args = {
        'codex': ['--sandbox', 'danger-full-access', '--ask-for-approval', 'never'],
        'claude': ['--dangerously-skip-permissions'],
    }.get(agent, [])
    identity = await asyncio.to_thread(create_window, body.get('path', ''), agent, args)
    return web.json_response({'id': identity})


def close_window(identity):
    pane_pid = int(tmux('display-message', '-p', '-t', identity, '#{pane_pid}', check=False) or 0)
    tmux('kill-window', '-t', identity)
    if not pane_pid:
        return
    # tmux hangs up the pane; anything still in its session (e.g. an agent that
    # ignored SIGHUP) is ended. Codex background servers run in their own
    # session, so tabs that share them are not affected.
    import time
    for _ in range(30):
        rows = subprocess.run(['ps', '-eo', 'pid=,sid='], capture_output=True, text=True).stdout.split('\n')
        left = [int(pid) for pid, sid in (r.split() for r in rows if r.strip()) if int(sid) == pane_pid]
        if not left:
            return
        time.sleep(.1)
    for pid in left:
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            pass

async def delete_window(request):
    identity = request.match_info['window']
    if identity not in {window['id'] for window in await asyncio.to_thread(windows)}:
        raise web.HTTPNotFound(text='Este terminal já foi encerrado.')
    request.app['attention'].closing.add(identity)
    await asyncio.to_thread(close_window, identity)
    await asyncio.to_thread(push.clear, f'term:{identity}')
    return web.json_response({})

async def leave_scrollback(request):
    identity = request.match_info['window']
    if identity not in {window['id'] for window in await asyncio.to_thread(windows)}:
        raise web.HTTPNotFound(text='Terminal encerrado.')
    # Scrolling puts the pane in tmux copy mode, which would swallow typing.
    if await asyncio.to_thread(tmux, 'display-message', '-p', '-t', identity, '#{pane_in_mode}', check=False) == '1':
        await asyncio.to_thread(tmux, 'send-keys', '-X', '-t', identity, 'cancel', check=False)
    return web.json_response({})

async def websocket(request):
    identity = request.query.get('window', '')
    if identity not in {window['id'] for window in await asyncio.to_thread(windows)}:
        raise web.HTTPNotFound(text='Terminal encerrado.')
    upstream_url = f"http://127.0.0.1:{request.app['backend_port']}/ws?{urlencode({'arg': identity})}"
    client = request.app['http']
    async with client.ws_connect(upstream_url, protocols=['tty'], origin=f"http://127.0.0.1:{request.app['backend_port']}", heartbeat=20) as upstream:
        downstream = web.WebSocketResponse(heartbeat=20, max_msg_size=1024 * 1024)
        await downstream.prepare(request)
        request.app['websockets'].add(downstream)

        async def forward(source, destination):
            async for message in source:
                if message.type == WSMsgType.BINARY:
                    await destination.send_bytes(message.data)
                elif message.type == WSMsgType.TEXT:
                    await destination.send_str(message.data)

        tasks = [asyncio.create_task(forward(upstream, downstream)), asyncio.create_task(forward(downstream, upstream))]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await downstream.close()
            request.app['websockets'].discard(downstream)
    return downstream


async def page(request):
    return web.FileResponse(WEB / 'index.html', headers={'Cache-Control': 'no-cache'})


async def root_certificate(request):
    return web.FileResponse(BASE / 'certs/rootCA.crt', headers={'Content-Type': 'application/x-x509-ca-cert', 'Content-Disposition': 'attachment; filename="Terminal-Local-CA.crt"'})


async def config(request):
    try:
        info = json.loads((BASE / 'network.json').read_text())
    except (OSError, ValueError):
        info = {'ip': '127.0.0.1', 'tls_port': 7682}
    return web.json_response(info)


async def disconnect_clients(app):
    await asyncio.gather(*(socket.close(code=1001, message=b'Servico reiniciando') for socket in list(app['websockets'])))


async def resources(app):
    # ttyd stays on loopback; authentication and browser origin checks live here.
    command = [os.environ.get('TERMINAL_MOBILE_TTYD', str(BASE / 'ttyd')), '-i', '127.0.0.1', '-p', str(app['backend_port']), '-W', '-O', '-a', str(BASE / 'attach.sh')]
    environment = {k: v for k, v in os.environ.items() if k != 'TMUX'}
    process = await asyncio.create_subprocess_exec(*command, env=environment)
    app['http'] = ClientSession()
    for _ in range(50):
        try:
            async with app['http'].get(f"http://127.0.0.1:{app['backend_port']}/") as response:
                if response.status == 200:
                    break
        except OSError:
            pass
        if process.returncode is not None:
            raise RuntimeError('ttyd não iniciou.')
        await asyncio.sleep(.1)
    else:
        process.terminate()
        await process.wait()
        await app['http'].close()
        raise RuntimeError('ttyd não respondeu.')
    try:
        yield
    finally:
        await app['http'].close()
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                process.kill()
                await process.wait()


async def run(args):
    try:
        await asyncio.to_thread(ensure_router)
        if not windows():
            await asyncio.to_thread(create_window, str(DEFAULT_PROJECT), 'codex',
                                    ['--sandbox', 'danger-full-access', '--ask-for-approval', 'never'])
            await asyncio.to_thread(create_window, str(DEFAULT_PROJECT), 'claude')
    except RouterUnavailable as error:
        # Keep the panel available so the user can retry or open a plain shell.
        log.error('%s', error)
    if windows():
        configure_session()
    app = web.Application(middlewares=[authenticated], client_max_size=1024 * 1024)
    app['credential'] = (BASE / 'credentials').read_text().strip()
    app['backend_port'] = args.backend_port
    app['websockets'] = set()
    app['quotas'] = QuotaService(state_path=BASE / 'quota-automation.json')
    app.on_shutdown.append(disconnect_clients)
    app.cleanup_ctx.append(resources)
    app.cleanup_ctx.append(attention_monitor)
    if not args.no_quota_automation:
        app.cleanup_ctx.append(quota_automation)
    app.router.add_get('/', page)
    app.router.add_get('/install', page)
    app.router.add_get('/api/state', get_state)
    app.router.add_get('/api/quotas', get_quotas)
    app.router.add_post('/api/quotas/order', reorder_accounts)
    app.router.add_get('/api/config', config)
    app.router.add_get('/api/push', push_key)
    app.router.add_post('/api/push/subscribe', push_subscribe)
    app.router.add_post('/api/push/unsubscribe', push_unsubscribe)
    app.router.add_post('/api/push/test', push_test)
    app.router.add_post('/api/push/seen', push_seen)
    app.router.add_get('/api/directories', directories)
    project_files.register(app)
    attachments.register(app)
    app.router.add_post('/api/projects', new_project)
    app.router.add_post('/api/windows', new_window)
    app.router.add_post('/api/windows/{window}/bottom', leave_scrollback)
    app.router.add_delete('/api/windows/{window}', delete_window)
    app.router.add_get('/terminal/ws', websocket)
    app.router.add_get('/ca.crt', root_certificate)
    app.router.add_static('/assets/', WEB)
    app.router.add_get('/sw.js', lambda r: web.FileResponse(WEB / 'sw.js', headers={'Cache-Control': 'no-cache', 'Service-Worker-Allowed': '/'}))
    app.router.add_get('/manifest.webmanifest', lambda r: web.FileResponse(WEB / 'manifest.webmanifest', headers={'Content-Type': 'application/manifest+json'}))
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, args.host, args.port).start()
    if args.tls_port:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(BASE / 'certs/server.crt', BASE / 'certs/server.key')
        await web.TCPSite(runner, args.host, args.tls_port, ssl_context=context).start()
    log.info('Terminal mobile ativo; HTTP %s, HTTPS %s', args.port, args.tls_port)
    import signal
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for event in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(event, stopping.set)
    try:
        await stopping.wait()
    finally:
        await runner.cleanup()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=7681)
    parser.add_argument('--tls-port', type=int, default=7682)
    parser.add_argument('--backend-port', type=int, default=17682)
    parser.add_argument('--no-quota-automation', action='store_true', help='Desativa as alterações automáticas de contas neste processo (prévia/testes).')
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(parser.parse_args()))
