"""Guarded local fix for the published 9router 0.5.104 scheduler bundles."""
from pathlib import Path
import hashlib

HERE = Path(__file__).resolve().parent
REPLACEMENTS = [
    ('async function u(a,b,c,d){',
     'function G(a){return!!a&&!0!==a.unlimited&&!a.resetAt&&0===r(a.used)&&r(a.total,0)>0}async function u(a,b,c,d){'),
    ('c.skipWhenBlockingQuotaExhausted&&(k=c.quotaKey,',
     '(c.skipWhenBlockingQuotaExhausted||G(v))&&(k=c.quotaKey,'),
    ('let y=Date.now(),z=w?q(w):null,',
     'let I=G(v),J=I?Math.max(c.minPingIntervalMs||0,6e5):c.minPingIntervalMs;let y=Date.now(),z=w?q(w):null,'),
    ('if(t(p,c.minPingIntervalMs,y))return}else{if(!h||!w)return;',
     'if(t(p,J,y))return}else{if(!h||!w&&!I)return;if(!I){'),
    ('||t(p,c.minPingIntervalMs,y)||a===z)return}if(!await d.sendPing',
     '||t(p,J,y)||a===z)return}else if(t(p,J,y))return}if(!await d.sendPing'),
    ('`reset ${w}`', '`reset ${w||"idle window"}`'),
    ('lastPingAt:C,updatedAt:C}),console.log',
     'lastPingAt:C,updatedAt:C});if(I)try{let a=await d.getUsage(p.accessToken,n,{force:!0}),b=a?.quotas?.[c.quotaKey]?.resetAt;b&&(f.resetCache[l]=b)}catch{}console.log'),
]


def patched(source):
    for before, after in REPLACEMENTS:
        expected = 2 if before == '`reset ${w}`' else 1
        assert source.count(before) == expected, f'Unexpected bundle structure: {before}'
        source = source.replace(before, after)
    return source
