"""秒杀续期的真实HTTP、数据库阶段与调度回归。"""
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import select
from test_tk_matrix import MatrixTests
from app.hub_v5.models import MatrixDevice, MatrixFlashActivity, MatrixFlashRenewal, MatrixItem, MatrixRun, MatrixPlan, MatrixFire
from app.hub_v5 import service as s

TASK='promotion.flash_sale.renew'


class FlashSaleTests(MatrixTests):
    def flash_run(self,selected=None):
        with self.sessions() as db:
            device=db.get(MatrixDevice,1)
            device.capabilities={**device.capabilities,TASK:['MY']};db.commit()
        pv=self.request('POST','/hub-v5/manual/preview',json={'environment_ids':[self.env],'tasks':[TASK]})
        self.assertEqual(pv.status_code,200,pv.text);self.assertFalse(pv.json()['errors'])
        created=self.client.post('/hub-v5/manual/runs',json={'previews':[{'preview_token':b['preview_token'],'expected_revision':b['revision']} for b in pv.json()['batches']]},headers={'Authorization':f'Bearer {self.tokens[1]}','Idempotency-Key':str(uuid4())})
        self.assertEqual(created.status_code,200,created.text)
        run=created.json()['items'][0];item,creds=self.claim(run)
        return run,item,creds

    def observation(self,external='old',hours=1,status='ongoing'):
        return {'external_id':external,'name':'测试秒杀','activity_type':'商家秒杀活动','status':status,
            'ends_at':(datetime.now(timezone.utc)+timedelta(hours=hours)).isoformat(),'product_count':2}

    def scan_flash(self,item,creds,activities):
        result=self.ar('POST',f'/agent/items/{item}/flash-sales/scan',json={**creds,'complete':True,'activities':activities})
        self.assertEqual(result.status_code,200,result.text);return result.json()['renewals']

    def step_flash(self,item,creds,rid,stage,**values):
        return self.ar('POST',f'/agent/items/{item}/flash-sales/{rid}/step',json={**creds,'stage':stage,**values})

    def finish_flash(self,item,creds):
        r=self.ar('POST',f'/agent/items/{item}/flash-sales/complete',json=creds)
        self.assertEqual(r.status_code,200,r.text)
        return self.ar('POST',f'/agent/items/{item}/report',json={**creds,'status':'succeeded'})

    def test_threshold_type_and_full_scan(self):
        run,item,creds=self.flash_run()
        now=datetime.now(timezone.utc)
        with patch('app.hub_v5.flash_sales.s.utcnow',return_value=now.replace(tzinfo=None)):
            activities=[{**self.observation('boundary'), 'ends_at':(now+timedelta(hours=12)).isoformat()},
                self.observation('far',13),self.observation('expired',-1,'expired'),self.observation('terminated',-1,'terminated'),self.observation('future',1,'scheduled')]
            records=self.scan_flash(item,creds,activities)
        self.assertEqual([r['external_id'] for r in records],['boundary'])
        invalid=self.observation('platform');invalid['activity_type']='平台秒杀活动'
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/flash-sales/scan',json={**creds,'complete':True,'activities':[invalid]}).status_code,422)
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/flash-sales/scan',json={**creds,'complete':False,'activities':[]}).status_code,422)
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/flash-sales/scan',json={**creds,'complete':True,'activities':[activities[0],activities[0]]}).status_code,422)

    def test_old_connector_threshold_and_schedule_validation(self):
        pv=self.request('POST','/hub-v5/manual/preview',json={'environment_ids':[self.env],'tasks':[TASK]})
        self.assertEqual(pv.status_code,200,pv.text);self.assertTrue(pv.json()['errors'])
        for threshold in (5,37):
            r=self.request('POST','/hub-v5/operations',json={'name':'秒杀','tasks':[TASK],'flash_sale':{'threshold_hours':threshold}})
            self.assertEqual(r.status_code,422)
        op=self.operation()
        invalid=self.request('POST','/hub-v5/plans',json={'name':'非法间隔','operation_id':op['id'],'agent_id':1,'environment_ids':[self.env],'schedule_mode':'interval'})
        self.assertEqual(invalid.status_code,422)

    def test_publish_intents_and_confirmed_window(self):
        run,item,creds=self.flash_run()
        record=self.scan_flash(item,creds,[self.observation()])[0];rid=record['id']
        self.assertEqual(self.step_flash(item,creds,rid,'published').status_code,409)
        for stage in ('terminate_intent','terminated','copy_intent'):
            response=self.step_flash(item,creds,rid,stage);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.step_flash(item,creds,rid,'draft_confirmed',new_activity_id='new').status_code,200)
        start=datetime.now(timezone.utc)+timedelta(minutes=5);end=start+timedelta(hours=72)
        self.assertEqual(self.step_flash(item,creds,rid,'publish_intent',starts_at=start.isoformat(),ends_at=(end+timedelta(seconds=1)).isoformat()).status_code,422)
        valid={'new_activity_id':'new','starts_at':start.isoformat(),'ends_at':end.isoformat()}
        self.assertEqual(self.step_flash(item,creds,rid,'publish_intent',**valid).status_code,200)
        self.assertEqual(self.step_flash(item,creds,rid,'published',**valid).status_code,422)
        response=self.step_flash(item,creds,rid,'published',evidence='平台ID及起止时间已核对',**valid)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.step_flash(item,creds,rid,'published',evidence='平台ID及起止时间已核对',**valid).status_code,200)
        result=self.finish_flash(item,creds);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['status'],'succeeded')
        with self.sessions() as db:self.assertEqual(len(list(db.scalars(select(MatrixFlashRenewal)))),1)

    def test_expired_only_after_completion_and_explicit_selection(self):
        run,item,creds=self.flash_run()
        self.assertEqual(self.scan_flash(item,creds,[self.observation('expired',-1,'expired'),self.observation('ancient',-80,'expired')]),[])
        self.assertEqual(self.request('GET','/hub-v5/flash-sales/expired').json()['total'],0)
        self.assertEqual(self.finish_flash(item,creds).json()['status'],'succeeded')
        expired=self.request('GET','/hub-v5/flash-sales/expired').json()
        self.assertEqual(expired['total'],1);aid=expired['items'][0]['id']
        self.assertEqual(self.request('POST','/hub-v5/flash-sales/expired/dismiss',json={'activity_ids':[aid]}).status_code,200)
        self.assertEqual(self.request('GET','/hub-v5/flash-sales/expired').json()['unread'],0)
        selected=self.request('POST','/hub-v5/flash-sales/expired/preview',json={'activity_ids':[aid]})
        self.assertEqual(selected.status_code,200,selected.text)
        payload={'previews':[{'preview_token':b['preview_token'],'expected_revision':b['revision']} for b in selected.json()['batches']]}
        headers={'Authorization':f'Bearer {self.tokens[1]}','Idempotency-Key':str(uuid4())}
        created=self.client.post('/hub-v5/manual/runs',json=payload,headers=headers)
        again=self.client.post('/hub-v5/manual/runs',json=payload,headers=headers)
        self.assertEqual(created.json()['items'][0]['id'],again.json()['items'][0]['id'])
        item,creds=self.claim(created.json()['items'][0])
        records=self.scan_flash(item,creds,[self.observation('expired',-1,'expired'),self.observation('unselected',-2,'expired')])
        self.assertEqual([r['external_id'] for r in records],['expired'])
        self.assertEqual(self.step_flash(item,creds,records[0]['id'],'terminate_intent').status_code,409)
        self.assertEqual(self.step_flash(item,creds,records[0]['id'],'copy_intent').status_code,200)
        self.assertEqual(self.request('POST','/hub-v5/flash-sales/expired/preview',json={'activity_ids':[aid]}).status_code,409)

    def test_unknown_result_cannot_be_retried_or_cancelled_blindly(self):
        run,item,creds=self.flash_run();rid=self.scan_flash(item,creds,[self.observation()])[0]['id']
        self.assertEqual(self.step_flash(item,creds,rid,'terminate_intent').status_code,200)
        self.assertEqual(self.step_flash(item,creds,rid,'unknown',error='超时').status_code,200)
        report=self.ar('POST',f'/agent/items/{item}/report',json={**creds,'status':'failed'})
        self.assertEqual(report.json()['status'],'awaiting_attention')
        for action in ('retry','cancel'):
            self.assertEqual(self.request('POST',f'/hub-v5/run-items/{item}/resolve',json={'action':action}).status_code,409)
        self.assertEqual(self.request('POST',f'/hub-v5/flash-sales/{rid}/resolve',json={'action':'cancel','evidence':'未核对'}).status_code,409)
        resumed=self.request('POST',f'/hub-v5/flash-sales/{rid}/resolve',json={'action':'resume','verified_stage':'terminated','evidence':'已核对平台显示旧活动终止，尚未复制'})
        self.assertEqual(resumed.status_code,200,resumed.text)
        self.assertTrue(resumed.json()['terminated'])
        item,creds=self.claim(run)
        self.assertEqual(self.scan_flash(item,creds,[self.observation(status='terminated')])[0]['stage'],'terminated')
        self.assertEqual(self.step_flash(item,creds,rid,'terminate_intent').status_code,409)

    def test_recheck_expired_moves_to_user_choice(self):
        run,item,creds=self.flash_run();rid=self.scan_flash(item,creds,[self.observation()])[0]['id']
        recheck=self.ar('POST',f'/agent/items/{item}/flash-sales/{rid}/recheck',json={**creds,'activity':self.observation(hours=-1,status='expired')})
        self.assertFalse(recheck.json()['eligible'])
        self.assertEqual(self.step_flash(item,creds,rid,'skipped',evidence='等待用户选择').status_code,200)
        self.assertEqual(self.finish_flash(item,creds).status_code,200)
        self.assertEqual(self.request('GET','/hub-v5/flash-sales/expired').json()['total'],1)

    def test_permissions_stop_fencing_and_missing_receipt(self):
        run,item,creds=self.flash_run();rid=self.scan_flash(item,creds,[self.observation()])[0]['id']
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/report',json={**creds,'status':'succeeded'}).json()['status'],'awaiting_attention')
        # 另一公司和旧租约均不能修改台账。
        self.assertEqual(self.request('GET',f'/hub-v5/run-items/{item}/flash-sales',uid=5).status_code,404)
        self.assertEqual(self.step_flash(item,{**creds,'fencing':creds['fencing']+1},rid,'terminate_intent').status_code,409)

    def test_stop_blocks_new_intents_and_keeps_known_stage(self):
        run,item,creds=self.flash_run();rid=self.scan_flash(item,creds,[self.observation()])[0]['id']
        self.assertEqual(self.request('POST',f"/hub-v5/runs/{run['id']}/stop",json={}).status_code,200)
        self.assertEqual(self.step_flash(item,creds,rid,'terminate_intent').status_code,409)

    def test_published_old_activity_cannot_create_another_successor(self):
        run,item,creds=self.flash_run();rid=self.scan_flash(item,creds,[self.observation()])[0]['id']
        for stage in ('terminate_intent','terminated','copy_intent'):
            self.assertEqual(self.step_flash(item,creds,rid,stage).status_code,200)
        self.assertEqual(self.step_flash(item,creds,rid,'draft_confirmed',new_activity_id='successor').status_code,200)
        start=datetime.now(timezone.utc)+timedelta(minutes=5);end=start+timedelta(hours=72)
        window={'new_activity_id':'successor','starts_at':start.isoformat(),'ends_at':end.isoformat()}
        self.assertEqual(self.step_flash(item,creds,rid,'publish_intent',**window).status_code,200)
        self.assertEqual(self.step_flash(item,creds,rid,'published',evidence='平台已核实',**window).status_code,200)
        self.assertEqual(self.finish_flash(item,creds).json()['status'],'succeeded')
        run,item,creds=self.flash_run()
        self.assertEqual(self.scan_flash(item,creds,[self.observation()]),[])
        self.assertEqual(self.finish_flash(item,creds).json()['status'],'succeeded')

    def test_manual_confirmation_persists_summary_and_releases_guard(self):
        run,item,creds=self.flash_run();rid=self.scan_flash(item,creds,[self.observation()])[0]['id']
        self.assertEqual(self.step_flash(item,creds,rid,'terminate_intent').status_code,200)
        self.assertEqual(self.step_flash(item,creds,rid,'unknown',error='需要核对').status_code,200)
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/report',json={**creds,'status':'failed'}).json()['status'],'awaiting_attention')
        start=datetime.now(timezone.utc);end=start+timedelta(hours=72)
        result=self.request('POST',f'/hub-v5/flash-sales/{rid}/resolve',json={'action':'confirm-published','new_activity_id':'manual-new',
            'starts_at':start.isoformat(),'ends_at':end.isoformat(),'evidence':'平台核对新活动ID与起止时间均正确'})
        self.assertEqual(result.status_code,200,result.text)
        with self.sessions() as db:
            saved=db.get(MatrixItem,item)
            self.assertEqual(saved.status,'succeeded');self.assertEqual(saved.result['flash_sale']['succeeded'],1)
            self.assertTrue(saved.result['flash_sale']['complete'])

    def test_missing_selected_activity_is_reported_as_skipped(self):
        run,item,creds=self.flash_run()
        self.scan_flash(item,creds,[self.observation('expired',-1,'expired')])
        self.finish_flash(item,creds)
        aid=self.request('GET','/hub-v5/flash-sales/expired').json()['items'][0]['id']
        with self.sessions() as db:
            stored=db.get(MatrixRun,run['id']);stored.frozen={**stored.frozen,'config':{**stored.frozen['config'],'selected_flash_ids':[aid]}}
            saved=db.get(MatrixItem,item);saved.status='queued';saved.stage='queued'
            db.commit()
        item,creds=self.claim(run)
        self.assertEqual(self.scan_flash(item,creds,[]),[])
        result=self.finish_flash(item,creds)
        self.assertEqual(result.json()['result']['flash_sale']['skipped'],1)
        self.assertEqual(self.request('GET','/hub-v5/flash-sales/expired').json()['total'],0)

    def readonly_sync(self):
        from app.hub_v5.flash_sales import COLLECT_TASK
        with self.sessions() as db:
            d=db.get(MatrixDevice,1);d.capabilities={**d.capabilities,COLLECT_TASK:['MY']};db.commit()
        headers={'Authorization':f'Bearer {self.tokens[1]}','Idempotency-Key':str(uuid4())}
        result=self.client.post(f'/hub-v5/environments/{self.env}/flash-sales/sync',json={},headers=headers)
        self.assertEqual(result.status_code,200,result.text)
        return result.json(),headers

    def test_store_readonly_sync_and_four_states(self):
        response=self.request('GET',f'/hub-v5/environments/{self.env}/flash-sales')
        self.assertEqual(response.status_code,200,response.text)
        self.assertIsNone(response.json()['snapshot']);self.assertIsNone(response.json()['counts'])
        self.assertEqual(self.request('GET',f'/hub-v5/environments/{self.env}/flash-sales',uid=5).status_code,404)
        run,headers=self.readonly_sync()
        self.assertEqual(run['tasks'],['promotion.flash_sale.collect'])
        repeated=self.client.post(f'/hub-v5/environments/{self.env}/flash-sales/sync',json={},headers=headers)
        self.assertEqual(repeated.json()['id'],run['id'])
        another,_=self.readonly_sync();self.assertEqual(another['id'],run['id'])
        item,creds=self.claim(run)
        payload=[self.observation('near',1),self.observation('ended',-1,'expired'),self.observation('old',-80,'expired'),self.observation('future',12,'scheduled'),self.observation('stopped',-2,'terminated')]
        start=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat();payload[0]['starts_at']=start
        self.assertEqual(self.scan_flash(item,creds,payload),[])
        self.assertEqual(self.step_flash(item,creds,999,'terminate_intent').status_code,403)
        with self.sessions() as db:self.assertEqual(len(list(db.scalars(select(MatrixFlashRenewal)))),0)
        self.assertEqual(self.finish_flash(item,creds).json()['status'],'succeeded')
        data=self.request('GET',f'/hub-v5/environments/{self.env}/flash-sales').json()
        self.assertEqual(data['snapshot']['count'],5);self.assertEqual(data['total'],5)
        self.assertEqual(data['counts'],{'ongoing':1,'scheduled':1,'expired':2,'terminated':1,'unknown':0})
        near=next(a for a in data['items'] if a['external_id']=='near')
        self.assertIsNotNone(near['starts_at']);self.assertFalse(near['can_renew'])
        ended=self.request('GET',f'/hub-v5/environments/{self.env}/flash-sales?status=expired').json()
        self.assertEqual(ended['total'],1);self.assertTrue(ended['items'][0]['can_renew'])
        for status in ('ongoing','scheduled','terminated'):
            result=self.request('GET',f'/hub-v5/environments/{self.env}/flash-sales?status={status}').json()
            self.assertEqual(result['total'],1);self.assertFalse(result['items'][0]['can_renew'])
        self.assertEqual(self.request('GET','/hub-v5/flash-sales/expired').json()['environment_count'],1)

    def test_complete_empty_sync_replaces_current_data_and_failed_scan_preserves_it(self):
        run,_=self.readonly_sync();item,creds=self.claim(run)
        self.scan_flash(item,creds,[self.observation('ended',-1,'expired')]);self.finish_flash(item,creds)
        run,_=self.readonly_sync();item,creds=self.claim(run)
        bad=self.ar('POST',f'/agent/items/{item}/flash-sales/scan',json={**creds,'complete':False,'activities':[]})
        self.assertEqual(bad.status_code,422)
        self.assertEqual(self.request('GET',f'/hub-v5/environments/{self.env}/flash-sales').json()['snapshot']['count'],1)
        self.assertEqual(self.scan_flash(item,creds,[]),[]);self.finish_flash(item,creds)
        data=self.request('GET',f'/hub-v5/environments/{self.env}/flash-sales').json()
        self.assertIsNotNone(data['snapshot']);self.assertEqual(data['snapshot']['count'],0)
        self.assertEqual(data['total'],0);self.assertEqual(sum(data['counts'].values()),0)
        self.assertEqual(self.request('GET','/hub-v5/flash-sales/expired').json()['total'],0)

    def test_sync_requires_declared_readonly_capability(self):
        response=self.client.post(f'/hub-v5/environments/{self.env}/flash-sales/sync',json={},headers={'Authorization':f'Bearer {self.tokens[1]}','Idempotency-Key':str(uuid4())})
        self.assertEqual(response.status_code,422,response.text)
        self.assertIn('同步秒杀活动',response.json()['detail'])

    def test_interval_slots_deduplicate_and_preserve_daily(self):
        from app.hub_v5.worker import schedule_plan
        with self.sessions() as db:
            d=db.get(MatrixDevice,1);d.capabilities={**d.capabilities,TASK:['MY']};db.commit()
        op=self.operation(tasks=[TASK])
        p=self.request('POST','/hub-v5/plans',json={'name':'两小时检查','operation_id':op['id'],'agent_id':1,'environment_ids':[self.env],'schedule_mode':'interval','interval_hours':2,'scheduled':True}).json()
        now=datetime.now(timezone.utc).replace(hour=2,minute=0,second=10,microsecond=0)
        with self.sessions() as db:
            db.get(MatrixPlan,p['id']).updated_at=now.replace(tzinfo=None)-timedelta(hours=3);db.commit()
        with patch('app.hub_v5.service.utcnow',return_value=now.replace(tzinfo=None)):
            with self.sessions() as db:schedule_plan(db,p['id'],now)
            with self.sessions() as db:schedule_plan(db,p['id'],now+timedelta(seconds=5))
        with self.sessions() as db:
            fires=list(db.scalars(select(MatrixFire).where(MatrixFire.plan_id==p['id'])))
            self.assertEqual(len(fires),1);self.assertEqual(fires[0].status,'created')
        edited=self.request('PATCH',f"/hub-v5/operations/{op['id']}",json={'name':'禁止混合','tasks':[TASK,'shop.collect'],'expected_revision':op['revision']})
        self.assertEqual(edited.status_code,422)


def load_tests(loader, tests, pattern):
    # 复用矩阵HTTP fixture，不重复运行导入基类的全部回归用例。
    return unittest.TestSuite(FlashSaleTests(name) for name in FlashSaleTests.__dict__ if name.startswith('test_'))
