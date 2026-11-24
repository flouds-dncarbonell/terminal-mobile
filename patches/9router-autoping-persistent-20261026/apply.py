"""Repair compatible 9router schedulers; refuse unknown code before writing."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
MARKER = '/* terminal-mobile-idle-ping-v2 */'
spec = importlib.util.spec_from_file_location('idle_patch', HERE.parent / '9router-idle-ping-20261022/apply.py')
idle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(idle)


def transform_v119(text):
    replacements = [
        ('async function y(a,b,c,d,e,f=G,g=null,h=!0){', 'function idleWindow(a){return!!a&&!0!==a.unlimited&&!a.resetAt&&0===r(a.used)&&r(a.total,0)>0}async function y(a,b,c,d,e,f=G,g=null,h=!0){'),
        ('let r=await d.getUsage(p.accessToken,n),v=r?.quotas||{}', 'let r=await d.getUsage(p.accessToken,n);if(r?.usageStale)return;let v=r?.quotas||{}'),
        ('c.skipWhenBlockingQuotaExhausted&&(k=c.quotaKey,', '(c.skipWhenBlockingQuotaExhausted||idleWindow(w))&&(k=c.quotaKey,'),
        ('let z=Date.now(),A=x?q(x):null,', 'let idle=idleWindow(w),minInterval=idle?Math.max(c.minPingIntervalMs||0,6e5):c.minPingIntervalMs;let z=Date.now(),A=x?q(x):null,'),
        ('if(t(p,c.minPingIntervalMs,z))return}else{if(!h||!x)return;', 'if(t(p,minInterval,z))return}else{if(!h||!x&&!idle)return;if(!idle){'),
        ('||t(p,c.minPingIntervalMs,z)||a===A)return}let D=', '||t(p,minInterval,z)||a===A)return}else if(t(p,minInterval,z))return}let D='),
        ('`reset ${x}`', '`reset ${x||"idle window"}`'),
        ('lastPingAt:F,updatedAt:F}),console.log', 'lastPingAt:F,updatedAt:F});if(idle)try{let a=await d.getUsage(p.accessToken,n,{force:!0}),b=a?.quotas?.[c.quotaKey]?.resetAt;b&&(f.resetCache[l]=b)}catch{}console.log'),
    ]
    for before, after in replacements:
        expected = 2 if before == '`reset ${x}`' else 1
        assert text.count(before) == expected, f'Unsupported 0.5.119 scheduler: {before}'
        text = text.replace(before, after)
    return MARKER + '\n' + text


def transform(text):
    if MARKER in text:
        return text
    if 'async function y(a,b,c,d,e,f=G,g=null,h=!0){' in text:
        return transform_v119(text)
    if 'idle window' not in text:
        text = idle.patched(text)
    before = 'let r=await d.getUsage(p.accessToken,n),u=r?.quotas||{}'
    after = 'let r=await d.getUsage(p.accessToken,n);if(r?.usageStale)return;let u=r?.quotas||{}'
    if after not in text:
        assert text.count(before) == 1, 'Unsupported quota usage guard'
        text = text.replace(before, after)
    assert 'function y(' in text and 'runQuotaAutoPingTick:()=>y' in text
    return MARKER + '\n' + text


def prepare(app):
    chunks = app / '.next-cli-build/server/chunks'
    targets = [(p, p.read_text()) for p in sorted(chunks.glob('*.js'))
               if 'runQuotaAutoPingTick:' in p.read_text()]
    assert targets, 'Quota scheduler not found in installed 9router'
    prepared = []
    for path, original in targets:
        updated = transform(original)
        if updated != original:
            subprocess.run(['node', '--check'], input=updated, text=True,
                           capture_output=True, check=True, timeout=10)
        prepared.append((path, original, updated))
    return prepared


def apply(app):
    prepared = prepare(app)
    changed = []
    # Validate every target before replacing any file. Each replacement is atomic.
    for path, original, updated in prepared:
        if original == updated:
            continue
        digest = hashlib.sha256(original.encode()).hexdigest()[:16]
        backup = HERE / 'backups' / (path.name + '.' + digest)
        backup.parent.mkdir(exist_ok=True)
        if not backup.exists():
            backup.write_text(original)
        assert path.read_text() == original, '9router files changed during validation; retry'
        temporary = path.with_suffix('.autoping-tmp')
        temporary.write_text(updated)
        temporary.chmod(path.stat().st_mode)
        temporary.replace(path)
        changed.append(path.name)
    return changed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        prepare(args.app)
        print('All scheduler bundles are compatible')
    else:
        print('Scheduler bundles repaired:', ', '.join(apply(args.app)) or 'already current')
