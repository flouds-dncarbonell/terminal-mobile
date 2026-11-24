"""Quotas and account priority using 9router's local CLI authentication."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time
from urllib.parse import quote

from aiohttp import ClientError, ClientTimeout
from router_dependency import ensure_router, RouterUnavailable

ROUTER_URL = 'http://127.0.0.1:20128'
PROVIDER_NAMES = {'codex': 'Codex', 'claude': 'Claude', 'antigravity': 'Antigravity', 'github': 'GitHub Copilot'}
QUOTA_NAMES = {
    'session': 'Sessão · 5 horas', 'session (5h)': 'Sessão · 5 horas',
    'weekly': 'Semana · 7 dias', 'weekly (7d)': 'Semana · 7 dias',
    'spark_session': 'Spark · 5 horas', 'spark_weekly': 'Spark · 7 dias',
    'review_session': 'Revisão · 5 horas', 'review_weekly': 'Revisão · 7 dias',
}
QUOTA_ORDER = {'available': 0, 'unknown': 0, 'session': 1, 'total': 2}
# Codex reset credits change rarely; each read is a ChatGPT call per account.
RESET_CREDITS_TTL = 600
# Pushes before a credit expires, then it is consumed instead of lost.
RESET_CREDIT_WARNINGS = ((86400, '24 h'), (3600, '1 h'))
RESET_CREDIT_REDEEM_BEFORE = 300
RESET_CREDIT_ATTEMPTS = 3


def exhausted(quota):
    """None means unknown; missing or malformed usage must never disable a login."""
    if not isinstance(quota, dict):
        return None
    if quota.get('unlimited') is True:
        return False
    for field in ('remaining', 'remainingPercentage'):
        value = number(quota.get(field))
        if value is not None:
            return value <= 0
    used, total = number(quota.get('used')), number(quota.get('total'))
    if used is not None and total is not None and total > 0:
        return used >= total
    return None


def quota_condition(usage, provider):
    if usage.get('usageStale') is True:
        return {'quotaState': 'unknown', 'totalAvailable': None}
    quotas = usage.get('quotas')
    if not isinstance(quotas, dict):
        return {'quotaState': 'unknown', 'totalAvailable': None}
    if provider == 'antigravity':
        # These are separate pools. A depleted model/pool cannot disable an
        # account that can still serve the other pool.
        families = ('gemini', 'claude_gpt')
        totals = [exhausted(quotas.get(f'{family}_weekly')) for family in families]
        sessions = [exhausted(quotas.get(f'{family}_session')) for family in families]
        total_empty = all(value is True for value in totals)
        total_available = True if False in totals else False if total_empty else None
        session_empty = all(total is True or session is True for total, session in zip(totals, sessions))
    else:
        totals = [exhausted(quotas[key]) for key in ('weekly', 'weekly (7d)', 'total', 'daily', 'monthly') if key in quotas]
        sessions = [exhausted(quotas[key]) for key in ('session', 'session (5h)') if key in quotas]
        total_empty = True in totals
        total_available = False if total_empty else True if totals and all(value is False for value in totals) else None
        session_empty = True in sessions
    state = 'total' if total_empty else 'session' if session_empty else 'available' if False in totals + sessions else 'unknown'
    return {'quotaState': state, 'totalAvailable': total_available}


def cli_headers():
    data = Path(os.environ.get('DATA_DIR', str(Path.home() / '.9router')))
    try:
        machine = (data / 'machine-id').read_text().strip()
        secret = (data / 'auth/cli-secret').read_text().strip()
        if not machine or not secret:
            raise OSError('Missing CLI credentials')
    except OSError as error:
        raise RouterUnavailable('Não foi possível autenticar a consulta local ao 9router.') from error
    token = hashlib.sha256((machine + '9r-cli-auth' + secret).encode()).hexdigest()[:16]
    return {'x-9r-cli-token': token}


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    return None


def normalize_quotas(usage, provider=''):
    result = []
    quotas = usage.get('quotas')
    if not isinstance(quotas, dict):
        return result
    for key, quota in quotas.items():
        if not isinstance(quota, dict):
            continue
        if provider == 'antigravity':
            if key.startswith('gemini-') and 'image' not in key and any(k in quotas for k in ('gemini_session', 'gemini_weekly')):
                continue
            if key.startswith(('claude-', 'gpt-')) and any(k in quotas for k in ('claude_gpt_session', 'claude_gpt_weekly')):
                continue
        used, total = number(quota.get('used')), number(quota.get('total'))
        remaining = number(quota.get('remainingPercentage'))
        if remaining is None and used is not None and total is not None and total > 0:
            remaining = (1 - used / total) * 100
        if remaining is None and total is not None and total > 0 and number(quota.get('remaining')) is not None:
            remaining = quota['remaining'] / total * 100
        reset = quota.get('resetAt')
        result.append({
            'name': QUOTA_NAMES.get(key, str(quota.get('displayName') or key)),
            'remainingPercent': max(0, min(100, remaining)) if remaining is not None else None,
            'used': used, 'total': total, 'resetAt': reset if isinstance(reset, str) else None,
            'unlimited': quota.get('unlimited') is True,
            'neverExpires': quota.get('neverExpires') is True,
            'recurring': quota.get('recurring') is not False,
        })
    return result


def claude_reset_credits(usage):
    """Resets granted by Anthropic, read from the usage payload."""
    data = usage.get('resetCredits')
    if not isinstance(data, dict):
        return None
    credits = []
    for grant in data.get('grants') or []:
        if not isinstance(grant, dict) or grant.get('paused') is True or not isinstance(grant.get('endsAt'), str):
            continue
        left = number(grant.get('resetsLeft'))
        for index in range(int(left) if left and left > 0 else 0):
            credits.append({'expiresAt': grant['endsAt'], 'grantId': str(grant.get('id') or ''),
                            'key': f"{grant.get('id')}#{index}", 'usableNow': grant.get('usableNow') is not False,
                            'label': str(grant.get('label') or ''),
                            'clears': [field for field in (grant.get('clears') or []) if isinstance(field, str)]})
    weekly = data.get('weeklyResetsAt')
    cooldown = data.get('cooldownUntil')
    return {
        'available': number(data.get('availableCount')) or len(credits),
        'credits': sorted(credits, key=lambda credit: credit['expiresAt']),
        'cooldownUntil': cooldown if isinstance(cooldown, str) else None,
        'weeklyResetsAt': weekly if isinstance(weekly, str) else None,
    }

class QuotaService:
    def __init__(self, state_path=None):
        self.lock = asyncio.Lock()
        self.cached = None
        self.updated = float('-inf')
        self.state_path = Path(state_path) if state_path else None
        self.auto_disabled = {}
        self.reset_credits = {}
        if self.state_path and self.state_path.exists():
            # Refuse corrupt state rather than forgetting ownership of disabled
            # accounts. The worker reports the failure without changing logins.
            data = json.loads(self.state_path.read_text())
            if not isinstance(data, dict) or not isinstance(data.get('disabled'), dict):
                raise ValueError('Estado da automação de quotas inválido.')
            self.auto_disabled = data['disabled']

    def save_automation(self):
        if self.state_path:
            temporary = self.state_path.with_suffix('.tmp')
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, 'w') as output:
                json.dump({'disabled': self.auto_disabled}, output)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(self.state_path)

    async def request(self, session, path, method='GET', body=None):
        try:
            async with session.request(method, ROUTER_URL + path, headers=cli_headers(), json=body, timeout=ClientTimeout(total=20), allow_redirects=False) as response:
                if response.status in (401, 403):
                    raise RouterUnavailable('O 9router não autorizou a consulta. Verifique a conexão da conta.')
                if response.status >= 300:
                    raise RouterUnavailable('O 9router não conseguiu concluir a operação desta conta.')
                data = await response.json()
                if not isinstance(data, dict):
                    raise ValueError('Unexpected quota response')
                return data
        except (ClientError, TimeoutError, ValueError) as error:
            raise RouterUnavailable('Não foi possível consultar o 9router agora. Tente atualizar novamente.') from error

    async def codex_reset_credits(self, session, identity, force=False, fresh=False):
        """Read-only GET; the POST on the same route consumes a credit."""
        cached = self.reset_credits.get(identity)
        if cached and not fresh and time.monotonic() - cached[0] < (60 if force else RESET_CREDITS_TTL):
            return cached[1]
        try:
            data = await self.request(session, '/api/usage/' + quote(identity, safe='') + '/codex-reset-credits')
        except RouterUnavailable:
            # Keep the last known expiry rather than hiding the countdown.
            return cached[1] if cached else None
        credits = [
            {'expiresAt': credit['expiresAt']}
            for credit in data.get('credits') or []
            if isinstance(credit, dict) and credit.get('status') == 'available' and isinstance(credit.get('expiresAt'), str)
        ]
        result = {'available': number(data.get('availableCount')) or 0, 'credits': sorted(credits, key=lambda credit: credit['expiresAt'])}
        self.reset_credits[identity] = (time.monotonic(), result)
        return result

    async def due_reset_credits(self, session, state, save):
        """Warn about and consume Codex reset credits close to expiry.

        `state` maps account|expiry to what was done; `save` persists it and is
        called before each redeem POST so a timed-out request is never repeated
        blindly. Returns events for push notifications."""
        events = []
        async with self.lock:
            snapshot = await self._snapshot(session)
            now = time.time()
            for account in snapshot['accounts']:
                if account.get('providerId') not in ('codex', 'claude'):
                    continue
                for credit in (account.get('resetCredits') or {}).get('credits') or []:
                    try:
                        expires = datetime.fromisoformat(credit['expiresAt'].replace('Z', '+00:00')).timestamp()
                    except (ValueError, AttributeError):
                        continue
                    entry = state.setdefault(account['id'] + '|' + (credit.get('key') or credit['expiresAt']), {'expiresAt': credit['expiresAt'], 'warned': []})
                    left = expires - now
                    if left <= 0 or entry.get('done') or entry.get('attempts', 0) >= RESET_CREDIT_ATTEMPTS:
                        continue
                    if left <= RESET_CREDIT_REDEEM_BEFORE:
                        event = await self._redeem(session, account, credit, entry, save)
                        if event:
                            events.append(event)
                        continue
                    # Smallest window reached; the larger ones are marked too, so a late start sends one warning.
                    reached = [(limit, label) for limit, label in RESET_CREDIT_WARNINGS if left <= limit]
                    if reached:
                        limit, label = min(reached)
                        if label not in entry['warned']:
                            entry['warned'] = sorted({*entry['warned'], *(other for _, other in reached)})
                            events.append({'type': 'warning', 'account': account, 'expiresAt': credit['expiresAt'], 'label': label})
            cutoff = datetime.fromtimestamp(now - 86400, timezone.utc).isoformat()
            for key in [key for key, entry in state.items() if entry.get('expiresAt', '') < cutoff]:
                del state[key]
        save()
        return events

    async def _current_credits(self, session, account):
        if account.get('providerId') == 'claude':
            try:
                usage = await self.request(session, '/api/usage/' + quote(account['id'], safe='') + '?force=1')
            except RouterUnavailable:
                return None
            return claude_reset_credits(usage) or {'available': 0, 'credits': []}
        return await self.codex_reset_credits(session, account['id'], force=True, fresh=True)

    async def _redeem(self, session, account, credit, entry, save):
        identity = account['id']
        claude = account.get('providerId') == 'claude'
        if entry.get('attempts'):
            # The previous POST may have committed: redeem only if still listed.
            current = await self._current_credits(session, account)
            if current is None:
                return None
            field = 'key' if claude else 'expiresAt'
            if credit.get(field) not in [row.get(field) for row in current['credits']]:
                entry['done'] = 'gone'
                return None
        entry['attempts'] = entry.get('attempts', 0) + 1
        save()
        route = '/claude-reset' if claude else '/codex-reset-credits'
        body = {'json': {'grantId': credit.get('grantId')}} if claude else {}
        try:
            async with session.post(ROUTER_URL + '/api/usage/' + quote(identity, safe='') + route, headers=cli_headers(),
                                    timeout=ClientTimeout(total=60), allow_redirects=False, **body) as response:
                status = response.status
                try:
                    data = await response.json(content_type=None)
                except ValueError:
                    data = None
        except (ClientError, TimeoutError) as error:
            return {'type': 'failed', 'account': account, 'expiresAt': credit['expiresAt'], 'message': 'O 9router não respondeu (' + (str(error) or error.__class__.__name__) + ').'}
        finally:
            self.reset_credits.pop(identity, None)
            self.cached = None
        data = data if isinstance(data, dict) else {}
        if status < 300 and (data.get('ok') if claude else data.get('reset')):
            entry['done'] = 'redeemed'
            return {'type': 'redeemed', 'account': account, 'expiresAt': credit['expiresAt']}
        if status == 409 and not claude:
            # No credit left: used elsewhere or already expired.
            entry['done'] = 'gone'
            return None
        if claude and data.get('reason') in ('no_resets_left', 'grant_exhausted', 'grant_expired', 'not_found'):
            entry['done'] = 'gone'
            return None
        return {'type': 'failed', 'account': account, 'expiresAt': credit['expiresAt'], 'message': str(data.get('message') or data.get('error') or f'Resposta {status} do 9router.')}

    async def connections(self, session):
        connections = []
        page = 1
        while True:
            data = await self.request(session, f'/api/providers/client?page={page}&pageSize=100&accountStatus=all&sort=priority')
            connections.extend(data.get('connections') or [])
            if page >= data.get('pagination', {}).get('totalPages', 1):
                return connections
            page += 1

    async def reorder(self, session, provider, order, previous):
        if not isinstance(provider, str) or not isinstance(order, list) or not isinstance(previous, list) or not order or any(not isinstance(i, str) for i in [*order, *previous]) or len(set(order)) != len(order):
            raise ValueError('Ordem de contas inválida.')
        async with self.lock:
            snapshot = await self._snapshot(session)
            rows = [row for row in await self.connections(session) if row.get('provider') == provider]
            current = [row['id'] for row in rows]
            if set(order) != set(current) or previous != current:
                self.cached = None
                raise ValueError('As contas mudaram no 9router. Atualize as quotas antes de reordenar.')
            states = {row['id']: row['quotaState'] for row in snapshot['accounts']}
            adjusted = sorted(order, key=lambda identity: QUOTA_ORDER[states.get(identity, 'unknown')])
            await self._write_order(session, provider, rows, adjusted)
            return {'provider': provider, 'order': adjusted, 'adjusted': adjusted != order}

    async def _write_order(self, session, provider, rows, order):
        originals = {row['id']: row.get('priority', 1) for row in rows}
        attempted = []
        try:
            if order != [row['id'] for row in rows]:
                for priority, identity in enumerate(order, 1):
                    if originals[identity] != priority:
                        # Include timeouts: the upstream may have committed a write.
                        attempted.append(identity)
                        await self.request(session, '/api/providers/' + quote(identity, safe=''), 'PUT', {'priority': priority})
        except RouterUnavailable as error:
            restored = True
            for identity in reversed(attempted):
                try:
                    await self.request(session, '/api/providers/' + quote(identity, safe=''), 'PUT', {'priority': originals[identity]})
                except RouterUnavailable:
                    restored = False
            self.cached = None
            message = 'Não foi possível salvar. A ordem anterior foi restaurada.' if restored else 'A ordem foi salva parcialmente. Atualize as quotas para conferir o estado atual.'
            raise RouterUnavailable(message) from error
        if self.cached:
            cached_ids = {row['id'] for row in self.cached['accounts'] if row['providerId'] == provider}
            if cached_ids != set(order):
                self.cached = None
            else:
                for row in self.cached['accounts']:
                    if row['providerId'] == provider:
                        row['priority'] = order.index(row['id']) + 1
                self.cached['accounts'].sort(key=lambda row: (row['providerId'], row['priority']))

    async def reconcile(self, session):
        """Runs without an open browser. Shares the lock with manual reorders."""
        async with self.lock:
            snapshot = await self._snapshot(session)
            # Re-read activity and order after quota polling so a manual disable
            # during the network calls is not mistaken for our own operation.
            connections = await self.connections(session)
            accounts = {row['id']: row for row in snapshot['accounts']}
            changed = []
            live_ids = {row['id'] for row in connections}
            removed = set(self.auto_disabled) - live_ids
            for identity in removed:
                del self.auto_disabled[identity]
            if removed:
                self.save_automation()
            for connection in connections:
                identity = connection['id']
                row = accounts.get(identity)
                if not row:
                    continue
                row['active'] = connection.get('isActive') is not False
                row['priority'] = number(connection.get('priority')) or 0
                if row['quotaState'] == 'total' and row['active']:
                    self.auto_disabled[identity] = {'provider': row['providerId']}
                    # Persist before sending: a timeout may still commit the PUT.
                    self.save_automation()
                    await self.request(session, '/api/providers/' + quote(identity, safe=''), 'PUT', {'isActive': False})
                    row['active'] = False
                    changed.append({'id': identity, 'action': 'disabled'})
                elif identity in self.auto_disabled and row['totalAvailable'] is True:
                    if not row['active']:
                        await self.request(session, '/api/providers/' + quote(identity, safe=''), 'PUT', {'isActive': True})
                        row['active'] = True
                        changed.append({'id': identity, 'action': 'enabled'})
                    del self.auto_disabled[identity]
                    self.save_automation()
                row['autoDisabled'] = identity in self.auto_disabled
            for provider in dict.fromkeys(row['provider'] for row in connections):
                rows = [row for row in connections if row['provider'] == provider]
                if any(accounts.get(row['id'], {}).get('usageStale') for row in rows):
                    continue
                order = [row['id'] for row in sorted(rows, key=lambda row: QUOTA_ORDER[accounts.get(row['id'], {}).get('quotaState', 'unknown')])]
                if order != [row['id'] for row in rows]:
                    await self._write_order(session, provider, rows, order)
                    changed.append({'provider': provider, 'action': 'reordered'})
            return changed

    async def snapshot(self, session, force=False):
        async with self.lock:
            return await self._snapshot(session, force)

    async def _snapshot(self, session, force=False):
        # Caller holds the lock, including during automation writes.
        # Share results across phones and limit provider polling.
        if self.cached is not None and time.monotonic() - self.updated < (10 if force else 60):
            return self.cached
        await asyncio.to_thread(ensure_router)
        connections = await self.connections(session)
        settings = await self.request(session, '/api/settings')
        semaphore = asyncio.Semaphore(3)

        async def account(connection):
            provider = str(connection.get('provider') or '')
            result = {
                'id': str(connection.get('id') or ''),
                'provider': PROVIDER_NAMES.get(provider, provider),
                'providerId': provider,
                'priority': number(connection.get('priority')) or 0,
                'strategy': (settings.get('providerStrategies', {}).get(provider) or {}).get('fallbackStrategy', 'priority'),
                'name': str(connection.get('displayName') or connection.get('name') or connection.get('email') or PROVIDER_NAMES.get(provider, provider)),
                'active': connection.get('isActive') is not False,
                'plan': None, 'quotas': [], 'error': None,
                'usageStale': False, 'usageFetchedAt': None, 'usageRetryAt': None,
                'quotaState': 'unknown', 'totalAvailable': None,
                'autoDisabled': str(connection.get('id')) in self.auto_disabled,
                'resetCredits': None,
            }
            async with semaphore:
                try:
                    suffix = '?force=1' if force else ''
                    usage = await self.request(session, '/api/usage/' + quote(result['id'], safe='') + suffix)
                    result.update(quota_condition(usage, provider))
                    result['plan'] = usage.get('plan') if isinstance(usage.get('plan'), str) else None
                    result['quotas'] = normalize_quotas(usage, provider)
                    if provider == 'claude':
                        result['resetCredits'] = claude_reset_credits(usage)
                    result['usageStale'] = usage.get('usageStale') is True
                    for field in ('usageFetchedAt', 'usageRetryAt'):
                        result[field] = usage.get(field) if isinstance(usage.get(field), str) else None
                    if result['usageStale']:
                        status = (usage.get('usageError') or {}).get('status')
                        reason = 'A Anthropic limitou temporariamente a consulta de uso.' if status == 429 else 'A consulta de uso está temporariamente indisponível.'
                        if result['quotas']:
                            last_read = result['usageFetchedAt']
                            try:
                                last_read = datetime.fromisoformat(last_read.replace('Z', '+00:00')).astimezone().strftime('%d/%m às %H:%M')
                            except (ValueError, AttributeError):
                                last_read = None
                            reason += ' Saldo da última leitura' + (f' em {last_read}.' if last_read else '.')
                        result['error'] = reason + ' A atualização será tentada novamente após o tempo de espera.'
                    elif not result['quotas']:
                        result['error'] = 'O provedor não informou quotas para esta conta.'
                except RouterUnavailable as error:
                    result['error'] = str(error)
                if provider == 'codex' and result['id']:
                    result['resetCredits'] = await self.codex_reset_credits(session, result['id'], force)
            return result

        accounts = await asyncio.gather(*(account(connection) for connection in connections))
        self.cached = {'accounts': accounts, 'updatedAt': datetime.now(timezone.utc).isoformat()}
        self.updated = time.monotonic()
        return self.cached
