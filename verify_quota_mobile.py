"""Mobile browser QA: real reads; reorder writes are intercepted fixtures."""
import asyncio
import copy
import json
from datetime import datetime, timezone, timedelta

from playwright.async_api import async_playwright
from mobile_core import BASE

URL = 'http://127.0.0.1:17781/'


async def main():
    username, password = (BASE/'credentials').read_text().strip().split(':', 1)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width':390,'height':844}, is_mobile=True, has_touch=True,
                                            http_credentials={'username':username,'password':password})
        page = await context.new_page(); errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(URL)
        await page.wait_for_function('terminalReady')
        generation = await page.evaluate('terminalGeneration')
        index = await page.evaluate('currentProject().windows.findIndex(w=>w.id===selectedWindow)')
        await page.get_by_role('button', name='Quotas', exact=True).click()
        await page.wait_for_function('quotaSnapshot !== null && !quotaBusy', timeout=60000)
        assert await page.locator('.quota-account').count() >= 1
        assert await page.locator('.controls').is_hidden()
        assert await page.evaluate('terminalReady && terminalGeneration') == generation
        await page.screenshot(path=str(BASE/'quota-mobile.png'))
        for width in (320,390,1280):
            await page.set_viewport_size({'width':width,'height':844})
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        await page.set_viewport_size({'width':390,'height':844})
        await page.locator('.tab-list .tab').nth(index).click()
        assert await page.locator('#terminal').is_visible()
        assert await page.evaluate('terminalReady && terminalGeneration') == generation
        assert not errors, errors
        await context.close()
        print('OK: quotas reais; layouts 320/390/1280 px; alternar abas preserva o terminal.')

        reset = (datetime.now(timezone.utc)+timedelta(hours=3)).isoformat()
        def account(identity,priority,provider='codex'):
            return {'id':identity, 'providerId':provider, 'provider':provider.title(), 'name':'Conta '+identity.upper(),
                    'priority':priority, 'strategy':'priority', 'active':True, 'plan':'Plus', 'error':None,
                    'quotas':[{'name':'Sessão · 5 horas','remainingPercent':13 if identity=='a' else 80,
                               'resetAt':reset,'unlimited':False,'neverExpires':False,'recurring':True}]}
        fixture={'accounts':[account('a',1),account('b',2),account('c',3),account('x',1,'claude')],
                 'updatedAt':datetime.now(timezone.utc).isoformat()}
        writes=[]; fail=False; fail_write=False
        async def intercept(route):
            nonlocal fail,fail_write
            if route.request.url.split('?')[0].endswith('/order'):
                body=route.request.post_data_json; writes.append(body)
                if fail_write:
                    return await route.fulfill(status=503,json={'error':'Não foi possível salvar a ordem.'})
                states={row['id']:row.get('quotaState') for row in fixture['accounts']}
                applied=sorted(body['order'],key=lambda identity:{'session':1,'total':2}.get(states[identity],0))
                for row in fixture['accounts']:
                    if row['providerId']==body['provider']:row['priority']=applied.index(row['id'])+1
                return await route.fulfill(json={'provider':body['provider'],'order':applied,'adjusted':applied!=body['order']})
            if fail:return await route.fulfill(status=503,json={'error':'9router indisponível para teste.'})
            await route.fulfill(json=copy.deepcopy(fixture))
        context=await browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,
                                         http_credentials={'username':username,'password':password})
        await context.route('**/api/quotas**',intercept)
        page=await context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto(URL);await page.wait_for_function('terminalReady')
        await page.get_by_role('button',name='Quotas',exact=True).click()
        await page.wait_for_function('quotaSnapshot !== null && !quotaBusy')
        await page.get_by_role('button',name='Descer Conta A',exact=True).click()
        await page.wait_for_function('!quotaSaving')
        assert writes[-1]=={'provider':'codex','order':['b','a','c'],'previous':['a','b','c']}
        # Real touch input, rather than HTML drag events that do not work on phones.
        first=page.locator('[data-provider="codex"] .quota-account').nth(0)
        second=page.locator('[data-provider="codex"] .quota-account').nth(1)
        handle=await first.locator('.quota-handle').bounding_box()
        target=await second.bounding_box()
        cdp=await context.new_cdp_session(page)
        x=handle['x']+handle['width']/2;y=handle['y']+handle['height']/2
        await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
        await cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x,'y':target['y']+target['height']-10}]})
        await cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
        await page.wait_for_function('!quotaSaving && !quotaDrag')
        assert writes[-1]['order']==['a','b','c'], writes
        # Cancelled gestures do not write. Keyboard handles can reorder too.
        await page.locator('[data-account-id="a"] .quota-handle').scroll_into_view_if_needed()
        handle=await page.locator('[data-account-id="a"] .quota-handle').bounding_box()
        count=len(writes)
        await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':handle['x']+20,'y':handle['y']+20}]})
        await cdp.send('Input.dispatchTouchEvent',{'type':'touchCancel','touchPoints':[]})
        assert len(writes)==count
        await page.locator('[data-account-id="a"] .quota-handle').focus()
        await page.keyboard.press('ArrowDown');await page.wait_for_function('!quotaSaving')
        assert writes[-1]['order']==['b','a','c']
        await page.evaluate('refresh()')
        assert await page.locator('#quota-panel').is_visible()
        fail=True
        await page.locator('#quota-refresh').click();await page.wait_for_function('!quotaBusy')
        assert await page.locator('#quota-error').is_visible()
        assert await page.locator('.quota-account').count()==4
        assert 'última consulta' in await page.locator('#quota-error').inner_text()
        fail=False;fail_write=True
        await page.get_by_role('button',name='Descer Conta B',exact=True).click()
        await page.wait_for_function('!quotaBusy && !quotaSaving')
        assert 'salvar' in await page.locator('#quota-error').inner_text()
        assert await page.locator('[data-provider="codex"] .quota-account').first.get_attribute('data-account-id')=='b'
        fail_write=False
        for row in fixture['accounts']:
            if row['id']=='a':row.update(priority=3,active=False,autoDisabled=True,quotaState='total')
            elif row['id']=='b':row.update(priority=2,quotaState='session')
            elif row['id']=='c':row.update(priority=1,quotaState='available')
        await page.locator('#quota-refresh').click();await page.wait_for_function('!quotaBusy')
        assert 'quota total esgotada' in await page.locator('[data-account-id="a"]').inner_text()
        assert 'Sessão esgotada' in await page.locator('[data-account-id="b"]').inner_text()
        await page.get_by_role('button',name='Subir Conta A',exact=True).click()
        await page.wait_for_function('!quotaSaving')
        assert writes[-1]['order']==['c','a','b']
        assert await page.locator('[data-provider="codex"] .quota-account').last.get_attribute('data-account-id')=='a'
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        await context.close();await browser.close()
        print('OK: setas, teclado, arraste touch, cancelamento, falhas, dados antigos, estados automáticos e ordem ajustada; nenhuma conta real alterada.')


if __name__=='__main__':asyncio.run(main())
