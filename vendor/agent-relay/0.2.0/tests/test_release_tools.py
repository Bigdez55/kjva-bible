import hashlib,json,tempfile,unittest,sys
from pathlib import Path
from support import gates
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from verify_candidate import verify_candidate

class CandidatePreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        p=self.root/'src'/'component.py';p.parent.mkdir();p.write_text('raise RuntimeError("must not import before verification")\n')
        self.file=p
        self.manifest={'format':1,'files':[{'path':'src/component.py','bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}]}
        (self.root/'CANDIDATE_MANIFEST.json').write_text(json.dumps(self.manifest))

    @gates('G31','G46')
    def test_candidate_preflight_checks_bytes_without_importing_target(self):
        self.assertTrue(verify_candidate(self.root)['verified'])

    @gates('G31','G42')
    def test_modified_input_is_rejected_before_import(self):
        self.file.write_text('print("replacement")')
        with self.assertRaises(ValueError):verify_candidate(self.root)

    @gates('G31','G42')
    def test_unlisted_executable_input_is_rejected(self):
        (self.root/'src'/'extra.py').write_text('print("unlisted")')
        with self.assertRaises(ValueError):verify_candidate(self.root)
