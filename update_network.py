"""Create a private LAN CA once and renew the host certificate if its IP changes."""
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
from mobile_core import BASE

ip = str(ipaddress.IPv4Address(sys.argv[1]))
certs = BASE / 'certs'
certs.mkdir(mode=0o700, exist_ok=True)
os.umask(0o077)


def openssl(*args):
    subprocess.run(['openssl', *map(str,args)], cwd=certs, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if not (certs / 'rootCA.key').exists():
    openssl('req', '-x509', '-newkey', 'rsa:3072', '-sha256', '-nodes', '-days', '3650', '-keyout', 'rootCA.key', '-out', 'rootCA.crt', '-subj', '/CN=Terminal Local CA', '-addext', 'basicConstraints=critical,CA:TRUE,pathlen:0', '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
try:
    previous = json.loads((BASE / 'network.json').read_text())
except (OSError, ValueError):
    previous = {}
validity = subprocess.run(['openssl', 'x509', '-in', str(certs / 'server.crt'), '-noout', '-checkend', '2592000'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
if previous.get('ip') == ip and validity == 0:
    print('unchanged')
    sys.exit(0)
openssl('req', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'server.key', '-out', 'server.csr', '-subj', '/CN=Terminal Local')
(certs / 'server.ext').write_text(f'subjectAltName=IP:{ip},IP:127.0.0.1,DNS:localhost\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n')
openssl('x509', '-req', '-in', 'server.csr', '-CA', 'rootCA.crt', '-CAkey', 'rootCA.key', '-CAcreateserial', '-out', 'server.crt', '-days', '365', '-sha256', '-extfile', 'server.ext')
temporary = BASE / 'network.json.tmp'
temporary.write_text(json.dumps({'ip':ip, 'tls_port':7682}))
temporary.replace(BASE / 'network.json')
print('updated')
