"""Enygma Public onchain footprint study. Standard library only.

  python scripts/footprint.py collect  [--trials trials.json]   fetch raw RPC + explorer data into raw/
  python scripts/footprint.py keys                              fill public keys in needles.json from the registry
  python scripts/footprint.py verify   [--trials trials.json]   integrity checks on raw/ (no network)
  python scripts/footprint.py recheck                           fetch every hash again from the live RPC and compare
  python scripts/footprint.py scan     [--trials trials.json]   H1 to H4, writes results/
  python scripts/footprint.py manifest                          write MANIFEST.sha256
  python scripts/footprint.py check-manifest                    confirm files match MANIFEST.sha256

Exit code is non-zero when a check fails, so CI fails loudly.
"""
import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RPC = "https://testnet-rpc.rayls.com"
EXPLORER = "https://testnet-explorer.rayls.com/api/v2"
CHAIN_ID = 7295799


def http_json(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"content-type": "application/json", "user-agent": "enygma-footprint/1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def rpc(method, params):
    out = http_json(RPC, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if "error" in out:
        raise RuntimeError(f"{method}: {out['error']}")
    return out["result"]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def raw_path(tid, kind, raw_dir):
    return Path(raw_dir) / f"{tid}.{kind}.json"


# ---------------------------------------------------------------- collect

def collect(trials, raw_dir):
    Path(raw_dir).mkdir(exist_ok=True)
    chain = int(rpc("eth_chainId", []), 16)
    assert chain == CHAIN_ID, f"wrong chain {chain}"
    for t in trials["trials"] + trials.get("baseline", []) + trials.get("setup", []):
        h = t["hash"]
        tx = rpc("eth_getTransactionByHash", [h])
        receipt = rpc("eth_getTransactionReceipt", [h])
        if tx is None or receipt is None:
            print(f"{t['id']}: RPC returned no tx or receipt for {h}")
            continue
        block = rpc("eth_getBlockByNumber", [tx["blockNumber"], False])
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        raw_path(t["id"], "rpc", raw_dir).write_text(json.dumps(
            {"retrieved_utc": stamp, "endpoint": RPC, "chain_id": chain, "tx": tx, "receipt": receipt, "block": block}, indent=1))
        exp = {"tx": http_json(f"{EXPLORER}/transactions/{h}"), "logs": http_json(f"{EXPLORER}/transactions/{h}/logs")}
        # The other explorer tabs a stranger can open: internal txns, state changes, raw trace.
        for key, ep in (("internal", "internal-transactions"), ("state", "state-changes"), ("trace", "raw-trace")):
            try:
                exp[key] = http_json(f"{EXPLORER}/transactions/{h}/{ep}")
            except Exception as err:  # an empty or missing tab is recorded, not hidden
                exp[key] = {"error": str(err)}
        exp["retrieved_utc"] = stamp
        raw_path(t["id"], "explorer", raw_dir).write_text(json.dumps(exp, indent=1))
        print(f"{t['id']}: block {int(tx['blockNumber'], 16)} saved")


# ---------------------------------------------------------------- keys

REGISTRY = "0xA473291FFb33e2276F364fAE169f03c4406719e9"
# UserRegistered(address indexed user, uint256 pkSpend, bytes pkView, bytes mlKemAuditCt, bytes aesAuditCt)
USER_REGISTERED = "0x1a474a7a358619487a8219a6591e6747ed1ea6861a357f234398140f80e7c3fb"


def fetch_keys(needles, path, oldest=23_950_000, step=100_000):
    """Fill spend and view public keys for each account from its public registration event."""
    head = int(rpc("eth_blockNumber", []), 16)
    for name, acct in needles["accounts"].items():
        topic = "0x" + acct["address"][2:].lower().rjust(64, "0")
        logs, to = [], head
        while to > oldest and not logs:
            logs = rpc("eth_getLogs", [{"address": REGISTRY, "topics": [USER_REGISTERED, topic],
                                        "fromBlock": hex(to - step + 1), "toBlock": hex(to)}])
            to -= step
        if not logs:
            print(f"{name}: no registration found")
            continue
        d = hexbytes(logs[-1]["data"])
        off = int.from_bytes(d[32:64], "big")
        n = int.from_bytes(d[off:off + 32], "big")
        acct.update(spend="0x" + d[:32].hex(), view="0x" + d[off + 32:off + 32 + n].hex(),
                    registration_tx=logs[-1]["transactionHash"], registration_block=int(logs[-1]["blockNumber"], 16))
        print(f"{name}: spend {acct['spend'][:12]}..., view {n} bytes, from {acct['registration_tx']}")
    Path(path).write_text(json.dumps(needles, indent=1))


# ---------------------------------------------------------------- verify

def verify_trial(tid, h, raw_dir):
    """Return a list of problems for one trial. Empty list means it passed."""
    try:
        r = load(raw_path(tid, "rpc", raw_dir))
        e = load(raw_path(tid, "explorer", raw_dir))
    except (OSError, ValueError) as err:
        return [f"cannot read raw files ({err})"]
    tx, rc, blk = r["tx"], r["receipt"], r["block"]
    h = h.lower()
    checks = [
        (r.get("chain_id") == CHAIN_ID, "chain id"),
        (tx["hash"].lower() == h, "tx hash"),
        (rc["transactionHash"].lower() == h, "receipt hash"),
        (rc["status"] == "0x1", "receipt status not success"),
        (tx["blockHash"] == rc["blockHash"] == blk["hash"], "block hash mismatch tx/receipt/block"),
        (tx["blockNumber"] == rc["blockNumber"] == blk["number"], "block number mismatch"),
        (h in [x.lower() for x in blk["transactions"]], "tx not in block's transaction list"),
        (all(l["blockHash"] == blk["hash"] and l["transactionHash"].lower() == h for l in rc["logs"]), "log points at other block or tx"),
    ]
    et = e["tx"]
    checks += [
        (et.get("hash", "").lower() == h, "explorer hash"),
        (et.get("status") == "ok", "explorer status"),
        (et.get("block_number", et.get("block")) == int(tx["blockNumber"], 16), "explorer block"),
        (et.get("from", {}).get("hash", "").lower() == tx["from"].lower(), "explorer from"),
        (et.get("raw_input", "").lower() == tx["input"].lower(), "explorer input differs from RPC input"),
        (len(e["logs"].get("items", [])) == len(rc["logs"]), "explorer log count"),
    ]
    rpc_logs = {(int(l["logIndex"], 16), l["data"].lower(), tuple(x.lower() for x in l["topics"])) for l in rc["logs"]}
    exp_logs = {(it["index"], (it.get("data") or "0x").lower(), tuple(x.lower() for x in it.get("topics", []) if x)) for it in e["logs"].get("items", [])}
    checks.append((rpc_logs == exp_logs, "explorer logs differ from RPC logs"))
    return [msg for ok, msg in checks if not ok]


def verify(trials, raw_dir):
    bad = 0
    for t in trials["trials"] + trials.get("baseline", []) + trials.get("setup", []):
        probs = verify_trial(t["id"], t["hash"], raw_dir)
        print(f"{t['id']}: {'PASS' if not probs else 'FAIL ' + '; '.join(probs)}")
        bad += bool(probs)
    return bad


# ---------------------------------------------------------------- scan

def hexbytes(s):
    s = s[2:] if s.startswith("0x") else s
    return bytes.fromhex(s)


def tx_blobs(r):
    """Every byte string an explorer viewer can see in the transaction and its logs, sender field included."""
    tx, rc = r["tx"], r["receipt"]
    blobs = [("input", hexbytes(tx["input"])), ("to", hexbytes(tx["to"] or "0x")), ("from", hexbytes(tx["from"]))]
    for i, l in enumerate(rc["logs"]):
        blobs.append((f"log{i}.address", hexbytes(l["address"])))
        for j, t in enumerate(l["topics"]):
            blobs.append((f"log{i}.topic{j}", hexbytes(t)))
        blobs.append((f"log{i}.data", hexbytes(l["data"])))
    return blobs


def amount_forms(wei):
    n = int(wei)
    return {"amount.be_min": n.to_bytes(max(1, (n.bit_length() + 7) // 8), "big"), "amount.ascii": str(n).encode()}


def account_forms(name, acct):
    f = {}
    if acct.get("address"):
        a = acct["address"].lower()
        f[f"{name}.address.raw"] = hexbytes(a)
        f[f"{name}.address.ascii"] = a[2:].encode()
    if acct.get("username"):
        f[f"{name}.username"] = acct["username"].lstrip("@").encode()
    for k in ("spend", "view"):
        v = acct.get(k)
        if v:
            b = hexbytes(v)
            f[f"{name}.{k}"] = b
            if len(b) == 33 and b[0] in (2, 3):
                f[f"{name}.{k}.x"] = b[1:]
            if len(b) > 64:
                # a long key (the 1184 byte ML-KEM view key) could leak in pieces, so its ends are searched too
                f[f"{name}.{k}.first32"] = b[:32]
                f[f"{name}.{k}.last32"] = b[-32:]
    return f


def find_hits(blobs, forms):
    # A needle made of one repeated byte (like the zero address) matches padding everywhere, so it is refused.
    weak = [k for k, v in forms.items() if len(set(v)) <= 1]
    if weak:
        raise ValueError(f"search values too weak to mean anything: {weak}")
    return [{"value": label, "where": where}
            for label, needle in forms.items() for where, blob in blobs if needle in blob]


def shape(r):
    rc = r["receipt"]
    return {
        "input_bytes": len(hexbytes(r["tx"]["input"])),
        "selector": r["tx"]["input"][:10],
        "log_count": len(rc["logs"]),
        "events": [[l["address"].lower(), l["topics"][0][:10], len(l["topics"]), len(hexbytes(l["data"]))] for l in rc["logs"]],
        "gas_used": int(rc["gasUsed"], 16),
    }


AGGREGATE3 = bytes.fromhex("82ad56cb")  # Multicall3 aggregate3((address,bool,bytes)[])


def calls(inp):
    """Call bodies (selector stripped). A Multicall3 aggregate3 is unpacked into its inner calls,
    so their ABI words line up on 32 byte boundaries."""
    if inp[:4] != AGGREGATE3:
        return [inp[4:]]
    body = inp[4:]
    u = lambda o: int.from_bytes(body[o:o + 32], "big")
    arr = u(0)
    out = []
    for i in range(u(arr)):
        tup = arr + 32 + u(arr + 32 + 32 * i)  # (target, allowFailure, offset to bytes)
        b = tup + u(tup + 64)
        out.append(body[b + 32 + 4:b + 32 + u(b)])
    return out


def words(r):
    """32 byte words: ABI words of each call body after its selector, every topic, and data words."""
    out = set()
    for body in calls(hexbytes(r["tx"]["input"])):
        out |= {body[i:i + 32] for i in range(0, len(body) - 31, 32)}
    for l in r["receipt"]["logs"]:
        out |= {hexbytes(t) for t in l["topics"]}
        d = hexbytes(l["data"])
        out |= {d[i:i + 32] for i in range(0, len(d) - 31, 32)}
    return out


def scan(trials, needles, raw_dir, out_dir):
    Path(out_dir).mkdir(exist_ok=True)
    acct_forms = {}
    for name, acct in needles["accounts"].items():
        acct_forms.update(account_forms(name, acct))
    res, failures = {}, []
    for t in trials["trials"]:
        r = load(raw_path(t["id"], "rpc", raw_dir))
        hits = find_hits(tx_blobs(r), dict(acct_forms, **amount_forms(t["amount_wei"])))
        found = {x["value"] for x in hits}
        res[t["id"]] = {"role": t["role"], "action": t["action"], "hash": t["hash"],
                        "block": int(r["tx"]["blockNumber"], 16), "relayer_sender": r["tx"]["from"],
                        "hits": hits, "shape": shape(r)}
        if t["role"] == "test" and hits:
            failures.append(f"H1 {t['id']} shows {sorted(found)}")
        missing = [v for v in t.get("expect_visible", []) if v not in found]
        if missing:
            failures.append(f"H2 {t['id']} control did not detect {missing}")

    tests = [t["id"] for t in trials["trials"] if t["role"] == "test"]
    ref = tests[0] if tests else None
    keys = ("selector", "input_bytes", "log_count", "events")
    shape_diff = {tid: [k for k in keys if res[tid]["shape"][k] != res[ref]["shape"][k]] for tid in tests}
    for tid, d in shape_diff.items():
        if d:
            failures.append(f"H3 {tid} differs from {ref} in {d}")

    base_words = set()
    for b in trials.get("baseline", []):
        base_words |= words(load(raw_path(b["id"], "rpc", raw_dir)))
    counts = {}
    for tid in tests:
        for w in words(load(raw_path(tid, "rpc", raw_dir))):
            counts.setdefault(w, []).append(tid)
    # Public constants are not a sender tag: small integers (ABI offsets, lengths, flags, IDs),
    # the address of any contract that emitted a log here, and event signature hashes (topic 0).
    logs = [l for tid in tests for l in load(raw_path(tid, "rpc", raw_dir))["receipt"]["logs"]]
    public = {hexbytes(l["address"]).rjust(32, b"\0") for l in logs} | {hexbytes(l["topics"][0]) for l in logs}
    def constant(w):
        return int.from_bytes(w, "big") < 2 ** 32 or w in public
    shared = {w: ids for w, ids in counts.items() if len(ids) >= 2 and w not in base_words}
    constants = {w.hex(): ids for w, ids in shared.items() if constant(w)}
    repeated = {w.hex(): ids for w, ids in shared.items() if not constant(w)}
    for w, ids in repeated.items():
        failures.append(f"H4 word {w} repeats in {ids} and is in no baseline send")

    posthoc = posthoc_checks(trials, needles, acct_forms, raw_dir, tests)

    summary = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "trials": res,
               "shape_reference": ref, "shape_differences": shape_diff,
               "h4_baseline_sends": [b["id"] for b in trials.get("baseline", [])],
               "h4_repeated_public_constants": constants,
               "h4_repeated_words_not_in_baseline": repeated, "failures": failures,
               # The same count with no baseline at all: every shared word, and how many are public constants.
               "h4_without_baseline": {
                   "shared_words": sum(1 for ids in counts.values() if len(ids) >= 2),
                   "public_constants": sum(1 for w, ids in counts.items() if len(ids) >= 2 and constant(w)),
               },
               "posthoc_amendment_3": posthoc}
    Path(out_dir, "scan.json").write_text(json.dumps(summary, indent=1))
    for tid, x in res.items():
        s = x["shape"]
        print(f"{tid:5} {x['role']:8} in={s['input_bytes']:5} logs={s['log_count']:2} gas={s['gas_used']:8} hits={sorted({h['value'] for h in x['hits']})}")
    print("H4 repeated words not in baseline:", len(repeated))
    print("Post-hoc (amendment 3):", "; ".join(f"{k} {v['summary']}" for k, v in posthoc.items()))
    print("FAILURES" if failures else "ALL CHECKS PASSED", *failures, sep="\n  ")
    return len(failures)


def posthoc_checks(trials, needles, acct_forms, raw_dir, tests):
    """Checks added after the trials (amendment 3). Reported separately from H1 to H5."""
    out = {}
    # P1. The explorer's other tabs (internal txns, state changes, raw trace) searched as text.
    p1 = {}
    for t in trials["trials"]:
        e = load(raw_path(t["id"], "explorer", raw_dir))
        text = json.dumps({k: e.get(k) for k in ("internal", "state", "trace")}).lower()
        forms = dict(acct_forms, **amount_forms(t["amount_wei"]))
        # Text forms (username, ascii address, decimal amount) must stand alone: "1000000000000000000"
        # is "1" plus 18 zeros and would otherwise match inside any long run of zeros in hex data.
        def standalone(s):
            return re.search(r"(?<![0-9a-z])" + re.escape(s) + r"(?![0-9a-z])", text) is not None
        p1[t["id"]] = sorted(k for k, v in forms.items()
                             if v.hex() in text or (k.endswith(("username", "ascii")) and standalone(v.decode(errors="ignore").lower())))
    out["P1_other_explorer_tabs"] = {"hits": p1, "summary": "test sends with hits: " + str([k for k in tests if p1[k]])}
    # P2. Token contract addresses, to see whether a send reveals which token moved.
    p2 = {}
    for t in trials["trials"]:
        blobs = tx_blobs(load(raw_path(t["id"], "rpc", raw_dir)))
        p2[t["id"]] = {name: sorted({w for w, b in blobs if hexbytes(addr) in b}) for name, addr in needles.get("tokens", {}).items()}
    out["P2_token_addresses"] = {"hits": p2, "summary": "test sends with hits: " + str([k for k in tests if any(p2[k].values())]),
                                 "note": "USDr sits at 0x...0400, the same 20 bytes as the number 1024, so a USDr hit can be a plain number"}
    return out


# ---------------------------------------------------------------- recheck (online)

def recheck(trials, raw_dir):
    """Fetch every hash again from the live RPC and compare it with the saved copy.
    The offline checks only prove the saved files are consistent; this ties them back to the chain."""
    bad = 0
    for t in trials["trials"] + trials.get("baseline", []) + trials.get("setup", []):
        saved = load(raw_path(t["id"], "rpc", raw_dir))
        tx = rpc("eth_getTransactionByHash", [t["hash"]])
        rc = rpc("eth_getTransactionReceipt", [t["hash"]])
        blk = rpc("eth_getBlockByNumber", [tx["blockNumber"], False]) if tx else None
        tx_same = (tx is not None and tx["input"] == saved["tx"]["input"] and tx["from"] == saved["tx"]["from"]
                   and tx["blockHash"] == saved["tx"]["blockHash"] and blk["hash"] == saved["block"]["hash"])
        saved_logs = [(l["address"].lower(), [x.lower() for x in l["topics"]], l["data"].lower()) for l in saved["receipt"]["logs"]]
        if rc is not None:
            source = "RPC"
            rc_same = rc["status"] == saved["receipt"]["status"] and saved_logs == [
                (l["address"].lower(), [x.lower() for x in l["topics"]], l["data"].lower()) for l in rc["logs"]]
        else:
            # The public RPC stops serving receipts for older blocks. Status and logs then come from the explorer.
            source = "explorer (RPC no longer serves this receipt)"
            et = http_json(f"{EXPLORER}/transactions/{t['hash']}")
            el = http_json(f"{EXPLORER}/transactions/{t['hash']}/logs").get("items", [])
            live = sorted((it["index"], it["address"]["hash"].lower(), [x.lower() for x in it.get("topics", []) if x],
                           (it.get("data") or "0x").lower()) for it in el)
            mine = sorted((int(l["logIndex"], 16), a, tp, d) for l, (a, tp, d) in zip(saved["receipt"]["logs"], saved_logs))
            rc_same = (et.get("status") == "ok") == (saved["receipt"]["status"] == "0x1") and live == mine
        same = tx_same and rc_same
        print(f"{t['id']}: {'MATCHES CHAIN' if same else 'DIFFERS FROM CHAIN'} (tx and block from RPC, receipt from {source})")
        bad += not same
    print("recheck", "OK" if not bad else f"{bad} differ")
    return bad


# ---------------------------------------------------------------- manifest

MANIFEST_GLOBS = ["PREREGISTRATION.md", "README.md", "trials.json", "needles.json", "raw/*.json", "results/*.json",
                  "scripts/*.py", "tests/*.py", "media/screens/*.jpg", "media/explorer/*.png", "media/*.txt"]


def write_manifest():
    files = sorted({p for g in MANIFEST_GLOBS for p in ROOT.glob(g) if p.is_file()})
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT).as_posix()}" for p in files]
    (ROOT / "MANIFEST.sha256").write_text("\n".join(lines) + "\n")
    print(f"{len(lines)} files hashed")


def check_manifest():
    bad = 0
    for line in (ROOT / "MANIFEST.sha256").read_text().splitlines():
        digest, rel = line.split("  ", 1)
        p = ROOT / rel
        if not (p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == digest):
            print("MISMATCH", rel)
            bad += 1
    print("manifest", "OK" if not bad else f"{bad} mismatches")
    return bad


def arg(argv, flag, default):
    return argv[argv.index(flag) + 1] if flag in argv else default


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    trials = ROOT / arg(argv, "--trials", "trials.json")
    raw_dir = ROOT / arg(argv, "--raw", "raw")
    if cmd == "collect":
        collect(load(trials), raw_dir)
        return 0
    if cmd == "keys":
        npath = ROOT / arg(argv, "--needles", "needles.json")
        fetch_keys(load(npath), npath)
        return 0
    if cmd == "verify":
        return verify(load(trials), raw_dir)
    if cmd == "recheck":
        return recheck(load(trials), raw_dir)
    if cmd == "scan":
        return scan(load(trials), load(ROOT / arg(argv, "--needles", "needles.json")), raw_dir, ROOT / arg(argv, "--out", "results"))
    if cmd == "manifest":
        write_manifest()
        return 0
    if cmd == "check-manifest":
        return check_manifest()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
