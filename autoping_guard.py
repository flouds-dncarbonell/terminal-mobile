"""Keep the opted-in native scheduler repaired across npm updates and restarts."""
import asyncio
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess

import aiohttp

BASE = Path(__file__).resolve().parent
PATCH = BASE / 'patches/9router-autoping-persistent-20261026/apply.py'
spec = importlib.util.spec_from_file_location('autoping_patch', PATCH)
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)
log = logging.getLogger('autoping')


class Inspector:
    """Use loopback briefly; never leave an inspector opened by us listening."""
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        self.opened = False
        self.paused = False
        self.serial = 0
        self.events = []
        self.responses = {}
        try:
            async def targets():
                async with self.session.get('http://127.0.0.1:9229/json/list') as r:
                    return await r.json()
            try:
                listing = await targets()
            except aiohttp.ClientError:
                os.kill(self.pid, signal.SIGUSR1)
                self.opened = True
                for _ in range(30):
                    await asyncio.sleep(.1)
                    try:
                        listing = await targets()
                        break
                    except aiohttp.ClientError:
                        continue
                else:
                    raise RuntimeError('Could not open the local Node inspector')
            self.ws = await self.session.ws_connect(listing[0]['webSocketDebuggerUrl'])
            assert await self.evaluate('process.pid') == self.pid, 'Inspector belongs to another process'
            return self
        except BaseException:
            if hasattr(self, 'ws'):
                await self.ws.close()
            await self.session.close()
            raise

    def __init__(self, pid):
        self.pid = pid

    async def send(self, method, params=None):
        self.serial += 1
        await self.ws.send_json({'id': self.serial, 'method': method, 'params': params or {}})
        return self.serial

    async def receive(self):
        message = await self.ws.receive(timeout=15)
        if message.type != aiohttp.WSMsgType.TEXT:
            raise RuntimeError('Inspector disconnected')
        value = json.loads(message.data)
        if 'id' in value:
            self.responses[value['id']] = value
        else:
            self.events.append(value)

    async def result(self, identity):
        while identity not in self.responses:
            await self.receive()
        value = self.responses.pop(identity)
        if value.get('error') or value.get('result', {}).get('exceptionDetails'):
            raise RuntimeError('Node inspector operation failed: ' + json.dumps(value))
        return value.get('result', {})

    async def call(self, method, params=None):
        return await self.result(await self.send(method, params))

    async def evaluate(self, code, by_value=True):
        # awaitPromise=true is broken in this running Node build ("Promise was
        # collected"). Keep asynchronous work rooted globally and poll its state.
        result = await self.call('Runtime.evaluate', {'expression': code,
                                'returnByValue': by_value, 'awaitPromise': False})
        return result['result'].get('value') if by_value else result['result']

    async def async_code(self, code):
        await self.evaluate("global.__tmPingJob={done:false};global.__tmPingJob.promise=(async()=>{" + code + "})().then(value=>{global.__tmPingJob.value=value;global.__tmPingJob.done=true},error=>{global.__tmPingJob.error=String(error);global.__tmPingJob.done=true});true")
        try:
            for _ in range(600):
                state = await self.evaluate('({done:global.__tmPingJob.done,value:global.__tmPingJob.value,error:global.__tmPingJob.error})')
                if state['done']:
                    if state.get('error'):
                        raise RuntimeError(state['error'])
                    return state.get('value')
                await asyncio.sleep(.1)
            raise TimeoutError('Scheduler repair timed out')
        finally:
            # A timed-out job stays rooted until it settles; do not delete state
            # out from under its completion handlers.
            with contextlib.suppress(Exception):
                await self.evaluate('if(global.__tmPingJob?.done)delete global.__tmPingJob;true')

    async def __aexit__(self, *args):
        try:
            if self.paused:
                with contextlib.suppress(Exception):
                    await self.call('Debugger.resume')
            with contextlib.suppress(Exception):
                await self.call('Debugger.disable')
            with contextlib.suppress(Exception):
                await self.evaluate('delete global.__tmPingReload;true')
            if self.opened:
                with contextlib.suppress(Exception):
                    await self.evaluate("setTimeout(()=>process.getBuiltinModule('inspector').close(),100);true")
        finally:
            await self.ws.close()
            await self.session.close()
            # Let the deferred close finish before another repair can attach.
            # Otherwise the preceding session's timer closes the new session.
            if self.opened:
                await asyncio.sleep(.2)


