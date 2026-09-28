"""Negative/positive unit tests of the acceptance evaluator, NOT fake runtime proofs.

Synthetic test reports are explicitly fixture data, never release evidence. The
installed policy loader is replaced only within these unit tests. Real release
verification uses the installed, sealed policy without monkeypatching.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from agent_relay import certification as cert
from agent_relay.codec import canonical,digest
from agent_relay.errors import RelayError
from agent_relay.store import private_write
from support import gates

class CertificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='rly-cert-');self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.report_path=self.base/'report.json';self.policy_path=self.base/'policy.json'
        self.key_path=self.base/'review.key';self.key=b'FIXTURE_ONLY_NOT_A_DEPLOYMENT_REVIEW_KEY'*2;private_write(self.key_path,self.key)
        original=cert.files('agent_relay').joinpath('data/original_gates.json').read_bytes()
        ids=[g['id'] for g in json.loads(original)['gates']]
        self.runtime=cert.runtime_identity()[0]
        self.policy={'profile':'EVALUATOR_UNIT_FIXTURE_NOT_RELEASE_CERTIFICATION','original_contract_sha256':digest(original),
                     'tests_sha256':'t'*64,'runner_sha256':'r'*64,'gates':[{'id':g,'required_tests':['fixture.'+g],'remaining_boundary':'Fixture-only unproven boundary' if g in ('G24','G27','G30') else ''} for g in ids]}
        self.report={'ok':True,'runtime_sha256':self.runtime,'runtime_after_sha256':self.runtime,'source_sha256':self.runtime,
                     'tests_sha256':'t'*64,'tests_after_sha256':'t'*64,'runner_sha256':'r'*64,'runner_after_sha256':'r'*64,
                     'environment':{'installed_mode':True},'tests_run':46,'records':[{'test':'fixture.'+g,'gate_ids':[g],'status':'PASS'} for g in ids]}
        patcher=patch.object(cert,'installed_policy',lambda:deepcopy(self.policy));patcher.start();self.addCleanup(patcher.stop)
        self.write()

    def write(self):
        self.report_path.write_bytes(canonical(self.report));self.policy_path.write_bytes(canonical(self.policy))

    def evaluate(self,decisions=None):return cert.evaluate(self.report_path,self.policy_path,decisions,self.key_path if decisions else None)

    def decisions(self,evaluation=None,expiry=None):
        evaluation=evaluation or self.evaluate()
        records=cert.unsigned_reviews(evaluation,'Fixture Reviewer')['decisions']
        for r in records:
            r['reason']='Explicit fixture review of a declared boundary; no production approval is issued.'
            if expiry is not None:r['expires_at']=expiry
        path=self.base/'decisions.json'
        path.write_bytes(canonical({'decisions':[cert.sign_review(r,self.key) for r in records]}))
        return path

    @gates('G30','G46')
    def test_passing_tests_do_not_silently_approve_remaining_boundaries(self):
        result=self.evaluate()
        self.assertFalse(result['ready']);self.assertFalse(result['full_original_certification'])
        self.assertEqual({g['id'] for g in result['gates'] if g['status']=='NEEDS_REVIEW'},{'G24','G27','G30'})

    @gates('G30','G46')
    def test_reviewed_exceptions_remain_exceptions_not_pass_or_global_certification(self):
        result=self.evaluate(self.decisions())
        self.assertTrue(result['ready']);self.assertEqual(result['reviewed_exception_count'],3)
        self.assertFalse(result['full_original_certification'])
        self.assertEqual(sum(g['status']=='EXCEPTED_REMAINING_BOUNDARY' for g in result['gates']),3)

    @gates('G30','G42')
    def test_missing_and_failed_required_tests_cannot_be_waived(self):
        for status in ('FAIL','SKIP','NOT_RUN','ERROR'):
            with self.subTest(status=status):
                self.report['records'][-1]['status']=status;self.write()
                result=self.evaluate(self.decisions())
                self.assertFalse(result['ready']);self.assertEqual(result['gates'][-1]['status'],'TESTS_MISSING_OR_FAILED')
        self.report['records'].pop();self.report['tests_run']=45;self.write()
        self.assertFalse(self.evaluate(self.decisions())['ready'])

    @gates('G30','G31','G46')
    def test_stale_runtime_and_changed_verifier_rejected(self):
        fields=['runtime_sha256','runtime_after_sha256','source_sha256','tests_sha256','tests_after_sha256','runner_sha256','runner_after_sha256']
        for field in fields:
            with self.subTest(field=field):
                original=self.report[field];self.report[field]='0'*64;self.write()
                with self.assertRaises(RelayError):self.evaluate()
                self.report[field]=original
        self.write()

    @gates('G30','G31')
    def test_source_mode_cannot_certify_installed_candidate(self):
        self.report['environment']['installed_mode']=False;self.write()
        with self.assertRaises(RelayError) as result:self.evaluate()
        self.assertEqual(result.exception.code,'NOT_INSTALLED_EVIDENCE')

    @gates('G30','G06')
    def test_duplicate_tests_or_gate_ids_and_omitted_gate_rejected(self):
        self.report['records'][1]=self.report['records'][0];self.write()
        with self.assertRaises(RelayError) as error:self.evaluate()
        self.assertEqual(error.exception.code,'DUPLICATE_TEST')
        self.report['records'][1]={'test':'fixture.G02','gate_ids':['G02'],'status':'PASS'}
        self.policy['gates'].pop();self.write()
        with self.assertRaises(RelayError) as error:self.evaluate()
        self.assertEqual(error.exception.code,'GATE_POLICY')

    @gates('G30','G42')
    def test_policy_cannot_be_replaced_with_easier_tests_or_empty_boundaries(self):
        edited=deepcopy(self.policy);edited['gates'][23]['remaining_boundary']=''
        self.policy_path.write_bytes(canonical(edited))
        with self.assertRaises(RelayError) as error:self.evaluate()
        self.assertEqual(error.exception.code,'GATE_POLICY_CHANGED')

    @gates('G30','G05')
    def test_review_is_bound_to_exact_evidence_not_reusable_on_another_run(self):
        decision=self.decisions()
        self.report['extra']='another execution';self.report_path.write_bytes(canonical(self.report))
        with self.assertRaises(RelayError) as error:self.evaluate(decision)
        self.assertEqual(error.exception.code,'REVIEW_BINDING')

    @gates('G30','G05')
    def test_expired_or_forged_review_is_rejected(self):
        with self.assertRaises(RelayError) as error:self.evaluate(self.decisions(expiry=time.time()-1))
        self.assertEqual(error.exception.code,'REVIEW_EXPIRED')
        path=self.decisions();data=json.loads(path.read_text());data['decisions'][0]['review']['reason']='tampered signed statement';path.write_bytes(canonical(data))
        with self.assertRaises(RelayError) as error:self.evaluate(path)
        self.assertEqual(error.exception.code,'REVIEW_SIGNATURE')

    @gates('G30','G05')
    def test_unsigned_template_is_not_an_approval_and_placeholder_reason_cannot_sign(self):
        template=cert.unsigned_reviews(self.evaluate(),'Fixture Reviewer')
        self.assertEqual(template['decisions'][0]['reason'],'TODO')
        with self.assertRaises(RelayError) as error:cert.sign_review(template['decisions'][0],self.key)
        self.assertEqual(error.exception.code,'REVIEW_REASON')

    @gates('G30','G33','G42')
    def test_unraisable_cleanup_error_blocks_acceptance_even_when_tests_claim_pass(self):
        self.report['unraisable_errors']=[{'type':'ResourceWarning','error':'not closed'}];self.write()
        self.assertFalse(self.evaluate(self.decisions())['ready'])

    @gates('G30','G31')
    def test_original_contract_hash_cannot_be_changed(self):
        self.policy['original_contract_sha256']='0'*64;self.write()
        with self.assertRaises(RelayError) as error:self.evaluate()
        self.assertEqual(error.exception.code,'CONTRACT_CHANGED')
