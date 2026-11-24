"""Web Push for the installed PWA. Shared by the gateway and the agent hooks."""
import base64
import fcntl
import json
import logging
import os
from pathlib import Path
import time

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02
from pywebpush import webpush, WebPushException

BASE = Path(__file__).resolve().parent
KEY = BASE / 'push-vapid.pem'
SUBSCRIPTIONS = BASE / 'push-subscriptions.json'
LOCK = BASE / 'push.lock'
# Tags still showing on the phones, so a clear is only sent when it removes something.
OPEN = BASE / 'push-open.json'
# Set a real contact URI before enabling Web Push.
CLAIMS = {'sub': os.environ.get('TERMINAL_MOBILE_PUSH_CONTACT', 'mailto:admin@example.com')}

log = logging.getLogger('push')

def private_write(path, text):
    temporary = path.with_suffix('.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        output.write(text)
    temporary.replace(path)

def vapid():
    with LOCK.open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not KEY.exists():
            key = Vapid02()
            key.generate_keys()
            private_write(KEY, key.private_pem().decode())
    return Vapid02.from_file(str(KEY))

def public_key():
    raw = vapid().public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()

def load():
    try:
        rows = json.loads(SUBSCRIPTIONS.read_text())
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []

def change(update):
    with LOCK.open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows = update(load())
        private_write(SUBSCRIPTIONS, json.dumps(rows))

def subscribe(subscription):
    keys = subscription.get('keys') if isinstance(subscription, dict) else None
    endpoint = subscription.get('endpoint') if isinstance(subscription, dict) else None
    if not isinstance(endpoint, str) or not endpoint.startswith('https://') or not isinstance(keys, dict) \
            or not all(isinstance(keys.get(k), str) for k in ('p256dh', 'auth')):
        raise ValueError('Inscrição de notificações inválida.')
    row = {'endpoint': endpoint, 'keys': {'p256dh': keys['p256dh'], 'auth': keys['auth']}}
    change(lambda rows: [r for r in rows if r['endpoint'] != endpoint] + [row])

def unsubscribe(endpoint):
    change(lambda rows: [r for r in rows if r['endpoint'] != endpoint])

def subscribed(endpoint):
    return any(r['endpoint'] == endpoint for r in load())

def open_tags(update=None):
    with LOCK.open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            tags = json.loads(OPEN.read_text())
        except (OSError, ValueError):
            tags = {}
        if update:
            tags = {t: v for t, v in update(tags).items() if time.time() - v < 86400}
            private_write(OPEN, json.dumps(tags))
    return tags

def forget(tags):
    """The phone already closed these (opened in the app); nothing to send."""
    open_tags(lambda current: {t: v for t, v in current.items() if t not in tags})

def clear(tag):
    """Removes a notification from the phones, e.g. after the conversation resumed.

    Android counts pushes that show nothing against a budget, so this only sends
    when the notification is still believed to be on screen."""
    removed = []

    def take(current):
        if tag in current:
            removed.append(tag)
        return {t: v for t, v in current.items() if t != tag}

    if tag not in open_tags():
        return 0
    open_tags(take)
    return deliver({'type': 'clear', 'tags': removed}) if removed else 0

def send(title, body, tag='', url='/', icon='/assets/icon-192.png'):
    if tag and tag != 'test':
        open_tags(lambda current: {**current, tag: time.time()})
    return deliver({'title': title, 'body': body, 'tag': tag, 'url': url, 'icon': icon})

def deliver(message):
    """Delivers to every registered device; returns how many accepted it."""
    rows = load()
    if not rows:
        return 0
    key = vapid()
    payload = json.dumps(message, ensure_ascii=False)
    delivered, gone = 0, set()
    for row in rows:
        try:
            # A finished turn is stale after an hour; the push service may drop it.
            webpush(row, payload, vapid_private_key=key, vapid_claims=dict(CLAIMS), ttl=3600, timeout=10,
                    headers={'Urgency': 'high'})
            delivered += 1
        except WebPushException as error:
            status = getattr(error.response, 'status_code', None)
            if status in (404, 410):
                gone.add(row['endpoint'])
            else:
                log.warning('Push recusado (%s): %s', status, error)
        except Exception as error:
            log.warning('Push falhou: %s', error)
    if gone:
        change(lambda current: [r for r in current if r['endpoint'] not in gone])
    return delivered
