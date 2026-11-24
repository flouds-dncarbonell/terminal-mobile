"""Quota API fixtures never modify real 9router accounts."""
import copy
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestClient, TestServer

from mobile_server import authenticated, get_quotas, reorder_accounts, quota_automation
from quota import QuotaService, normalize_quotas, quota_condition
from router_dependency import RouterUnavailable


class NormalizationTests(unittest.TestCase):
    def test_percent_is_explicit_or_calculated_without_inventing_a_limit(self):
        rows = normalize_quotas({'quotas': {
            'session': {'used': 87, 'total': 100, 'resetAt': '2026-10-23T10:00:00Z'},
            'weekly': {'used': 100, 'total': 1000, 'remainingPercentage': 87.75},
            'unknown': {'used': 0, 'total': 0},
            'balance': {'remaining': 2, 'total': 8},
            'unlimited': {'unlimited': True},
            'bad': {'remainingPercentage': float('nan')},
        }})
        self.assertAlmostEqual(rows[0]['remainingPercent'], 13)
        self.assertEqual(rows[1]['remainingPercent'], 87.75)
        self.assertIsNone(rows[2]['remainingPercent'])
        self.assertEqual(rows[3]['remainingPercent'], 25)
        self.assertTrue(rows[4]['unlimited'])
        self.assertIsNone(rows[5]['remainingPercent'])
        self.assertIn('5 horas', rows[0]['name'])

    def test_antigravity_prefers_shared_windows_and_preserves_image_quota(self):
        rows = normalize_quotas({'quotas': {
            'claude-opus-high': {'used':0, 'total':100},
            'claude_gpt_weekly': {'displayName':'Claude & GPT (Weekly)', 'remainingPercentage':40},
            'gemini-pro': {'used':0, 'total':100},
            'gemini_weekly': {'remainingPercentage':80},
            'gemini-image': {'remainingPercentage':15},
        }}, 'antigravity')
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['remainingPercent'], 40)


class ConditionTests(unittest.TestCase):
    def test_session_and_total_limits_have_different_effects(self):
        for provider, session, total in [('codex','session','weekly'),('claude','session (5h)','weekly (7d)')]:
            for used, weekly, state in [(100,30,'session'),(30,100,'total'),(100,100,'total'),(99.9,99.9,'available')]:
                with self.subTest(provider=provider,used=used,weekly=weekly):
                    result=quota_condition({'quotas':{session:{'used':used,'total':100},total:{'used':weekly,'total':100}}},provider)
                    self.assertEqual(result['quotaState'],state)
                    self.assertEqual(result['totalAvailable'],weekly<100)

    def test_missing_invalid_unlimited_and_scoped_limits_are_not_total_exhaustion(self):
        for quotas in [{},{'weekly':{'used':0,'total':0}},{'weekly':{'used':True,'total':100}},
                       {'weekly':{'remainingPercentage':float('nan')}},
                       {'weekly':{'remaining':0,'unlimited':True}},
                       {'spark_weekly':{'remaining':0},'review_weekly':{'remaining':0}},
                       {'weekly sonnet (7d)':{'remaining':0}}]:
            with self.subTest(quotas=quotas):
                self.assertNotEqual(quota_condition({'quotas':quotas},'codex')['quotaState'],'total')
        self.assertIsNone(quota_condition({'message':'unavailable'},'claude')['totalAvailable'])

    def test_antigravity_keeps_accounts_with_another_available_pool(self):
        quotas={'gemini_weekly':{'remainingPercentage':0},'claude_gpt_weekly':{'remainingPercentage':80},
                'claude_gpt_session':{'remainingPercentage':20}}
        self.assertEqual(quota_condition({'quotas':quotas},'antigravity')['quotaState'],'available')
        quotas['claude_gpt_session']['remainingPercentage']=0
        self.assertEqual(quota_condition({'quotas':quotas},'antigravity')['quotaState'],'session')
        quotas['claude_gpt_weekly']['remainingPercentage']=0
        self.assertEqual(quota_condition({'quotas':quotas},'antigravity')['quotaState'],'total')
        del quotas['gemini_weekly']
        self.assertNotEqual(quota_condition({'quotas':quotas},'antigravity')['quotaState'],'total')


class QuotaApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.rows = [
            {'id':'c1', 'provider':'codex', 'name':'Conta A', 'priority':1, 'isActive':True, 'apiKey':'never-send-key'},
            {'id':'c2', 'provider':'codex', 'name':'Conta B', 'priority':2, 'isActive':True},
            {'id':'a1', 'provider':'claude', 'name':'Conta C', 'priority':1, 'isActive':False},
        ]
        self.calls = []; self.writes = []; self.fail_once = False
        self.usage_queries = []
        self.usages = {}; self.usage_failures = set(); self.fail_activity_once = False
        async def providers(request):
            self.calls.append('providers')
            self.assertEqual(request.headers.get('x-9r-cli-token'), 'fixture-cli-secret')
            return web.json_response({'connections':sorted(copy.deepcopy(self.rows), key=lambda r:r['priority']), 'pagination':{'totalPages':1}})
        async def settings(request):
            return web.json_response({'password':'never-send-password', 'providerStrategies':{'claude':{'fallbackStrategy':'round-robin'}}})
        async def usage(request):
            self.calls.append('usage')
            self.usage_queries.append(dict(request.query))
            identity=request.match_info['identity']
            if identity in self.usage_failures:
                return web.json_response({'error':'Unavailable'},status=503)
            return web.json_response(self.usages.get(identity,{'plan':'Plus', 'quotas':{'session':{'used':80, 'total':100}}, 'raw':{'accessToken':'never-send-token'}}))
        async def update(request):
            body = await request.json(); identity = request.match_info['identity']
            self.writes.append((identity, body))
            if self.fail_once and identity == 'c1' and body.get('priority') == 2:
                self.fail_once = False
                return web.json_response({'error':'fixture failure'}, status=500)
            row = next(r for r in self.rows if r['id'] == identity)
            row.update(body)
            if self.fail_activity_once and 'isActive' in body:
                self.fail_activity_once=False
                return web.json_response({'error':'Response lost after commit'},status=500)
            return web.json_response({'connection':row})
        upstream = web.Application()
        upstream.router.add_get('/api/providers/client', providers)
        upstream.router.add_get('/api/settings', settings)
        upstream.router.add_get('/api/usage/{identity}', usage)
        upstream.router.add_put('/api/providers/{identity}', update)
        self.upstream = TestServer(upstream); await self.upstream.start_server()
        self.patches = [patch('quota.ROUTER_URL',str(self.upstream.make_url('/')).rstrip('/')), patch('quota.cli_headers',return_value={'x-9r-cli-token':'fixture-cli-secret'}), patch('quota.ensure_router')]
        for replacement in self.patches: replacement.start()
        self.session = ClientSession()
        self.service = QuotaService()

    async def asyncTearDown(self):
        await self.session.close(); await self.upstream.close()
        for replacement in reversed(self.patches): replacement.stop()

    async def test_only_safe_data_is_exposed_and_snapshots_are_cached(self):
        result = await self.service.snapshot(self.session)
        self.assertEqual(len(result['accounts']), 3)
        self.assertNotIn('never-send',json.dumps(result))
        self.assertNotIn('fixture-cli-secret',json.dumps(result))
        self.assertEqual(next(a for a in result['accounts'] if a['id']=='a1')['strategy'],'round-robin')
        calls = list(self.calls)
        self.assertIs(await self.service.snapshot(self.session), result)
        self.assertIs(await self.service.snapshot(self.session, force=True), result)
        self.assertEqual(calls,self.calls)

    async def test_reorder_saves_priority_within_provider(self):
        await self.service.snapshot(self.session)
        result = await self.service.reorder(self.session,'codex',['c2','c1'],['c1','c2'])
        self.assertEqual(result['order'],['c2','c1'])
        self.assertEqual([r['id'] for r in sorted(self.rows[:2],key=lambda r:r['priority'])],['c2','c1'])
        self.assertTrue(all(set(body)=={'priority'} for _,body in self.writes))
        self.assertEqual(self.rows[2]['priority'],1)
        self.assertFalse(self.rows[2]['isActive'])

    async def test_background_checks_do_not_bypass_router_cache(self):
        await self.cycle()
        self.assertTrue(self.usage_queries)
        self.assertTrue(all('force' not in query for query in self.usage_queries))

    async def test_stale_balances_are_visible_without_automatic_account_changes(self):
        self.set_usage('c1', total=100)
        self.set_usage('c2', total=10)
        self.usages['c1'].update(usageStale=True, usageFetchedAt='2026-10-25T14:00:00Z',
                                 usageRetryAt='2026-10-25T14:30:00Z', usageError={'status':429})
        # Existing priority differs from quota sorting; stale data must not move it.
        self.rows[1]['priority'] = 2
        await self.cycle()
        row = next(a for a in self.service.cached['accounts'] if a['id'] == 'c1')
        self.assertEqual(row['quotaState'], 'unknown')
        self.assertIsNone(row['totalAvailable'])
        self.assertTrue(row['quotas'])
        self.assertIn('última leitura', row['error'])
        self.assertIn('limitou temporariamente', row['error'])
        self.assertEqual(row['usageFetchedAt'], '2026-10-25T14:00:00Z')
        self.assertEqual(self.writes, [])
        self.service.auto_disabled['c1'] = {'provider':'codex'}
        self.rows[0]['isActive'] = False
        self.usages['c1']['quotas']['weekly']['used'] = 10
        await self.cycle()
        self.assertEqual(self.writes, [])
        self.assertFalse(self.rows[0]['isActive'])

    async def test_stale_without_previous_balance_reports_temporary_failure(self):
        self.usages['a1'] = {'usageStale':True, 'usageError':{'status':429}}
        result = await self.service.snapshot(self.session)
        row = next(a for a in result['accounts'] if a['id'] == 'a1')
        self.assertEqual(row['quotaState'], 'unknown')
        self.assertEqual(row['quotas'], [])
        self.assertIn('limitou temporariamente', row['error'])
        self.assertNotIn('última leitura', row['error'])

    async def test_foreign_accounts_duplicates_and_stale_order_are_rejected(self):
        for order,previous in [(['c1','a1'],['c1','c2']), (['c1','c1'],['c1','c2']), (['c2','c1'],['c2','c1'])]:
            with self.assertRaises(ValueError):
                await self.service.reorder(self.session,'codex',order,previous)
        self.assertEqual(self.writes,[])

    async def test_partial_failure_restores_original_priorities(self):
        self.fail_once = True
        with self.assertRaisesRegex(RouterUnavailable,'restaurada'):
            await self.service.reorder(self.session,'codex',['c2','c1'],['c1','c2'])
        self.assertEqual([r['priority'] for r in self.rows],[1,2,1])

    async def test_reorder_requires_monitor_login_and_same_origin(self):
        app = web.Application(middlewares=[authenticated])
        app['credential'] = 'fixture:fixture'; app['http'] = self.session; app['quotas'] = self.service
        app.router.add_get('/api/quotas',get_quotas)
        app.router.add_post('/api/quotas/order',reorder_accounts)
        headers={'Authorization':'Basic Zml4dHVyZTpmaXh0dXJl'}
        async with TestClient(TestServer(app)) as client:
            response=await client.get('/api/quotas')
            self.assertEqual(response.status,401)
            response=await client.get('/api/quotas',headers=headers)
            self.assertEqual(response.status,200)
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            body={'provider':'codex','order':['c2','c1'],'previous':['c1','c2']}
            response=await client.post('/api/quotas/order',json=body,headers={**headers,'Origin':'https://external.example'})
            self.assertEqual(response.status,403)
            self.assertFalse(self.writes)
            response=await client.post('/api/quotas/order',json=body,headers={**headers,'Origin':str(client.make_url('/')).rstrip('/')})
            self.assertEqual(response.status,200)
            self.assertEqual((await response.json())['order'],['c2','c1'])

    def set_usage(self, identity, session=20, total=30):
        self.usages[identity]={'quotas':{'session':{'used':session,'total':100},'weekly':{'used':total,'total':100}}}

    async def cycle(self):
        self.service.cached=None
        return await self.service.reconcile(self.session)

    async def test_session_exhaustion_moves_account_last_without_disabling(self):
        self.set_usage('c1',session=100)
        self.set_usage('c2')
        await self.cycle()
        self.assertEqual([r['id'] for r in sorted(self.rows[:2],key=lambda r:r['priority'])],['c2','c1'])
        self.assertTrue(self.rows[0]['isActive'])
        self.assertTrue(all('isActive' not in body for _,body in self.writes))
        self.assertEqual(self.service.auto_disabled,{})

    async def test_background_worker_applies_rules_without_a_browser(self):
        self.set_usage('c1',total=100)
        worker=quota_automation({'quotas':self.service,'http':self.session})
        await worker.__anext__()
        try:
            for _ in range(100):
                if not self.rows[0]['isActive'] and self.rows[0]['priority']==2:
                    break
                await asyncio.sleep(.01)
            self.assertFalse(self.rows[0]['isActive'])
            self.assertEqual(self.rows[0]['priority'],2)
        finally:
            await worker.aclose()

    async def test_total_exhaustion_disables_and_recovers_across_restart(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'state.json'
            self.service=QuotaService(state_path=path)
            self.set_usage('c1',total=100)
            self.set_usage('c2')
            await self.cycle()
            self.assertFalse(self.rows[0]['isActive'])
            self.assertEqual(self.rows[0]['priority'],2)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertIn('c1',json.loads(path.read_text())['disabled'])
            self.service=QuotaService(state_path=path)
            # Renewal with an exhausted session re-enables, but keeps it last.
            self.set_usage('c1',session=100,total=0)
            await self.cycle()
            self.assertTrue(self.rows[0]['isActive'])
            self.assertEqual(self.rows[0]['priority'],2)
            self.assertEqual(self.service.auto_disabled,{})
            self.assertFalse(self.rows[2]['isActive'])

    async def test_initial_manual_disable_is_never_claimed_or_reenabled(self):
        self.set_usage('a1',total=100)
        await self.cycle()
        self.assertNotIn('a1',self.service.auto_disabled)
        self.set_usage('a1',total=0)
        await self.cycle()
        self.assertFalse(self.rows[2]['isActive'])
        self.assertFalse(any(identity=='a1' and 'isActive' in body for identity,body in self.writes))

    async def test_unknown_quota_and_failed_reads_cannot_reactivate_or_disable(self):
        self.set_usage('c1',total=100)
        await self.cycle()
        self.usage_failures.add('c1')
        self.usage_failures.add('c2')
        await self.cycle()
        self.assertFalse(self.rows[0]['isActive'])
        self.assertTrue(self.rows[1]['isActive'])
        self.assertIn('c1',self.service.auto_disabled)
        self.usage_failures.clear()
        self.usages['c1']={'quotas':{'session':{'remaining':100}}}
        await self.cycle()
        self.assertFalse(self.rows[0]['isActive'])

    async def test_repeated_checks_are_idempotent_and_preserve_manual_order(self):
        self.rows.insert(2,{'id':'c3','provider':'codex','name':'C','priority':3,'isActive':True})
        self.set_usage('c1',total=100)
        self.set_usage('c2')
        self.set_usage('c3')
        await self.cycle()
        self.assertEqual([r['id'] for r in sorted(self.rows[:3],key=lambda r:r['priority'])],['c2','c3','c1'])
        writes=list(self.writes)
        await self.cycle()
        self.assertEqual(self.writes,writes)
        await self.service.reorder(self.session,'codex',['c3','c1','c2'],['c2','c3','c1'])
        self.assertEqual([r['id'] for r in sorted(self.rows[:3],key=lambda r:r['priority'])],['c3','c2','c1'])
        writes=list(self.writes)
        await self.cycle()
        self.assertEqual(self.writes,writes)

    async def test_drag_cannot_promote_an_exhausted_account(self):
        self.set_usage('c1',session=100)
        self.set_usage('c2')
        result=await self.service.reorder(self.session,'codex',['c1','c2'],['c1','c2'])
        self.assertEqual(result['order'],['c2','c1'])
        self.assertTrue(result['adjusted'])
        self.assertTrue(self.rows[0]['isActive'])

    async def test_total_is_last_even_when_other_accounts_have_exhausted_sessions(self):
        self.set_usage('c1',total=100)
        self.set_usage('c2',session=100)
        await self.cycle()
        self.assertEqual(self.rows[0]['priority'],2)
        self.assertFalse(self.rows[0]['isActive'])
        self.assertTrue(self.rows[1]['isActive'])

    async def test_disable_commit_with_failed_response_does_not_lose_ownership(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'state.json'
            self.service=QuotaService(state_path=path)
            self.set_usage('c1',total=100)
            self.fail_activity_once=True
            with self.assertRaises(RouterUnavailable):
                await self.cycle()
            self.assertFalse(self.rows[0]['isActive'])
            self.service=QuotaService(state_path=path)
            self.set_usage('c1',total=0)
            await self.cycle()
            self.assertTrue(self.rows[0]['isActive'])
            self.assertEqual(self.service.auto_disabled,{})


if __name__ == '__main__':
    unittest.main()
