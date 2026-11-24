import json,os,pathlib,pty,select,subprocess,tempfile,time
from mobile_core import BASE,windows,tmux
original={w['id'] for w in windows()}
project=tempfile.mkdtemp(prefix='terminal-routing-qa-')
previous=(BASE/'projects.json').read_bytes() if (BASE/'projects.json').exists() else None
master,slave=pty.openpty()
process=subprocess.Popen([str(BASE/'venv/bin/python'),str(BASE/'route_cli.py'),'codex'],stdin=slave,stdout=slave,stderr=slave,cwd=project,start_new_session=True)
os.close(slave)
created=[]
try:
 for attempt in range(100):
  created=[w for w in windows() if w['id'] not in original and w['path']==project]
  if created:break
  if process.poll() is not None:raise RuntimeError('Roteador encerrou antes de abrir a sessão.')
  time.sleep(.1)
 assert len(created)==1,created
 for attempt in range(100):
  views=tmux('list-clients','-F','#{client_session}',check=False)
  if any(line.startswith('view-') for line in views.splitlines()):break
  time.sleep(.1)
 os.write(master,b'\x02d')
 process.wait(timeout=10)
 assert any(w['id']==created[0]['id'] for w in windows())
 print('OK: codex interativo apareceu no projeto correto; desconectar manteve a sessão aberta.')
 before={w['id'] for w in windows()}
 result=subprocess.run([str(BASE/'venv/bin/python'),str(BASE/'route_cli.py'),'codex','--version'],capture_output=True,text=True,timeout=20)
 assert result.returncode==0,(result.stdout,result.stderr)
 assert before=={w['id'] for w in windows()}
 print('OK: --version passa direto e não cria aba.')
finally:
 if process.poll() is None:process.terminate();process.wait(timeout=5)
 os.close(master)
 for w in windows():
  if w['id'] not in original and w['path']==project:tmux('kill-window','-t',w['id'],check=False)
 if previous is None:(BASE/'projects.json').unlink(missing_ok=True)
 else:(BASE/'projects.json').write_bytes(previous)
 pathlib.Path(project).rmdir()
