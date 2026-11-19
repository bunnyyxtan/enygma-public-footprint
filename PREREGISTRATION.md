# Preregistration

What can someone with only the public explorer learn about a private payment on Enygma Public testnet?

This file is written and pushed before trial 1. Its commit time on GitHub is the record that the hypotheses, trial order and decision rules came first. Anything changed after that gets a dated amendment at the bottom, nothing is edited in place.

## Setting

- Network. Rayls Public Chain testnet, chain ID 7295799, RPC https://testnet-rpc.rayls.com, explorer https://testnet-explorer.rayls.com
- App. Enygma Public testnet demo, https://enygma-testnet.rayls.com
- Token. USDr (USD Rayls), 18 decimals. Gas for private actions is paid in shielded RLS.
- Every private action is submitted by a relayer, so the relayer is the transaction sender. That part was already checked in my episode 2 post and is not the question here.

## Accounts

- A is a fresh account made for this study. It is the only sender.
- B and C are receivers. They are earlier test accounts of mine. For a receiver it does not matter whether the account is fresh, the test is whether its details show up.
- For each account the study records the EVM address, username, spend public key and view public key as shown in the app. These go in `needles.json` before trial 1.

## Trials, in this order

| ID | Action | Amount | Role |
|----|--------|--------|------|
| T0 | A shields USDr from its public balance | 10 USDr (5, see amendment 1) | Control, address and amount are public by design |
| T1 | A sends to B | 1 USDr | Test |
| T2 | A sends to B | 2 USDr | Test, amount changed only |
| T3 | A sends to B | 5 USDr (3, see amendment 1) | Test, amount changed only |
| T4 | A sends to C | 1 USDr | Test, recipient changed only |
| T5 | A sends to B | 1 USDr | Test, repeat of T1 |
| T6 | A unshields to its own address | 1 USDr | Control, address and amount are public by design |

A failed or stuck trial is kept and logged with its hash. It is not quietly rerun. A rerun gets a new ID (for example T2b) and both appear in the results.

## What gets scanned

For each trial, the full transaction input and every log (all topics and data) from the RPC, pinned to the block hash it was included in. The explorer copy of the same transaction is saved too and must agree. The RPC and explorer are both run by Rayls, so they are two endpoints of the same operator, not independent sources.

Search values, all byte aligned, anywhere in the bytes

- Every account address as 20 raw bytes (this also covers the 32 byte padded form) and as its ASCII hex text
- Every username as UTF-8 bytes
- Every spend and view public key as recorded, full length
- The trial amount in base units as its shortest big endian byte string (covers any uint width) and as ASCII decimal text

## Hypotheses

- H1 absence. In T1 to T5 none of the search values for A, B or C appear in the input or logs.
- H2 detector works. In T0 and T6 the scanner finds A's address and the trial amount. If it does not, the scanner is broken and H1 means nothing.
- H3 same shape. T1 to T5 have the same input length, the same number of logs, and the same ordered list of event types and data lengths. Gas used is reported as measured. A difference is a finding to report, not a failure to hide.
- H4 no repeated sender tag. No 32 byte word appears in two or more of T1 to T5 unless it also appears in a baseline send by someone else, or is a public constant. Public constant means a number below 2^32 (ABI offsets, lengths, IDs) or the address of a contract that emitted a log in these transactions. Constants are still listed in the results.
- H5 tamper check. The verifier rejects every edited copy of the evidence in `tests/`.

Baseline sends for H4 are picked by a fixed rule after the trials. The 3 relayer transactions closest in time to T1 to T5 that have the same input length and event list as T1 and are not part of this study. If fewer than 3 exist, every one that does is used and the count is reported.

Search values made of one repeated byte (like the zero address) are refused by the script, because they match padding everywhere.

## Pilot

Before writing this file I ran the scanner on five transactions from my earlier QA session (shield, send, invite, claim, unshield) to test it. Those are in `pilot/` and are not study data. The pilot found that a zero address placeholder matched padding, which is why weak search values are now refused.

## Decision rules

- Any hit in H1, or a repeated word in H4, is reported as found. If it looks security relevant, Rayls gets it privately first and the article waits.
- Things the shape shows anyway (which vault and token, that a payment happened, when) are reported as what the public can see, measured.
- No result is dropped because it is inconvenient.

## Out of scope

The relayer, the per deployment auditor who can read every payment by design, timing analysis, network level metadata, the anonymity set size, and anything off chain. The claim is only about these values in these bytes on this testnet.

## Amendments

### Amendment 1, 19 Nov 2026, before T0

