"""Independent follow-up tests for sticky local authorization and observed receipts.
All provider operations below use the local fixture ledger; direct adapter capture
simulates activity by another merchant process, never an actual external payment.
"""
import copy
import tempfile
import unittest
import uuid
from pathlib import Path
from commitguard.adapters import FixturePlanner, FixturePayPal
from commitguard.policy import PolicyError
from commitguard.service import Service
from commitguard.store import Store

class FollowupReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'followup.db'
        self.store=Store(self.path)
        self.pp=FixturePayPal(self.store)
        self.svc=Service(self.store,FixturePlanner(),self.pp)
        self.owner='followup-owner'
    def tearDown(self):
        self.store.close();self.temp.cleanup()
    def ready(self,scenario='happy'):
        p=self.svc.plan(self.owner,{'need':'Patches and gloves for 20 bike repairs','budget':'80.00','currency':'USD','scenario':scenario,'request_key':str(uuid.uuid4())})
        self.svc.approve(p['id'],self.owner,p['plan_hash'])
        self.svc.create(p['id'],self.owner)
        return self.svc.payer_fixture(p['id'],self.owner)
    def restart(self):
        self.store.close()
        self.store=Store(self.path)
        self.pp=FixturePayPal(self.store)
        self.svc=Service(self.store,FixturePlanner(),self.pp)
    def mismatch_then_restore(self,p,via_webhook=False):
        original=self.pp.get
        good=original(p['paypal_id'])
        corrupt=copy.deepcopy(good)
        corrupt['purchase_units'][0]['amount']['value']='0.01'
        self.pp.get=lambda id:copy.deepcopy(corrupt)
        try:
            if via_webhook:
                r=self.svc.webhook({},self.event(p,'BAD-EVIDENCE'),fixture_owner=self.owner)['purchase']
            else:r=self.svc.reconcile(p['id'],self.owner)
        finally:self.pp.get=original
        self.assertEqual(r['state'],'REVIEW_REQUIRED')
        return self.svc.reconcile(p['id'],self.owner)
    def event(self,p,event_id,event_type='CHECKOUT.ORDER.APPROVED'):
        resource={'id':p['paypal_id']} if event_type=='CHECKOUT.ORDER.APPROVED' else {'supplementary_data':{'related_ids':{'order_id':p['paypal_id']}}}
        return {'id':event_id,'event_type':event_type,'resource':resource}
    def assert_capture_not_sent(self,p):
        before=self.store.fixture_get(p['paypal_id'])['capture_calls']
        try:self.svc.capture(p['id'],self.owner)
        except PolicyError:pass
        self.assertEqual(self.store.fixture_get(p['paypal_id'])['capture_calls'],before)
    def test_cancel_then_bad_read_then_good_read_never_restores_capture(self):
        p=self.ready();self.svc.cancel(p['id'],self.owner)
        r=self.mismatch_then_restore(p)
        self.assertEqual(r['state'],'CANCELLED')
        self.assertIsNotNone(r.get('local_cancelled_at'))
        self.assert_capture_not_sent(p)
    def test_cancel_then_bad_webhook_then_good_webhook_never_restores_capture(self):
        p=self.ready();self.svc.cancel(p['id'],self.owner)
        self.mismatch_then_restore(p,via_webhook=True)
        r=self.svc.webhook({},self.event(p,'GOOD-EVIDENCE'),fixture_owner=self.owner)['purchase']
        self.assertEqual(r['state'],'CANCELLED')
        self.assertIsNotNone(r.get('local_cancelled_at'))
        self.assert_capture_not_sent(p)
    def test_cancel_survives_mismatch_and_actual_database_reopen(self):
        p=self.ready();self.svc.cancel(p['id'],self.owner)
        original=self.pp.get
        self.pp.get=lambda id:None
        try:self.svc.reconcile(p['id'],self.owner)
        finally:self.pp.get=original
        self.restart()
        r=self.svc.reconcile(p['id'],self.owner)
        self.assertEqual(r['state'],'CANCELLED')
        self.assertIsNotNone(r.get('local_cancelled_at'))
        self.assert_capture_not_sent(p)
    def test_historical_cancel_trace_is_migrated_even_after_review_state(self):
        p=self.ready();self.svc.cancel(p['id'],self.owner)
        with self.store.tx():
            raw=self.store.get(p['id']);raw.pop('local_cancelled_at',None)
            raw.pop('capture_observed',None);raw['state']='REVIEW_REQUIRED'
            self.store.save(raw)
        self.restart()
        r=self.svc.reconcile(p['id'],self.owner)
        self.assertEqual(r['state'],'CANCELLED')
        self.assertIsNotNone(r.get('local_cancelled_at'))
        self.assert_capture_not_sent(p)
    def test_cancellation_marker_blocks_capture_even_if_display_state_is_ready(self):
        p=self.ready();self.svc.cancel(p['id'],self.owner)
        with self.store.tx():
            raw=self.store.get(p['id']);raw['state']='READY_TO_CAPTURE';self.store.save(raw)
        self.assert_capture_not_sent(p)
    def test_cancelled_purchase_observes_external_completion_without_reauthorization(self):
        p=self.ready();self.svc.cancel(p['id'],self.owner)
        remote=self.pp.capture(p['paypal_id'],'external-fixture-capture')
        expected=remote['purchase_units'][0]['payments']['captures'][0]['id']
        r=self.svc.reconcile(p['id'],self.owner)
        self.assertEqual(r['state'],'COMPLETED');self.assertEqual(r['capture_id'],expected)
        self.assertIsNotNone(r.get('local_cancelled_at'));self.assertTrue(r.get('capture_observed'))
        self.assertFalse(r['capture_started'])
        self.assert_capture_not_sent(p)
    def test_cancelled_purchase_observes_external_pending_then_settlement(self):
        p=self.ready('pending');self.svc.cancel(p['id'],self.owner)
        remote=self.pp.capture(p['paypal_id'],'external-fixture-capture')
        expected=remote['purchase_units'][0]['payments']['captures'][0]['id']
        r=self.svc.reconcile(p['id'],self.owner)
        self.assertEqual(r['state'],'PAYMENT_PENDING');self.assertEqual(r['capture_id'],expected)
        self.assertIsNotNone(r.get('local_cancelled_at'));self.assertTrue(r.get('capture_observed'))
        self.assert_capture_not_sent(p)
        self.pp.settle_fixture(p['paypal_id'])
        self.restart()
        r=self.svc.webhook({},self.event(p,'SETTLED','PAYMENT.CAPTURE.COMPLETED'),fixture_owner=self.owner)['purchase']
        self.assertEqual(r['state'],'COMPLETED');self.assertEqual(r['capture_id'],expected)
        self.assertIsNotNone(r.get('local_cancelled_at'))
        self.assert_capture_not_sent(p)
    def test_external_completed_preflight_keeps_receipt_and_sends_no_second_capture(self):
        p=self.ready()
        remote=self.pp.capture(p['paypal_id'],'external-fixture-capture')
        expected=remote['purchase_units'][0]['payments']['captures'][0]['id']
        r=self.svc.capture(p['id'],self.owner)
        self.assertEqual(r['state'],'COMPLETED');self.assertEqual(r['capture_id'],expected)
        self.assertTrue(r.get('capture_observed'));self.assertFalse(r['capture_started'])
        self.assertEqual(r['rehearsal_metrics']['capture_calls'],1)
        self.assert_capture_not_sent(p)
    def test_external_pending_preflight_keeps_receipt_and_sends_no_second_capture(self):
        p=self.ready('pending')
        remote=self.pp.capture(p['paypal_id'],'external-fixture-capture')
        expected=remote['purchase_units'][0]['payments']['captures'][0]['id']
        r=self.svc.capture(p['id'],self.owner)
        self.assertEqual(r['state'],'PAYMENT_PENDING');self.assertEqual(r['capture_id'],expected)
        self.assertTrue(r.get('capture_observed'));self.assertFalse(r['capture_started'])
        self.assertEqual(r['rehearsal_metrics']['capture_calls'],1)
        self.assert_capture_not_sent(p)
    def test_completed_missing_capture_receipt_can_be_reconciled(self):
        p=self.ready();done=self.svc.capture(p['id'],self.owner)
        expected=done['capture_id']
        with self.store.tx():
            raw=self.store.get(p['id']);raw['capture_id']=None;self.store.save(raw)
        r=self.svc.reconcile(p['id'],self.owner)
        self.assertEqual(r['state'],'COMPLETED');self.assertEqual(r['capture_id'],expected)
        self.assertEqual(r['rehearsal_metrics']['capture_calls'],1)
    def test_observed_pending_cannot_regress_to_authorized_capture(self):
        p=self.ready('pending');self.pp.capture(p['paypal_id'],'external-fixture-capture')
        r=self.svc.reconcile(p['id'],self.owner)
        self.assertEqual(r['state'],'PAYMENT_PENDING')
        with self.store.tx():
            remote=self.store.fixture_get(p['paypal_id']);remote['purchase_units'][0].pop('payments');remote['status']='APPROVED';self.store.fixture_save(remote)
        self.restart()
        r=self.svc.reconcile(p['id'],self.owner)
        self.assertEqual(r['state'],'CAPTURE_UNKNOWN');self.assertTrue(r.get('capture_observed'))
        self.assert_capture_not_sent(p)

    def test_observed_capture_identity_change_requires_review_and_keeps_history(self):
        p=self.ready('pending');self.pp.capture(p['paypal_id'],'external-fixture-capture')
        observed=self.svc.reconcile(p['id'],self.owner)
        expected=observed['capture_id']
        with self.store.tx():
            original=self.store.fixture_get(p['paypal_id'])
            corrupt=copy.deepcopy(original)
            corrupt['purchase_units'][0]['payments']['captures'][0]['id']='DIFFERENTCAPTURE'
            self.store.fixture_save(corrupt)
        r=self.svc.reconcile(p['id'],self.owner)
        self.assertEqual(r['state'],'REVIEW_REQUIRED');self.assertEqual(r['capture_id'],expected)
        self.assertEqual(r['last_capture_evidence']['id'],expected)
        self.assert_capture_not_sent(p)
        with self.store.tx():self.store.fixture_save(original)
        self.assertEqual(self.svc.reconcile(p['id'],self.owner)['capture_id'],expected)
    def test_cancelled_draft_cannot_create_even_if_display_state_is_approved(self):
        p=self.svc.plan(self.owner,{'need':'Patches for 20 bike repairs','budget':'80.00','currency':'USD','request_key':str(uuid.uuid4())})
        self.svc.approve(p['id'],self.owner,p['plan_hash']);self.svc.cancel(p['id'],self.owner)
        with self.store.tx():
            raw=self.store.get(p['id']);raw['state']='APPROVED';self.store.save(raw)
        with self.assertRaises(PolicyError):self.svc.create(p['id'],self.owner)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM fixture_orders').fetchone()[0],0)
    def test_legacy_external_completion_missing_proof_repairs_after_reopen(self):
        p=self.ready();remote=self.pp.capture(p['paypal_id'],'external-fixture-capture')
        expected=remote['purchase_units'][0]['payments']['captures'][0]['id']
        with self.store.tx():
            raw=self.store.get(p['id']);raw.update(state='COMPLETED',capture_id=None,capture_started=False)
            for key in ('capture_observed','last_capture_evidence','provider_state'):raw.pop(key,None)
            self.store.save(raw)
        self.restart()
        r=self.svc.reconcile(p['id'],self.owner)
        self.assertEqual(r['state'],'COMPLETED');self.assertEqual(r['capture_id'],expected)
        self.assertTrue(r['capture_observed']);self.assertEqual(r['last_capture_evidence']['id'],expected)
        self.assert_capture_not_sent(p)
    def test_legacy_completed_record_with_missing_remote_proof_cannot_regain_authority(self):
        p=self.ready()
        with self.store.tx():
            raw=self.store.get(p['id']);raw.update(state='COMPLETED',capture_id=None,capture_started=False)
            for key in ('capture_observed','last_capture_evidence','provider_state'):raw.pop(key,None)
            self.store.save(raw)
        self.restart()
        r=self.svc.reconcile(p['id'],self.owner)
        self.assertEqual(r['state'],'CAPTURE_UNKNOWN');self.assertTrue(r['capture_observed'])
        self.assert_capture_not_sent(p)

if __name__=='__main__':unittest.main(verbosity=2)
