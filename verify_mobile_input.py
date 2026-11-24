import asyncio,fcntl,json,pathlib,tempfile
from playwright.async_api import async_playwright
from mobile_core import BASE,tmux

async def main():
 credential=(BASE/'credentials').read_text().strip().split(':',1)
 project=tempfile.mkdtemp(prefix='terminal-input-qa-')
 created=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=['--no-sandbox','--ignore-certificate-errors'])
  context=await browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,device_scale_factor=2,http_credentials={'username':credential[0],'password':credential[1]},ignore_https_errors=True)
  page=await context.new_page();errors=[]
  page.on('pageerror',lambda error:errors.append(str(error)))
  origin='https://127.0.0.1:7682'
  try:
   response=await context.request.post(origin+'/api/projects',data={'path':project},headers={'Origin':origin});assert response.ok
   for _ in range(2):
    response=await context.request.post(origin+'/api/windows',data={'path':project,'agent':'shell'},headers={'Origin':origin});assert response.ok
    created.append((await response.json())['id'])
   await page.goto(origin)
   await page.get_by_role('button',name='Trocar de projeto').click()
   await page.locator('.project-row').filter(has_text=pathlib.Path(project).name).click()
   await page.wait_for_function('(path)=>terminalReady && selectedProject===path',arg=project)
   assert await page.locator('#composer, #message, #send').count()==0
   assert await page.locator('textarea').count()==1
   await page.locator('#terminal').tap(position={'x':120,'y':100})
   assert await page.evaluate('document.activeElement===terminal.textarea')
   await page.keyboard.type("printf 'DIRECT_INPUT_OK\\n'")
   await page.get_by_role('button',name='Enter',exact=True).click()
   await page.wait_for_function("Array.from({length:terminal.buffer.active.length},(_,i)=>terminal.buffer.active.getLine(i)?.translateToString()).some(line=>line?.trim()==='DIRECT_INPUT_OK')")
   assert await page.evaluate('document.activeElement===terminal.textarea')
   await page.get_by_role('button',name='Seta para cima').click()
   assert "printf 'DIRECT_INPUT_OK" in tmux('capture-pane','-p','-t',created[0])
   await page.get_by_role('button',name='Ctrl C',exact=True).click()
   await page.get_by_role('button',name='Aumentar fonte').click()
   assert await page.evaluate('document.activeElement===terminal.textarea')
   assert await page.evaluate('terminal.options.fontSize')==9
   print('OK: somente a entrada do terminal; digitação, Enter, histórico, Ctrl+C e fonte preservam o foco.')
   await page.locator('.tab').nth(1).click()
   await page.wait_for_function('(id)=>terminalReady && selectedWindow===id',arg=created[1])
   await page.locator('#terminal').tap(position={'x':120,'y':100})
   await page.keyboard.type("printf 'SECOND_TAB_OK\\n'")
   await page.get_by_role('button',name='Enter',exact=True).click()
   await page.wait_for_function("Array.from({length:terminal.buffer.active.length},(_,i)=>terminal.buffer.active.getLine(i)?.translateToString()).some(line=>line?.trim()==='SECOND_TAB_OK')")
   for width,height in [(390,420),(320,640),(844,390)]:
    await page.set_viewport_size({'width':width,'height':height});await page.wait_for_timeout(100)
    assert await page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    assert (await page.locator('#terminal').bounding_box())['height']>100
   await page.set_viewport_size({'width':390,'height':844})
   await page.screenshot(path=str(BASE/'mobile-direct-input.png'))
   await page.wait_for_function('navigator.serviceWorker.controller !== null')
   await page.wait_for_function("caches.keys().then(keys=>keys.includes('terminal-local-v4'))")
   await context.set_offline(True)
   await page.reload()
   await page.wait_for_function('typeof terminal!=="undefined"')
   assert await page.locator('#composer').count()==0
   assert await page.locator('.xterm-helper-textarea').count()==1
   assert not errors,errors
   print('OK: troca de abas, viewport reduzido pelo teclado e interface PWA em cache atualizada.')
  finally:
   await context.close();await browser.close()
   for identity in created:tmux('kill-window','-t',identity,check=False)
   with (BASE/'projects.lock').open('w') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    saved=BASE/'projects.json'
    if saved.exists():saved.write_text(json.dumps([path for path in json.loads(saved.read_text()) if path!=project]))
   pathlib.Path(project).rmdir()

asyncio.run(main())
