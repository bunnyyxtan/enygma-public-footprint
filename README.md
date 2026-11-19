# What does a private Enygma Public payment leave on chain?

A preregistered test on Rayls Public Chain testnet (chain 7295799), 19 Nov 2026.

**Short answer.** In five private sends of 1, 2 and 3 USDr to two receivers, none of the sender's or receivers' addresses, usernames, spend keys, view keys, the amount or the token's contract address appeared anywhere in the transaction, its logs, or the explorer's other tabs. All five had the same size and the same ten events. Two public controls (a shield and an unshield) showed the address and amount, so the scanner does catch them when they are there.

This is about the bytes of these five testnet sends. It is not a claim about timing, network data, the size of the anonymity set, mainnet, or the auditor, who can read every payment by design.

## Results

Times are block times in UTC. Gas is gas used.

| ID | What | Block | Time | Input bytes | Logs | Gas | Found by the scanner |
|----|------|-------|------|-------------|------|-----|----------------------|
| T0 | Shield 4.9775 USDr (control) | 24502945 | 08:34:15 | 2340 | 8 | 981,546 | A's address, A's spend key, amount |
| T1 | Send 1 USDr to B | 24503619 | 08:40:27 | 7300 | 10 | 2,103,973 | nothing |
| T2 | Send 2 USDr to B | 24503876 | 08:42:49 | 7300 | 10 | 2,103,279 | nothing |
| T3 | Send 3 USDr to B | 24507811 | 09:18:59 | 7300 | 10 | 2,193,660 | nothing |
| T4 | Send 1 USDr to C | 24507957 | 09:20:19 | 7300 | 10 | 2,225,188 | nothing |
| T5 | Send 1 USDr to B (repeat) | 24508175 | 09:22:19 | 7300 | 10 | 2,187,536 | nothing |
| T6 | Unshield 1 USDr (control) | 24508409 | 09:24:29 | 5476 | 11 | 2,149,276 | A's address, amount |

Full hashes are in `trials.json`. Raw RPC and explorer data are in `raw/`. The full scan output is `results/scan.json`.

## What a stranger can and cannot see, from these transactions

| Seen in T1 to T5 | Not seen in T1 to T5 |
|------------------|----------------------|
| That a private action happened, and when | Sender address or username |
| The relayer as the sender (0xa5f0...0Ac8) | Receiver address or username |
| The shared vault contract and vault ID 2 (the same ID for USDr and RLS) | Spend or view keys |
| Nullifiers, commitments and encrypted notes | The amount |
| Gas used, which varied about 6% between sends | Which token moved |
| How many notes were spent (two setup sends that spent two notes were 96 bytes longer) | Any value shared between the five sends that could tag one sender |

## Hypotheses (from `PREREGISTRATION.md`)

| | Check | Result |
|-|-------|--------|
| H1 | No account values or amount in T1 to T5 | Passed |
| H2 | The scanner finds address and amount in both controls | Passed |
| H3 | T1 to T5 have the same input size, log count and event list | Passed (gas varies, reported above) |
| H4 | No 32 byte word repeats across T1 to T5 except public constants | Passed (0 words, with and without the baseline) |
| H5 | Edited copies of the evidence are rejected | Passed (9 of 9) |

Post-hoc checks P1 (other explorer tabs) and P2 (token addresses) are described in Amendment 3. Both found nothing in T1 to T5.

## Check it yourself

```bash
git clone https://github.com/bunnyyxtan/enygma-public-footprint.git
cd enygma-public-footprint
python scripts/footprint.py check-manifest   # files match MANIFEST.sha256
python scripts/footprint.py verify           # saved data is consistent (block hash, tx in block, RPC equals explorer)
python scripts/footprint.py scan --out /tmp/rescan
python -m unittest discover -s tests -v      # the 9 tamper tests
python scripts/footprint.py recheck          # online, compares the saved data with the live chain
```

Python 3.12, standard library only. The first four commands run offline. `recheck` needs the network. The public RPC stops serving receipts for older blocks, so for those `recheck` takes status and logs from the explorer and prints which source it used. Do not rerun `collect` later, it would overwrite saved receipts the RPC no longer serves.

`media/terminal-fresh-clone.txt` is the output of these commands on a fresh clone.

## How the claims are labelled

| Claim | Status |
|-------|--------|
| Shield and unshield show address and amount, sends hide them | Documented by Rayls, and independently verified here for these transactions |
| The relayer submits every private action | Documented, and verified (the `from` field of every transaction here) |
| The auditor can read every payment but cannot move or freeze funds | Documented by Rayls, not tested here |
| The proof is 256 bytes and takes about 2 seconds | Reported by the app, not measured independently |
| The view key is 1184 bytes | Verified from the registration events, which matches the ML-KEM-768 public key size |
| Same size and events for different amounts and receivers | Own measurement, five sends |
| Two-note spends are 96 bytes longer | Own observation, two setup sends |

## Files

- `PREREGISTRATION.md` hypotheses, trial order, rules, and three dated amendments
- `trials.json` every transaction, with setup, trials and baseline
- `needles.json` the values searched for. The keys come from public registration events (`footprint.py keys`)
- `raw/` saved RPC and explorer responses
- `results/scan.json` scanner output
- `scripts/footprint.py` the scanner and checks
- `tests/test_tamper.py` tamper tests
- `pilot/` the scanner tried on older transactions before the study (not study data)
- `media/` screenshots, explorer captures (sponsored banners hidden) and the fresh clone output
- `MANIFEST.sha256` SHA-256 of every evidence file

## Sources

- Rayls, Enygma Public docs. https://docs.rayls.com/docs/enygma-public
- Enygma Public testnet app. https://enygma-testnet.rayls.com
- Rayls testnet explorer. https://testnet-explorer.rayls.com