Account A was created and funded. The faucet turned out to give 5 USDr and 50 RLS per claim, with a 3 hour wait between claims, so the planned amounts did not fit.

- T0 shields 5 USDr, not 10.
- T3 sends 3 USDr, not 5. The amount still differs from T1 and T2, which is what the test needs.
- The rest of A's USDr comes from the shielded faucet (5 USDr straight into the shielded balance) once the wait is over. That claim is saved but is not a trial.
- Gas. A shields part of its public RLS to pay gas for private actions. That shield is a setup step called S1. It is saved but is not a trial.
- Trials will run across the faucet wait. Times and blocks are in the results.
- B is @qa-test and C is @notyourbunnyy.
- The spend and view public keys used as search values are read from each account's public registration event with `footprint.py keys`. Registration is public by design (the app says so), so those keys showing up in the registration is expected. The question is whether they show up in a payment.
- The view key is 1184 bytes, so besides the full key the scanner also searches its first and last 32 bytes.
- The setup transactions (faucet, registration) are listed in `trials.json` under `setup`.

### Amendment 2, 19 Nov 2026, after T2 and before T3

A change to how H4 cuts the transaction input into 32 byte words. It was found when T1 and T2 were scanned before any baseline sends had been picked, and it is logged here because it changes the analysis after seeing data.

- Every send is a Multicall3 `aggregate3` call holding two inner calls (3424 bytes each in T1 and T2). Cutting the outer input every 32 bytes put the inner calls 4 bytes off, so ABI offsets and selectors showed up as fake unique words. The script now unpacks `aggregate3` and cuts each inner call after its own selector.
- Event signature hashes (topic 0 of a log) are now counted as public constants, alongside small numbers and emitting contract addresses. They are the same for every user of the contract.
- Nothing else changed. H1 to H3 and H5 are untouched. The tamper tests still pass, including the planted repeated tag.
- With the change, T1 and T2 share no word outside public constants, before any baseline is applied. The scan output from before the change is kept in git history (commit with message "T0, S1, T1, T2 collected and scanned").

### Amendment 3, 19 Nov 2026, after all trials

Everything here was added or found after T6. None of it changes H1 to H5 or their results. The new checks are reported apart from H1 to H5 as post-hoc checks.

What happened differently from the plan

- T0 shielded 4.9775 USDr (the app's MAX of the 5 USDr faucet balance), not 5. The 0.25% fee was paid on top.
- The shielded faucet was not used. A was funded by two private sends from my own other account (F1 and F2 in `trials.json`), at 09:14 and 09:16 UTC.
- S2 is a shield of A's last 5.3153 public RLS, made in the app at 09:12 UTC. It was not in the plan. It is listed under setup.
- The screen recording starts at S1. Account creation, the faucet, registration and T0 have screenshots only.
- The trial times in `README.md` come from the block headers in `raw/`, not from my notes.

Post-hoc checks added after the trials

- P1. The explorer's other tabs (internal transactions, state changes, raw trace) are saved for every transaction and searched as text. The first run flagged the amount in T1 to T5. That was a false match, because 1000000000000000000 is a 1 and 18 zeros and appears inside long runs of zeros in hex data. Text values now have to stand alone. After the fix, T1 to T5 show nothing and both controls still show the address and amount.
- P2. The two token contract addresses (USDr and RLS) are searched in every transaction. Neither appears in T1 to T5. Both controls show them. The USDr contract sits at 0x...0400, the same 20 bytes as the number 1024, so a USDr hit alone would not be proof.
- The sender field (`from`) is now part of the scanned bytes. It is the relayer in every transaction.
- H4 was also run with no baseline at all. It still found 0 repeated words, so the baseline sends did not hide anything.
- The vault ID in the logs is 2 for both USDr and RLS, so it does not tell which token moved.
- F1 and F2 each spend two notes. Their payment call is 3520 bytes instead of 3424, which makes the whole input 7396 bytes instead of 7300. This comes from two setup sends, not from the trials.

Evidence handling

- `footprint.py recheck` fetches every hash again and compares it with the saved copy. The public RPC stops serving receipts for older blocks (X1 to X3 already return none), so recheck then takes status and logs from the explorer and says so.
- Timing of the preregistration. GitHub Actions run 44486567904 was triggered by the first push at 08:19:02 UTC. Account A's first transaction is at 08:26:04 UTC by block time. Git commit dates come from my local clock, the Actions run time does not.
- Explorer screenshots in `media/explorer/` were taken with sponsored banners hidden by a page script. Nothing else on the page was changed.
