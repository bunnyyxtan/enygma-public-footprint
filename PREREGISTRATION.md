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
| T0 | A shields USDr from its public balance | 10 USDr | Control, address and amount are public by design |
| T1 | A sends to B | 1 USDr | Test |
| T2 | A sends to B | 2 USDr | Test, amount changed only |
| T3 | A sends to B | 5 USDr | Test, amount changed only |
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

None yet.
