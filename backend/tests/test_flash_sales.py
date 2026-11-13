"""秒杀续期的真实HTTP、数据库阶段与调度回归。"""
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import select
from test_tk_matrix import MatrixTests
from app.hub_v5.models import MatrixDevice, MatrixFlashActivity, MatrixFlashRenewal, MatrixFlashSnapshot, MatrixItem, MatrixRun, MatrixPlan, MatrixFire
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
            db.get(MatrixPlan,p['id']).updated_at=now.replace(tzinfo=None)-timedelta(hours=3)
            from app.models import HubAgent
            db.get(HubAgent,1).last_seen_at=now.replace(tzinfo=None)
            from app.hub_v5.models import MatrixAccess
            for access in db.scalars(select(MatrixAccess).where(MatrixAccess.agent_id==1)):
                access.seen_at=now.replace(tzinfo=None)
            db.commit()
        with patch('app.hub_v5.service.utcnow',return_value=now.replace(tzinfo=None)):
            with self.sessions() as db:schedule_plan(db,p['id'],now)
            with self.sessions() as db:schedule_plan(db,p['id'],now+timedelta(seconds=5))
        with self.sessions() as db:
            fires=list(db.scalars(select(MatrixFire).where(MatrixFire.plan_id==p['id'])))
            self.assertEqual(len(fires),1);self.assertEqual(fires[0].status,'created')
        edited=self.request('PATCH',f"/hub-v5/operations/{op['id']}",json={'name':'禁止混合','tasks':[TASK,'shop.collect'],'expected_revision':op['revision']})
        self.assertEqual(edited.status_code,422)

    def test_partial_scan_preserves_full_snapshot_and_history(self):
        run,item,creds=self.flash_run()
        self.scan_flash(item,creds,[self.observation('expired',-1,'expired'),self.observation('terminated',-2,'terminated')])
        with self.sessions() as db:
            snapshot=db.scalar(select(MatrixFlashSnapshot));before=(snapshot.observed_at,snapshot.activity_count)
        response=self.ar('POST',f'/agent/items/{item}/flash-sales/scan',json={**creds,'complete':True,'scope':'ongoing','activities':[self.observation()]})
        self.assertEqual(response.status_code,200,response.text)
        with self.sessions() as db:
            snapshot=db.scalar(select(MatrixFlashSnapshot))
            self.assertEqual((snapshot.observed_at,snapshot.activity_count),before)
            self.assertTrue(all(a.present for a in db.scalars(select(MatrixFlashActivity))))
        invalid=self.ar('POST',f'/agent/items/{item}/flash-sales/scan',json={**creds,'complete':True,'scope':'ongoing','activities':[self.observation('expired',-1,'expired')]})
        self.assertEqual(invalid.status_code,422)
        invalid=self.ar('POST',f'/agent/items/{item}/flash-sales/scan',json={**creds,'complete':True,'scope':'selected','activities':[]})
        self.assertEqual(invalid.status_code,422)

    def test_api_creation_persists_preparation_before_termination_and_id_after_creation(self):
        run,item,creds=self.flash_run();rid=self.scan_flash(item,creds,[self.observation()])[0]['id']
        preparation={'promotion_name':f'秒杀[HT-R{rid}]','type_detail':9,'promotion_limit_dimension':4,
            'flash_sale_products':[{'product_id':'100','flash_sale_price':'23.45'}]}
        result=self.step_flash(item,creds,rid,'prepared',preparation=preparation)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['preparation'],preparation);self.assertIsNone(result.json()['new_activity_id'])
        changed={**preparation,'flash_sale_products':[{'product_id':'100','flash_sale_price':'1'}]}
        self.assertEqual(self.step_flash(item,creds,rid,'prepared',preparation=changed).status_code,409)
        again=self.scan_flash(item,creds,[self.observation()])[0]
        self.assertEqual(again['preparation'],preparation)
        start=datetime.now(timezone.utc)+timedelta(minutes=6);end=start+timedelta(hours=72)
        times={'starts_at':start.isoformat(),'ends_at':end.isoformat()}
        self.assertEqual(self.step_flash(item,creds,rid,'publish_intent',**times).status_code,409)
        for stage in ('terminate_intent','terminated','publish_intent'):
            result=self.step_flash(item,creds,rid,stage,**(times if stage=='publish_intent' else {}))
            self.assertEqual(result.status_code,200,result.text)
        result=self.step_flash(item,creds,rid,'created',new_activity_id='platform-new')
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['new_activity_id'],'platform-new')
        result=self.step_flash(item,creds,rid,'published',new_activity_id='platform-new',evidence='已核对接口商品价格和时间',**times)
        self.assertEqual(result.status_code,200,result.text)
        self.assertTrue(result.json()['terminated'])
        self.assertEqual(self.finish_flash(item,creds).json()['status'],'succeeded')

    def test_unsent_or_rejected_requests_can_fail_but_uncertain_requests_cannot(self):
        run,item,creds=self.flash_run();rid=self.scan_flash(item,creds,[self.observation()])[0]['id']
        self.assertEqual(self.step_flash(item,creds,rid,'terminate_intent').status_code,200)
        self.assertEqual(self.step_flash(item,creds,rid,'failed',error='不确定').status_code,409)
        result=self.step_flash(item,creds,rid,'failed',request_outcome='not_sent',error='本机检查失败，尚未发送请求')
        self.assertEqual(result.status_code,200,result.text)
        self.assertFalse(result.json()['terminated']);self.assertIn('尚未发送',result.json()['error'])

    def test_selected_scan_rejects_other_activities_and_claim_has_scoped_targets(self):
        run,item,creds=self.flash_run()
        self.scan_flash(item,creds,[self.observation('expired',-1,'expired')]);self.finish_flash(item,creds)
        aid=self.request('GET','/hub-v5/flash-sales/expired').json()['items'][0]['id']
        preview=self.request('POST','/hub-v5/flash-sales/expired/preview',json={'activity_ids':[aid]}).json()
        created=self.client.post('/hub-v5/manual/runs',json={'previews':[{'preview_token':b['preview_token'],'expected_revision':b['revision']} for b in preview['batches']]},headers={'Authorization':f'Bearer {self.tokens[1]}','Idempotency-Key':str(uuid4())}).json()['items'][0]
        item=created['items'][0]['id']
        claimed=self.ar('POST',f'/agent/items/{item}/claim',json={}).json()
        self.assertEqual(claimed['config']['flash_sale_targets'],[{'external_id':'expired','name':'测试秒杀'}])
        creds={k:claimed[k] for k in ('claim_token','fencing')}
        response=self.ar('POST',f'/agent/items/{item}/flash-sales/scan',json={**creds,'complete':True,'scope':'selected','activities':[self.observation('other',-1,'expired')]})
        self.assertEqual(response.status_code,422)
        response=self.ar('POST',f'/agent/items/{item}/flash-sales/scan',json={**creds,'complete':True,'scope':'selected','activities':[self.observation('expired',-1,'expired')]})
        self.assertEqual(response.status_code,200,response.text)


    def end_previous_run(self,run,item):
        from app.hub_v5.models import MatrixAttempt
        with self.sessions() as db:
            previous=db.get(MatrixItem,item)
            db.get(MatrixRun,run['id']).status='failed';previous.status='failed'
            previous.stage='precheck_failed';previous.error='执行器或插件版本已变化，请重新预览创建运行'
            db.get(MatrixAttempt,previous.attempt_id).status='failed'
            s.release_guard(db,previous);db.commit()

    def test_new_run_adopts_confirmed_unexecuted_records_from_failed_previous_run(self):
        run,item,creds=self.flash_run()
        observations=[self.observation('one'),self.observation('two')]
        before=self.scan_flash(item,creds,observations)
        self.end_previous_run(run,item)
        new_run,new_item,new_creds=self.flash_run()
        response=self.ar('POST',f'/agent/items/{new_item}/flash-sales/scan',json={**new_creds,'complete':True,'scope':'ongoing','activities':observations})
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertEqual([r['id'] for r in result['renewals']],[r['id'] for r in before])
        self.assertEqual(result['blocked'],[])
        self.assertTrue(all(r['item_id']==new_item and r['stage']=='pending' for r in result['renewals']))
        with self.sessions() as db:
            self.assertEqual(len(list(db.scalars(select(MatrixFlashRenewal)))),2)
            self.assertEqual(db.get(MatrixRun,run['id']).status,'failed')
        events=self.request('GET',f"/hub-v5/runs/{new_run['id']}/events").json()
        self.assertTrue(any(e['kind']=='flash.reassigned' and e['payload']['old_run_id']==run['id'] for e in events))

    def test_unknown_previous_record_blocks_instead_of_reporting_zero_work_success(self):
        run,item,creds=self.flash_run()
        old=self.scan_flash(item,creds,[self.observation()])[0]
        self.step_flash(item,creds,old['id'],'terminate_intent');self.step_flash(item,creds,old['id'],'unknown',error='请求响应丢失')
        self.end_previous_run(run,item)
        new_run,new_item,new_creds=self.flash_run()
        response=self.ar('POST',f'/agent/items/{new_item}/flash-sales/scan',json={**new_creds,'complete':True,'scope':'ongoing','activities':[self.observation()]})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['renewals'],[])
        self.assertEqual(response.json()['blocked'][0]['run_id'],run['id'])
        completed=self.ar('POST',f'/agent/items/{new_item}/flash-sales/complete',json=new_creds)
        self.assertEqual(completed.json()['blocked_count'],1)
        report=self.ar('POST',f'/agent/items/{new_item}/report',json={**new_creds,'status':'succeeded','message':'不应误报成功'})
        self.assertEqual(report.status_code,200,report.text)
        self.assertEqual(report.json()['status'],'failed')
        self.assertIn(f"原运行 #{run['id']}",report.json()['error'])
        with self.sessions() as db:
            row=db.get(MatrixFlashRenewal,old['id'])
            self.assertEqual((row.item_id,row.stage),(item,'unknown'))

    def test_active_or_other_owner_records_cannot_be_adopted(self):
        from app.hub_v5.models import MatrixAttempt
        run,item,creds=self.flash_run();self.scan_flash(item,creds,[self.observation()])
        self.end_previous_run(run,item)
        new_run,new_item,new_creds=self.flash_run()
        for case in ('queued','live_lease','other_owner'):
            with self.subTest(case=case):
                with self.sessions() as db:
                    old_item=db.get(MatrixItem,item);old_run=db.get(MatrixRun,run['id']);attempt=db.get(MatrixAttempt,old_item.attempt_id)
                    old_item.status='queued' if case=='queued' else 'failed'
                    old_run.status='queued' if case=='queued' else 'failed'
                    old_run.owner_id=2 if case=='other_owner' else 1
                    attempt.status='running' if case=='live_lease' else 'failed'
                    attempt.lease_until=datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(minutes=1)
                    db.commit()
                response=self.ar('POST',f'/agent/items/{new_item}/flash-sales/scan',json={**new_creds,'complete':True,'scope':'ongoing','activities':[self.observation()]})
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['renewals'],[]);self.assertEqual(len(response.json()['blocked']),1)



    def test_confirm_created_activity_closes_interrupted_run_and_defers_unexecuted_remaining(self):
        self.confirm_interrupted_run()

    def test_reconfirm_same_created_activity_repairs_legacy_incomplete_resolution(self):
        self.confirm_interrupted_run(already_confirmed=True)

    def confirm_interrupted_run(self,already_confirmed=False):
        run,item,creds=self.flash_run()
        records=self.scan_flash(item,creds,[self.observation('one'),self.observation('two')])
        rid=records[0]['id']
        for stage in ('terminate_intent','terminated','copy_intent'):
            self.assertEqual(self.step_flash(item,creds,rid,stage).status_code,200)
        self.step_flash(item,creds,rid,'draft_confirmed',new_activity_id='new-one')
        start=datetime.now(timezone.utc)+timedelta(minutes=6);end=start+timedelta(hours=72)
        times={'starts_at':start.isoformat(),'ends_at':end.isoformat()}
        self.step_flash(item,creds,rid,'publish_intent',**times)
        self.step_flash(item,creds,rid,'created',new_activity_id='new-one')
        self.step_flash(item,creds,rid,'unknown',error='此前误把未开始状态判为未发布')
        self.ar('POST',f'/agent/items/{item}/report',json={**creds,'status':'failed'})
        if already_confirmed:
            with self.sessions() as db:
                row=db.get(MatrixFlashRenewal,rid);row.stage='published'
                row.starts_at=(start+timedelta(minutes=14)).replace(tzinfo=None)
                row.ends_at=(end+timedelta(minutes=14)).replace(tzinfo=None)
                db.commit()
            rejected=self.request('POST',f'/hub-v5/flash-sales/{rid}/resolve',json={'action':'confirm-published','new_activity_id':'another-id','evidence':'禁止替换已确认ID',**times})
            self.assertEqual(rejected.status_code,409,rejected.text)
        result=self.request('POST',f'/hub-v5/flash-sales/{rid}/resolve',json={'action':'confirm-published','new_activity_id':'new-one','evidence':'只读核验ID、时间及全部商品价格一致',**times})
        self.assertEqual(result.status_code,200,result.text)
        with self.sessions() as db:
            self.assertEqual(db.get(MatrixFlashRenewal,rid).stage,'published')
            self.assertEqual(db.get(MatrixFlashRenewal,rid).starts_at,start.replace(tzinfo=None))
            self.assertEqual(db.get(MatrixFlashRenewal,records[1]['id']).stage,'skipped')
            self.assertEqual(db.get(MatrixItem,item).status,'partial_success')
            self.assertEqual(db.get(MatrixItem,item).stage,'partial_success')
            self.assertEqual(db.get(MatrixRun,run['id']).status,'partial_success')
        new_run,new_item,new_creds=self.flash_run()
        rows=self.scan_flash(new_item,new_creds,[self.observation('two')])
        self.assertEqual([r['id'] for r in rows],[records[1]['id']])
        self.assertEqual(rows[0]['stage'],'pending')


def load_tests(loader, tests, pattern):
    # 复用矩阵HTTP fixture，不重复运行导入基类的全部回归用例。
    return unittest.TestSuite(FlashSaleTests(name) for name in FlashSaleTests.__dict__ if name.startswith('test_'))
