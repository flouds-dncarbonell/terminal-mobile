"""Local, read-only monitoring. Silence is never evidence that an agent stopped."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

from mobile_core import BASE, tmux, windows


def confirmation_visible(screen):
    # Only inspect the bottom of the visible screen, never terminal history.
    lines = [line.strip() for line in screen.splitlines() if line.strip()][-20:]
    text = '\n'.join(lines)
    options = len(re.findall(r'(?m)^[›❯>\s]*\d+[.)]\s+(?:Yes|No|Allow|Deny|Sim|Não|Approve)\b', text, re.I)) >= 2
    question = re.search(r'(?:would you like to (?:run|make|apply|proceed)|do you want to (?:proceed|allow|make|run|execute|create|edit|update|delete|continue)|do you trust|allow .+\?|allow this|approve this|deseja (?:continuar|permitir|executar))', text, re.I)
    submit = re.search(r'(?:enter to (?:confirm|select|submit)|press enter to|esc to cancel)', '\n'.join(lines[-4:]), re.I)
    return bool(options and question and submit)


def codex_working(screen):
    lines = [line for line in screen.splitlines() if line.strip()][-8:]
    return any('esc to interrupt' in line for line in lines)

def process_tree():
    rows = subprocess.run(['ps', '-eo', 'pid=,ppid=,stat=,comm='], check=True,
                          capture_output=True, text=True).stdout
    processes, children = {}, {}
    for line in rows.splitlines():
        fields = line.split(None, 3)
        if len(fields) != 4:
            continue
        pid, parent, status, command = fields
        pid, parent = int(pid), int(parent)
        processes[pid] = (status, command)
        children.setdefault(parent, []).append(pid)
    return processes, children


def agent_process(root, agent, processes, children):
    # The pane command is often the Python launcher or bash; find the agent itself.
    pending, visited = [root], set()
    candidates = []
    while pending:
        pid = pending.pop(0)
        if pid in visited:
            continue
        visited.add(pid)
        status, command = processes.get(pid, ('', ''))
        if command == agent and not status.startswith(('Z', 'X')):
            candidates.append((pid, status))
        pending.extend(children.get(pid, []))
    # A shell can retain a stopped job after another agent is opened. Prefer a
    # live agent, then the terminal's foreground job (ps marks it with '+').
    return max(candidates, key=lambda process: (
        not process[1].startswith(('T', 't')), '+' in process[1]
    ), default=None)


class AttentionMonitor:
    def __init__(self, path=BASE / 'attention-state.json'):
        self.path = Path(path)
        self.boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        try:
            saved = json.loads(self.path.read_text())
            self.entries = saved['entries'] if saved['boot'] == self.boot else {}
        except (OSError, ValueError, KeyError):
            self.entries = {}
        self.alerts = []
        self.working = set()
        # Tabs closed from the panel: no "Esta aba foi fechada" alert for them.
        self.closing = set()

    def scan(self):
        running = windows()
        processes, children = process_tree()
        now = time.time()
        present = set()
        self.working = set()
        for window in running:
            identity = window['id'] + ':' + window['pane']
            present.add(identity)
            entry = self.entries.setdefault(identity, {'first_seen': now, 'kind': 'running'})
            entry.update(window=window['id'], project=window['path'], name=window['name'], agent=window['agent'])
            kind, message = 'running', ''
            process = agent_process(window['pid'], window['agent'], processes, children) if window['agent'] != 'shell' else None
            if window['dead']:
                kind, message = 'exited', 'O processo do terminal foi encerrado.'
            elif process:
                entry['seen_agent'] = True
                entry['agent_pid'] = process[0]
                if process[1].startswith(('T', 't')):
                    kind, message = 'suspended', 'O agente está suspenso. Verifique o terminal.'
                else:
                    screen = tmux('capture-pane', '-p', '-J', '-t', window['pane'], check=False)
                    # Claude keeps this hint while idle, so only Codex is trusted here.
                    if window['agent'] == 'codex' and codex_working(screen):
                        self.working.add(window['id'])
                    if confirmation_visible(screen):
                        kind, message = 'attention', 'Possível pedido de confirmação. Verifique o terminal.'
            elif window['agent'] != 'shell' and (entry.get('seen_agent') or now - entry['first_seen'] > 10):
                kind, message = 'exited', 'O agente foi encerrado; a aba pode continuar aberta no shell.'
            known_exit = window['dead'] or window.get('exit_pid') and (
                not entry.get('seen_agent') or entry.get('agent_pid') == window['exit_pid'])
            if kind == 'exited' and window['exit_code'] and known_exit:
                message += ' Código de saída: ' + window['exit_code'] + '.'

            # Debounce redraws of confirmation menus; process exits are immediate.
            if kind != entry.get('candidate'):
                entry['candidate'], entry['candidate_since'] = kind, now
            if kind == 'attention' or entry['kind'] == 'attention' and kind == 'running':
                if now - entry['candidate_since'] < 2:
                    if kind == 'attention' and entry['kind'] != 'attention':
                        self.transition(entry, 'running', '', now)
                    continue
            self.transition(entry, kind, message, now)

        for identity, entry in list(self.entries.items()):
            if identity not in present:
                if entry['window'] in self.closing or not Path(entry['project']).is_dir():
                    del self.entries[identity]
                    continue
                self.transition(entry, 'closed', 'Esta aba foi fechada.', now)
                if now - entry['since'] > 86400:
                    del self.entries[identity]
        self.alerts = [dict(id=e['event'], window=e['window'], project=e['project'],
                            name=e['name'], agent=e['agent'], kind=e['kind'], message=e['message'],
                            since=e['since']) for e in self.entries.values() if e['kind'] != 'running']
        self.alerts.sort(key=lambda e: e['since'], reverse=True)
        saved = json.dumps({'boot': self.boot, 'entries': self.entries}, ensure_ascii=False)
        if not self.path.exists() or self.path.read_text() != saved:
            temporary = self.path.with_suffix('.tmp')
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as output:
                output.write(saved)
            temporary.replace(self.path)

    @staticmethod
    def transition(entry, kind, message, now):
        if entry['kind'] != kind:
            entry.update(kind=kind, event=uuid.uuid4().hex, since=now, message=message)
        elif kind != 'running':
            entry['message'] = message

    def snapshot(self):
        return copy.deepcopy(self.alerts)
