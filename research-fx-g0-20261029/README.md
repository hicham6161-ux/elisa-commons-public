# ELISA RESEARCH DATA & JUMP HYPOTHESIS — G0 / 001

Date: 2026-10-29. Goal: real **data access** check for bid/ask ticks. Not an economic test, trading advice, or strategy promotion.

## Result before cloud attempt

- TrueFX official historical-download page requires login. No account was created; terms restrict dissemination of prices.
- HistData.com has a free, no-account Generic ASCII tick-download procedure and says tick fields are timestamp, BID, ASK, volume, with timezone EST fixed (UTC-5) without DST.
- This source is **indicative**, not a confirmed quote from a retail broker. No real trading is authorized.
- Offline software checks of acquisition parsing: 5/5 PASS.

## Planned cloud smoke

On a dedicated branch in user's existing public `elisa-commons-public` repo, run a standard GitHub Actions Ubuntu runner; read the HistData normal public form and download up to two historical monthly ZIPs (EURUSD and GBPUSD, August 2026) if accessible. Validate source bytes, CRC, timestamps and bid/ask. Save ONLY non-sensitive counts/hashes/logs in a public artifact; raw third-party prices are intentionally not redistributed or published there. If blocked, record the exact blocker. Once source works, a private permitted channel for raw archival must be set up before economic tests.

## Boundaries

No fees, paid accounts, bypass of access controls, login handling, private ELISA code, broker API, orders, live/leveraged positions, mock trading signals, retro-optimization or economic conclusions.

## Tests

```
python -m unittest discover -s . -p test_probe_g0.py -v
```

## Expected publication

The `research-fx-g0-20261029/` folder contains only generic acquisition code and public data-source names. The workflow is `.github/workflows/elisa-fx-g0-20261029.yml` on an isolated branch; main remains unchanged.