async def activate(pid, app, revision=None):
    revision = revision or hashlib.sha256(''.join(s for _, _, s in patcher.prepare(app)).encode()).hexdigest()
    async with Inspector(pid) as inspector:
        if await inspector.evaluate('global.__terminalMobilePingRepair===' + json.dumps(revision)):
            return
        # Dependencies come from the installed settings route instead of a list
        # of version-specific bundle names. Reuse the HTTP process's DB/auth.
        loaded = await inspector.async_code("""
            const app=APP, base=BASE;
            const req=process.getBuiltinModule('module').createRequire(app+'/server.js');
            const plan=req(base+'/router_autoping.cjs').discover(app);
            req(app+'/.next-cli-build/server/app/api/settings/route.js');
            const runtime=req(app+'/.next-cli-build/server/webpack-runtime.js');
            await Promise.all(plan.chunks.map(id=>runtime.e(id)));
            const previous=await runtime(plan.schedulerId);
            const fs=process.getBuiltinModule('fs');
            const filename=fs.readdirSync(app+'/.next-cli-build/server/chunks').find(name=>{
                if(!name.endsWith('.js'))return false;
                const s=fs.readFileSync(app+'/.next-cli-build/server/chunks/'+name,'utf8');
                return s.includes('runQuotaAutoPingTick:')&&s.includes('terminal-mobile-idle-ping-v2');
            });
            if(!filename)throw Error('Repaired scheduler bundle missing');
            const chunk={};
            new Function('exports',fs.readFileSync(app+'/.next-cli-build/server/chunks/'+filename,'utf8'))(chunk);
            const mod={id:plan.schedulerId,exports:{}};
            chunk.modules[plan.schedulerId](mod,mod.exports,runtime);
            const fresh=await mod.exports;
            const settings=await runtime(plan.settingsId);
            global.__tmPingReload={previous,fresh,runtime,plan,settings:await settings.mt()};
            return typeof fresh.runQuotaAutoPingTick==='function';
        """.replace('APP', json.dumps(str(app))).replace('BASE', json.dumps(str(BASE))))
        assert loaded is True
        await inspector.call('Debugger.enable')
        # configureQuotaAutoPing always retains the original module's scope,
        # even after its tick binding was repaired by a previous guard process.
        function = await inspector.evaluate('global.__tmPingReload.previous.configureQuotaAutoPing', False)
        breakpoint = await inspector.call('Debugger.setBreakpointOnFunctionCall', {'objectId': function['objectId']})
        # Preserve the real settings; toggling an account still controls the
        # native interval and cannot restore the buggy tick afterwards.
        invocation = await inspector.send('Runtime.evaluate', {'expression':
            'global.__tmPingReload.previous.configureQuotaAutoPing(global.__tmPingReload.settings);true',
            'awaitPromise': False})
        while not any(e.get('method') == 'Debugger.paused' for e in inspector.events):
            await inspector.receive()
            if invocation in inspector.responses and not any(e.get('method') == 'Debugger.paused' for e in inspector.events):
                raise RuntimeError('Scheduler did not pause; refusing to alter another binding')
        inspector.paused = True
        event = next(e for e in inspector.events if e.get('method') == 'Debugger.paused')
        frame = event['params']['callFrames'][0]
        assert frame['functionName'] == 'C', 'Unsupported live scheduler function'
        async def in_frame(code):
            result = await inspector.call('Debugger.evaluateOnCallFrame', {'callFrameId': frame['callFrameId'],
                                          'expression': code, 'returnByValue': True})
            return result['result'].get('value')
        assert await in_frame('y===global.__tmPingReload.previous.runQuotaAutoPingTick') is True
        assert await in_frame('y=global.__tmPingReload.fresh.runQuotaAutoPingTick;y===global.__tmPingReload.previous.runQuotaAutoPingTick') is True
        await inspector.call('Debugger.removeBreakpoint', {'breakpointId': breakpoint['breakpointId']})
        await inspector.call('Debugger.resume')
        inspector.paused = False
        await inspector.call('Debugger.disable')
        await inspector.async_code("""
            const {previous}=global.__tmPingReload;
            await previous.runQuotaAutoPingTick();
            global.__terminalMobilePingRepair=REVISION;
            return {pid:process.pid,interval:Boolean(global.__quotaAutoPing?.interval)};
        """.replace('REVISION', json.dumps(revision)))


def listener():
    result = subprocess.run(['ss', '-ltnp', 'sport = :20128'], text=True, capture_output=True, check=True, timeout=5)
    match = re.search(r'pid=(\d+)', result.stdout)
    return int(match[1]) if match else None


async def watch():
    previous = None
    while True:
        try:
            executable = shutil.which('9router')
            if not executable:
                raise RuntimeError('9router executable missing')
            app = Path(executable).resolve().parent / 'app'
            prepared = await asyncio.to_thread(patcher.prepare, app)
            changed = await asyncio.to_thread(patcher.apply, app)
            if changed:
                log.info('Repaired installed scheduler: %s', ', '.join(changed))
                prepared = await asyncio.to_thread(patcher.prepare, app)
            pid = listener()
            if pid and Path(f'/proc/{pid}/cwd').resolve() != app.resolve():
                raise RuntimeError('The router listener does not run from the installed app directory')
            signature = (pid, tuple((str(p), hashlib.sha256(s.encode()).hexdigest()) for p, _, s in prepared))
            if pid and signature != previous:
                revision = hashlib.sha256(''.join(s for _, _, s in prepared).encode()).hexdigest()
                await asyncio.wait_for(activate(pid, app, revision), timeout=90)
                previous = signature
                log.info('Persistent auto-ping active in router PID %s', pid)
        except Exception:
            log.exception('Auto-ping repair failed; retrying in one minute')
        await asyncio.sleep(60)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    with (BASE / 'autoping-guard.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Auto-ping guard already running')
        asyncio.run(watch())
