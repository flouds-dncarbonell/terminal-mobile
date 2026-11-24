"""Agent hooks -> Web Push on the installed PWA.

Claude: `notify_hook.py claude <Stop|Notification|PreToolUse|PostToolUse|UserPromptSubmit>`
with the hook JSON on stdin. The last two remove the terminal's pending push.
Codex: `notify_hook.py codex [json]`; `notify` passes the JSON as an argument,
hooks.json passes it on stdin. Never fails the agent: errors go to stderr.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlencode

import push

RECENT = push.BASE / 'push-recent.json'
NAMES = {'claude': 'Claude', 'codex': 'Codex'}

def sentence(text, limit=220):
    """First paragraph, trimmed at a sentence end when it runs long."""
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', str(text or ''))
    text = re.sub(r'[*`#>]', '', text).strip()
    text = ' '.join(re.split(r'\n\s*\n', text)[0].split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind('. '), cut.rfind('! '), cut.rfind('? '))
    return cut[:end + 1] if end > limit // 3 else cut.rsplit(' ', 1)[0] + '…'

def last_assistant(transcript):
    try:
        lines = Path(transcript).read_text().splitlines()
    except (OSError, TypeError):
        return ''
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get('type') == 'assistant':
            texts = [c.get('text', '') for c in row.get('message', {}).get('content', []) if isinstance(c, dict) and c.get('type') == 'text']
            if any(texts):
                return '\n'.join(texts)
    return ''

def first_question(payload):
    """The question plus its choices, so it can be read without opening the app."""
    questions = (payload.get('tool_input') or {}).get('questions')
    if not isinstance(questions, list) or not questions or not isinstance(questions[0], dict):
        return ''
    question = sentence(questions[0].get('question') or questions[0].get('prompt') or '')
    labels = [o.get('label') for o in questions[0].get('options') or [] if isinstance(o, dict) and o.get('label')]
    if labels:
        question += '\n' + ' · '.join(re.sub(r'\s*\(Recommended\)', '', label) for label in labels[:4])
    if len(questions) > 1:
        question += f'\n+{len(questions) - 1} pergunta(s)'
    return question

def internal_message(text):
    """Structured output from Codex side turns (e.g. {"summary": ...}) is not for the user."""
    text = str(text or '').strip()
    if not text.startswith('{'):
        return False
    try:
        return isinstance(json.loads(text), dict)
    except ValueError:
        return False

def tmux(*args):
    return subprocess.run(['tmux', '-L', 'terminal-mobile-test', *args], capture_output=True, text=True, timeout=5).stdout

def panel_windows():
    rows = []
    for line in tmux('list-windows', '-t', 'agentes', '-F', '#{window_id}\t#{pane_id}\t#{@agent}\t#{@project_path}\t#{pane_title}').splitlines():
        fields = line.split('\t', 4)
        if len(fields) == 5:
            rows.append(dict(zip(('id', 'pane', 'agent', 'project', 'title'), fields)))
    return rows

def thread_name(thread):
    """Latest name Codex gave the thread (session_index.jsonl), '' when unknown."""
    name = ''
    if not thread:
        return name
    try:
        with (Path.home() / '.codex' / 'session_index.jsonl').open() as index:
            for line in index:
                if thread in line:
                    try:
                        name = json.loads(line).get('thread_name') or name
                    except ValueError:
                        pass
    except OSError:
        pass
    return name.strip()

def panel_window(agent, payload):
    """(window, project) of the terminal that raised the event, '' when unknown."""
    rows = panel_windows()
    if agent == 'claude':
        # Claude runs its hooks inside the pane, so the pane is exact.
        pane = os.environ.get('TMUX_PANE', '')
        if pane and push.BASE.name in os.environ.get('TMUX', ''):
            row = next((r for r in rows if r['pane'] == pane), None)
            if row:
                return row['id'], row['project']
        return '', ''
    # Codex runs hooks in a shared background server whose environment points at
    # whichever tab started it, so match by folder and, if needed, by screen text.
    cwd = payload.get('cwd') or ''
    candidates = [r for r in rows if r['agent'] == 'codex' and r['project'] == cwd]
    if len(candidates) == 1:
        return candidates[0]['id'], cwd
    # Codex titles the pane "<status> | <thread name> | <folder>", so the thread
    # name tells apart two tabs in the same folder.
    name = thread_name(payload.get('thread-id') or payload.get('session_id'))
    named = [r for r in candidates if name and f'{name} | ' in r['title'] + ' | ']
    if len(named) == 1:
        return named[0]['id'], cwd
    clues = [str(m) for m in (payload.get('input-messages') or [])[-1:]] + [first_question(payload).split('\n')[0]]
    clues = [' '.join(c.split())[:60] for c in clues if c and len(c.strip()) > 12]
    matches = []
    for row in candidates:
        screen = ' '.join(tmux('capture-pane', '-p', '-J', '-S', '-300', '-t', row['pane']).split())
        if any(clue in screen for clue in clues):
            matches.append(row)
    return (matches[0]['id'], cwd) if len(matches) == 1 else ('', '')

def tab_label(agent, window, project):
    """'Claude 2' when the project has more than one tab of that agent, like the panel."""
    name = NAMES[agent]
    siblings = [r['id'] for r in panel_windows() if r['agent'] == agent and r['project'] == project]
    return f'{name} {siblings.index(window) + 1}' if window in siblings and len(siblings) > 1 else name

ANSWER_TOOLS = ('AskUserQuestion', 'ExitPlanMode', 'request_user_input')

def describe(agent, event, payload):
    """Returns (kind, title, body) or None for events that need no push."""
    hook = payload.get('hook_event_name') or event
    # The conversation moved on: earlier pushes for this terminal are stale.
    if hook in ('UserPromptSubmit', 'Interrupt', 'SessionEnd') or hook == 'PostToolUse' and payload.get('tool_name') in ANSWER_TOOLS:
        return 'clear', '', ''
    # /clear (and a new or resumed session in the same tab) starts over; compaction does not.
    if hook == 'SessionStart' and payload.get('source') != 'compact':
        return 'clear', '', ''
    if agent == 'claude' and hook == 'Stop':
        text = payload.get('last_assistant_message') or last_assistant(payload.get('transcript_path'))
        return 'done', 'terminou', sentence(text) or 'Aguardando sua resposta.'
    if agent == 'codex' and payload.get('type') == 'agent-turn-complete':
        text = payload.get('last-assistant-message')
        if internal_message(text):
            return None
        return 'done', 'terminou', sentence(text) or 'Aguardando sua resposta.'
    if hook == 'Notification':
        message = payload.get('message') or ''
        # Idle reminders repeat the Stop push a minute later.
        if payload.get('notification_type') == 'idle_prompt' or 'waiting for your input' in message:
            return None
        return 'ask', 'precisa de você', sentence(message) or 'Abra a sessão para continuar.'
    if hook == 'PreToolUse':
        tool = payload.get('tool_name')
        if tool == 'ExitPlanMode':
            return 'ask', 'tem um plano para aprovar', 'O plano está pronto para sua revisão.'
        if tool in ('AskUserQuestion', 'request_user_input'):
            return 'ask', 'fez uma pergunta', first_question(payload) or 'Abra a sessão para responder.'
        return None
    if hook == 'PermissionRequest':
        return 'ask', 'precisa da sua aprovação', 'Abra a sessão para aprovar ou recusar.'
    return None

def recently_sent(key, seconds=15):
    """A question often raises two hooks (tool + notification); buzz once."""
    with (push.BASE / 'push.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            recent = json.loads(RECENT.read_text())
        except (OSError, ValueError):
            recent = {}
        now = time.time()
        recent = {k: v for k, v in recent.items() if now - v < 3600}
        duplicate = now - recent.get(key, 0) < seconds
        if not duplicate:
            recent[key] = now
        push.private_write(RECENT, json.dumps(recent))
    return duplicate

def main():
    agent = sys.argv[1]
    event = sys.argv[2] if agent == 'claude' and len(sys.argv) > 2 else ''
    raw = sys.argv[2] if agent == 'codex' and len(sys.argv) > 2 else sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    described = describe(agent, event, payload)
    if not described:
        return
    kind, action, body = described
    window, project = panel_window(agent, payload)
    project = project or payload.get('cwd') or os.getcwd()
    identity = window or payload.get('session_id') or payload.get('thread-id') or project
    tag = f'term:{identity}'
    if kind == 'clear':
        push.clear(tag)
        return
    if kind == 'ask' and recently_sent(f'ask:{identity}'):
        return
    query = {'project': project, **({'window': window} if window else {})}
    title = f'{tab_label(agent, window, project)} {action} · {Path(project).name}'
    push.send(title, body, tag=tag, url='/?' + urlencode(query), icon=f'/assets/notify-{agent}.png')

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'terminal-mobile push failed: {error}', file=sys.stderr)
