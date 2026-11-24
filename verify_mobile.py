import asyncio,json,pathlib,subprocess,tempfile
from playwright.async_api import async_playwright
from mobile_core import BASE,tmux

async def main():
 credential=(BASE/'credentials').read_text().strip().split(':',1)
 original_windows={w['id'] for w in __import__('mobile_core').windows()}; test_project=tempfile.mkdtemp(prefix='terminal-mobile-qa-')
 previous_projects=(BASE/'projects.json').read_bytes() if (BASE/'projects.json').exists() else None
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=['--no-sandbox','--ignore-certificate-errors'])
  context=await browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,device_scale_factor=2,http_credentials={'username':credential[0],'password':credential[1]},ignore_https_errors=True)
  page=await context.new_page();errors=[]
  page.on('pageerror',lambda error:errors.append(str(error)))
  async def ready():await page.wait_for_function('terminalReady === true',timeout=20000)
  try:
   await page.goto('https://127.0.0.1:17684/');await ready()
   assert await page.locator('.tab.active').inner_text()=='Codex'
   await page.get_by_role('button',name='Claude',exact=True).click();await ready()
   assert await page.locator('.tab.active').inner_text()=='Claude'
   await page.get_by_role('button',name='Aumentar fonte').click()
   assert await page.evaluate('terminal.options.fontSize')==9
   await page.get_by_role('button',name='Novo terminal',exact=True).click()
   await page.locator('#agent-dialog [data-launch="shell"]').click()
   await page.wait_for_function('terminalReady && currentProject()?.windows.find(w=>w.id===selectedWindow)?.agent === "shell"')
   await page.wait_for_function("Array.from({length:terminal.buffer.active.length},(_,i)=>terminal.buffer.active.getLine(i)?.translateToString()).some(line=>line?.includes('$'))",timeout=120000)
   await page.locator('.xterm-helper-textarea').focus();await page.keyboard.type("printf 'MOBILE_OK\\n'")
   await page.get_by_role('button',name='Enter',exact=True).click()
   await page.wait_for_function("Array.from({length:terminal.buffer.active.length},(_,i)=>terminal.buffer.active.getLine(i)?.translateToString()).some(line=>line?.trim()==='MOBILE_OK')")
   print('OK: troca Codex/Claude, fonte e comando enviado diretamente no terminal.')
   await page.get_by_role('button',name='Trocar de projeto').click()
   await page.get_by_role('button',name='Adicionar uma pasta').click()
   await page.locator('#folder-path').fill(test_project)
   await page.get_by_role('button',name='Ir',exact=True).click()
   await page.wait_for_function('(expected)=>folderPath===expected',arg=test_project)
   await page.get_by_role('button',name='Usar esta pasta').click()
   await page.wait_for_function('(expected)=>selectedProject===expected',arg=test_project)
   assert await page.locator('#empty').is_visible()
   await page.get_by_role('button',name='Novo terminal',exact=True).click()
   await page.locator('#agent-dialog [data-launch="shell"]').click()
   await page.wait_for_function('terminalReady && currentProject()?.windows.find(w=>w.id===selectedWindow)?.agent === "shell"')
   await page.locator('.xterm-helper-textarea').focus();await page.keyboard.type('pwd')
   await page.get_by_role('button',name='Enter',exact=True).click()
   await page.wait_for_function('(expected)=>Array.from({length:terminal.buffer.active.length},(_,i)=>terminal.buffer.active.getLine(i)?.translateToString()).some(line=>line?.trim()===expected)',arg=test_project)
   print('OK: adicionou outro projeto; terminal iniciou na pasta correta.')
   await page.get_by_role('button',name='Trocar de projeto').click()
   await page.locator('.project-row').filter(has_text='mistureba').click();await ready()
   await page.get_by_role('button',name='Codex',exact=True).click();await ready()
   await page.screenshot(path=str(BASE/'mobile-preview.png'))
   assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
   for width,height in [(320,740),(844,390),(1280,800)]:
    await page.set_viewport_size({'width':width,'height':height});await page.wait_for_timeout(150)
    assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),str(width)
   await page.wait_for_function('navigator.serviceWorker.controller !== null',timeout=20000)
   manifest=await page.evaluate("fetch('/manifest.webmanifest').then(r=>r.json())")
   assert manifest['display']=='standalone' and len(manifest['icons'])==2
   assert not errors,errors
   print('OK: sem overflow em 320, 390, 844 e 1280 px; manifest e service worker ativos.')
   # A second browser must select its own window without changing the first client.
   await page.set_viewport_size({'width':390,'height':844})
   other=await context.new_page();await other.goto('https://127.0.0.1:17684/')
   await other.wait_for_function('terminalReady === true')
   await other.get_by_role('button',name='Claude',exact=True).click();await other.wait_for_function('terminalReady === true')
   assert await page.evaluate("Array.from({length:terminal.buffer.active.length},(_,i)=>terminal.buffer.active.getLine(i)?.translateToString()).join(String.fromCharCode(10)).includes('Codex')")
   print('OK: dois clientes podem selecionar abas diferentes.')
   response=await context.request.post('https://127.0.0.1:17684/api/windows',data={'path':test_project,'agent':'shell'},headers={'Origin':'https://evil.example'})
   assert response.status==403
   print('OK: origem externa bloqueada para criação de terminal.')
  except Exception:
   print('DEBUG',await page.evaluate('({selectedWindow,terminalReady,opening,text:Array.from({length:terminal.buffer.active.length},(_,i)=>terminal.buffer.active.getLine(i)?.translateToString()).join("\\n")})'),flush=True)
   await page.screenshot(path=str(BASE/'failure.png'))
   raise
  finally:
   await context.close();await browser.close()
   for window in __import__('mobile_core').windows():
    if window['id'] not in original_windows and window['agent']=='shell':tmux('kill-window','-t',window['id'],check=False)
   if previous_projects is None:(BASE/'projects.json').unlink(missing_ok=True)
   else:(BASE/'projects.json').write_bytes(previous_projects)
   pathlib.Path(test_project).rmdir()

asyncio.run(main())
