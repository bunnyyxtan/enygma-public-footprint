"""H5. Edited copies of the evidence must be rejected. Offline, no network.

Run from the repo root
  python -m unittest discover -s tests -v
Set FOOTPRINT_DATA=pilot to run against the pilot folder instead of the study.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import footprint as fp  # noqa: E402

DATA = os.environ.get("FOOTPRINT_DATA", "")
BASE = ROOT / DATA if DATA else ROOT
TRIALS = fp.load(BASE / "trials.json")
NEEDLES = fp.load(BASE / "needles.json")
RAW = BASE / "raw"
TEST_ID = next(t for t in TRIALS["trials"] if t["role"] == "test")["id"]
CONTROL_ID = next(t for t in TRIALS["trials"] if t["role"] == "control")["id"]
HASH = {t["id"]: t["hash"] for t in TRIALS["trials"]}


class Tamper(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(RAW, self.tmp / "raw")
        self.raw = self.tmp / "raw"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def edit(self, tid, kind, fn):
        p = fp.raw_path(tid, kind, self.raw)
        d = json.loads(p.read_text())
        fn(d)
        p.write_text(json.dumps(d))

    def problems(self, tid=TEST_ID):
        return fp.verify_trial(tid, HASH[tid], self.raw)

    def scan_failures(self):
        out = self.tmp / "out"
        with open(os.devnull, "w") as quiet:
            old, sys.stdout = sys.stdout, quiet
            try:
                fp.scan(TRIALS, NEEDLES, self.raw, out)
            finally:
                sys.stdout = old
        return fp.load(out / "scan.json")["failures"]

    def test_original_passes(self):
        for t in TRIALS["trials"] + TRIALS.get("baseline", []):
            self.assertEqual(fp.verify_trial(t["id"], t["hash"], self.raw), [], t["id"])
        self.assertFalse([f for f in self.scan_failures() if f.startswith(("H1", "H2", "H4"))])

    def test_block_hash_changed(self):
        self.edit(TEST_ID, "rpc", lambda d: d["tx"].update(blockHash="0x" + "ab" * 32))
        self.assertIn("block hash mismatch tx/receipt/block", self.problems())

    def test_status_flipped_to_failed(self):
        self.edit(TEST_ID, "rpc", lambda d: d["receipt"].update(status="0x0"))
        self.assertIn("receipt status not success", self.problems())

    def test_log_removed(self):
        self.edit(TEST_ID, "rpc", lambda d: d["receipt"]["logs"].pop())
        self.assertIn("explorer log count", self.problems())

    def test_input_byte_changed(self):
        def flip(d):
            s = d["tx"]["input"]
            d["tx"]["input"] = s[:-2] + ("00" if s[-2:] != "00" else "01")
        self.edit(TEST_ID, "rpc", flip)
        self.assertIn("explorer input differs from RPC input", self.problems())

    def test_tx_moved_out_of_block(self):
        self.edit(TEST_ID, "rpc", lambda d: d["block"].update(transactions=[]))
        self.assertIn("tx not in block's transaction list", self.problems())

    def test_log_data_changed(self):
        self.edit(TEST_ID, "rpc", lambda d: d["receipt"]["logs"][0].update(data="0x" + "11" * 32))
        self.assertIn("explorer logs differ from RPC logs", self.problems())

    def test_planted_address_is_caught(self):
        addr = NEEDLES["accounts"]["A"]["address"].lower()[2:]
        self.edit(TEST_ID, "rpc", lambda d: d["receipt"]["logs"][-1].update(
            data=d["receipt"]["logs"][-1]["data"] + "00" * 12 + addr))
        self.assertTrue(any(f.startswith(f"H1 {TEST_ID}") for f in self.scan_failures()))

    def test_control_without_amount_is_caught(self):
        wei = next(t for t in TRIALS["trials"] if t["id"] == CONTROL_ID)["amount_wei"]
        amt = fp.amount_forms(wei)["amount.be_min"].hex()
        fake = "ff" * (len(amt) // 2)
        def scrub(d):
            for l in d["receipt"]["logs"]:
                l["data"] = l["data"].replace(amt, fake)
                l["topics"] = [t.replace(amt, fake) for t in l["topics"]]
            d["tx"]["input"] = d["tx"]["input"].replace(amt, fake)
        self.edit(CONTROL_ID, "rpc", scrub)
        self.assertTrue(any(f.startswith(f"H2 {CONTROL_ID}") for f in self.scan_failures()))

    def test_planted_repeated_tag_is_caught(self):
        tests = [t["id"] for t in TRIALS["trials"] if t["role"] == "test"]
        tag = "c0ffee" * 10 + "abcd"
        for tid in tests[:2]:
            self.edit(tid, "rpc", lambda d: d["receipt"]["logs"][-1].update(data=d["receipt"]["logs"][-1]["data"] + tag))
        self.assertTrue(any(f.startswith("H4") and tag in f for f in self.scan_failures()))


if __name__ == "__main__":
    unittest.main()
