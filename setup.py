"""Create local credentials and certificates without overwriting existing secrets."""
import getpass
import ipaddress
import os
from pathlib import Path
import shutil
import subprocess
import sys

base = Path(__file__).resolve().parent
ip = str(ipaddress.IPv4Address(sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"))
os.umask(0o077)
if not (base / "credentials").exists():
    username = input("Login do painel: ").strip()
    password = getpass.getpass("Senha do painel (mínimo 16 caracteres): ")
    if not username or ":" in username or any(c in username + password for c in "\r\n") or len(password) < 16:
        sys.exit("Login inválido ou senha muito curta.")
    with (base / "credentials").open("x") as output:
        output.write(username + ":" + password + "\n")
if not (base / "ttyd").exists():
    executable = shutil.which("ttyd")
    if not executable:
        sys.exit("Instale ttyd >= 1.7.7 e execute este script novamente.")
    (base / "ttyd").symlink_to(Path(executable).resolve())
subprocess.run([sys.executable, str(base / "update_network.py"), ip], check=True)
print("Configuração pronta. Inicie com ./serve.sh")
