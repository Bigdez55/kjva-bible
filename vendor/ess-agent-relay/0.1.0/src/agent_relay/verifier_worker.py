"""Trusted unittest harness launched by the controller, never by a model-supplied PASS.

Candidate and oracle code run under the controller's OS account in this profile.
This harness does not claim isolation against deliberately malicious Python code.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import unittest


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--workspace",required=True)
    p.add_argument("--oracle",required=True)
    p.add_argument("--result",required=True)
    args=p.parse_args()
    workspace=Path(args.workspace)
    sys.path.insert(0,str(workspace))
    for child in sorted(workspace.iterdir()):
        if child.is_dir():sys.path.insert(0,str(child))
    try:
        suite=unittest.defaultTestLoader.discover(args.oracle,pattern="test*.py")
        result=unittest.TextTestRunner(stream=sys.stderr,verbosity=2).run(suite)
        report={"schema":1,"tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
                "skipped":len(result.skipped),"expected_failures":len(result.expectedFailures),
                "unexpected_successes":len(result.unexpectedSuccesses),"successful":result.wasSuccessful()}
    except BaseException as e:
        report={"schema":1,"tests":0,"failures":0,"errors":1,"skipped":0,"expected_failures":0,
                "unexpected_successes":0,"successful":False,"harness_error":repr(e)}
    with open(args.result,"x",encoding="utf-8") as f:
        json.dump(report,f,sort_keys=True);f.flush();os.fsync(f.fileno())
    return 0 if report["successful"] else 1


if __name__=="__main__":
    raise SystemExit(main())
