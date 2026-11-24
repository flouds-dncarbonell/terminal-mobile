"""Guarded, idempotent patch for 9router's published Claude usage bundle.

The npm package ships a compiled usage service rather than its source. Keep
the original parser/reset-credit behavior and replace only caching and errors.
"""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent

MARKER = '/* claude-usage-cache-fix-20261025 */'


def patch_usage(text):
    if MARKER in text:
        return text
    start = text.index('69788:(a,b,c)=>{')
    end = text.index('}},85081:', start) + 2
    module = text[start:end]
    assert module.count('async function j(') == 1
    a = module.index('async function j(')
    b = module.index('async function k(', a)
    module = module[:a] + MARKER + '\n' + (HERE / 'cache.js').read_text() + module[b:]
    before = 'let c=h.get(a);if(c&&Date.now()<c)return await m(a,b);'
    assert module.count(before) == 1
    module = module.replace(before, '')
    module = module.replace('},h=new Map,i=new Map;', '},i=new Map;')
    before = '"User-Agent":g.userAgent}},b);if(e.ok)'
    assert module.count(before) == 1
    module = module.replace(before, '"User-Agent":g.userAgent},signal:AbortSignal.timeout(15000)},b);if(e.ok)')
    before = 'return 429===e.status&&h.set(a,Date.now()+18e4),console.warn(`[Claude Usage] OAuth endpoint returned ${e.status}, falling back to legacy`),await m(a,b)}catch(a){return{message:`Claude connected. Unable to fetch usage: ${a.message}`}}'
    assert module.count(before) == 1
    module = module.replace(before, '''const retry=e.headers?.get?.("retry-after");
let retryMs=0;
if(retry){const seconds=Number(retry);retryMs=Number.isFinite(seconds)?Math.max(0,seconds*1000):Math.max(0,Date.parse(retry)-Date.now())||0;}
throw Object.assign(new Error(`Claude usage HTTP ${e.status}`),{status:e.status,retryAfterMs:retryMs});
}catch(error){throw error;}''')
    # The legacy /v1/settings endpoint returns 404 for these OAuth accounts.
    legacy = module.index('async function m(a,b=null){')
    module = module[:legacy] + '}'
    assert 'falling back to legacy' not in module
    return text[:start] + module + text[end:]


def patch_scheduler(text):
    before = 'let r=await d.getUsage(p.accessToken,n),u=r?.quotas||{}'
    after = 'let r=await d.getUsage(p.accessToken,n);if(r?.usageStale)return;let u=r?.quotas||{}'
    if after in text:
        return text
    assert text.count(before) == 1, 'Unsupported quota scheduler build'
    return text.replace(before, after)


def apply(app):
    chunks = app / '.next-cli-build/server/chunks'
    # Prepare and validate all edits before writing any bundle.
    usage = [(p, p.read_text()) for p in chunks.glob('*.js')
             if re.search(r'69788:\(a,b,c\)=>\{', p.read_text())]
    assert len(usage) == 1, 'Unsupported or ambiguous Claude usage module'
    prepared = [(p, text, patch_usage(text)) for p, text in usage]
    for name in ('6877.js', '8363.js'):
        path = chunks / name
        text = path.read_text()
        prepared.append((path, text, patch_scheduler(text)))
    source = app / 'src/shared/services/quotaAutoPing.js'
    if source.exists():
        text = source.read_text()
        before = 'const usage = await handler.getUsage(connection.accessToken, proxyOptions);'
        after = before + '\n  if (usage?.usageStale) return;'
        assert before in text
        prepared.append((source, text, text if after in text else text.replace(before, after)))
    for path, original, updated in prepared:
        if original == updated:
            continue
        subprocess.run(['node', '--check', '--input-type=' + ('module' if path == source else 'commonjs')],
                       input=updated, text=True, check=True, capture_output=True)
    for path, original, updated in prepared:
        if original == updated:
            continue
        digest = hashlib.sha256(original.encode()).hexdigest()[:16]
        backup = HERE / 'backups' / (path.name + '.' + digest)
        backup.parent.mkdir(exist_ok=True)
        if not backup.exists():
            backup.write_text(original)
        temporary = path.with_suffix(path.suffix + '.usage-fix-tmp')
        temporary.write_text(updated)
        temporary.chmod(path.stat().st_mode)
        temporary.replace(path)
        print('Patched', path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    apply(parser.parse_args().app)
