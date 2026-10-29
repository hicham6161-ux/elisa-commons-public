#!/usr/bin/env python3
"""ELISA index close-momentum test: public, generic research code only.
Only indicative OHLC. Never place real orders, never reinterpret these as quotes.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
OUT = Path("index_momentum_artifact")
EASTERN = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
D5 = dt.timedelta(minutes=5)
SYMS = ("SPY", "QQQ")
BEGIN = dt.datetime(2026, 9, 30, tzinfo=UTC)
END = dt.datetime(2026, 10, 29, tzinfo=UTC)
CUTOVER = dt.date(2026, 10, 21)
NOTIONAL = 10.0
MAIN_COST_BPS = 10
TIME_0930 = dt.time(9, 30)
TIME_1525 = dt.time(15, 25)
TIME_1535 = dt.time(15, 35)
TIME_1540 = dt.time(15, 40)
TIME_1555 = dt.time(15, 55)
BUDGET = 1_500_000


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)+"\n").encode()


def fetch(symbol: str):
    query = urllib.parse.urlencode({"period1": int(BEGIN.timestamp()), "period2": int(END.timestamp()),
                                    "interval": "5m", "includePrePost": "false", "events": "history"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent":"ELISA-Research-CloudGate/1.0 research only", "Accept":"application/json"})
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=22) as response:
        status = response.status
        size = int(response.headers.get("Content-Length") or 0)
        if size > BUDGET: raise ValueError("SOURCE_SIZE_LIMIT")
        raw = response.read(BUDGET + 1)
        if len(raw) > BUDGET: raise ValueError("SOURCE_BYTES_LIMIT")
        source_date = response.headers.get("Date")
    if status != 200: raise ValueError(f"HTTP_{status}")
    result = json.loads(raw)
    if result.get("chart", {}).get("error") or not result.get("chart", {}).get("result"):
        raise ValueError("NO_VALID_CHART_JSON")
    data = result["chart"]["result"][0]
    meta = data.get("meta", {})
    if meta.get("symbol") != symbol or meta.get("currency") != "USD" or meta.get("instrumentType") != "ETF":
        raise ValueError("WRONG_SOURCE_INSTRUMENT")
    if meta.get("exchangeTimezoneName") != "America/New_York":
        raise ValueError("WRONG_SESSION_TIMEZONE")
    return raw, {"url": url, "status": status, "bytes": len(raw), "sha256": sha(raw),
                 "response_date":source_date, "latency_ms":round((time.monotonic()-started)*1000),
                 "source_symbol":symbol, "currency":"USD", "timezone":"America/New_York"}, data


def valid_candles(data):
    stamps = data.get("timestamp", [])
    quote = data.get("indicators", {}).get("quote", [None])[0]
    if not quote: raise ValueError("NO_OHLC_ARRAYS")
    if any(len(quote.get(k, [])) != len(stamps) for k in ("open", "high", "low", "close")):
        raise ValueError("MISMATCHED_OHLC_ARRAYS")
    if sorted(stamps) != stamps or len(stamps) != len(set(stamps)):
        raise ValueError("TIMESTAMP_ORDER_OR_DUPLICATES")
    sessions = {}
    rejected = {"incomplete_values":0,"invalid_ohlc":0,"outside_regular_session":0,"bad_timestamp":0}
    for i, epoch in enumerate(stamps):
        local = dt.datetime.fromtimestamp(int(epoch), UTC).astimezone(EASTERN)
        if not (TIME_0930 <= local.time().replace(tzinfo=None) <= TIME_1555):
            rejected["outside_regular_session"] += 1
            continue
        if (local.minute - 30) % 5 != 0 and local.hour == 9:
            rejected["bad_timestamp"] += 1
            continue
        if local.minute % 5:
            rejected["bad_timestamp"] += 1
            continue
        vals = [quote[k][i] for k in ("open", "high", "low", "close")]
        if any(v is None or not isinstance(v, (float, int)) or not math.isfinite(v) for v in vals):
            rejected["incomplete_values"] += 1
            continue
        op, hi, lo, cl = map(float, vals)
        if min(op,hi,lo,cl) <= 0 or hi + 1e-8 < max(op,cl,lo) or lo-1e-8 > min(op,cl,hi):
            rejected["invalid_ohlc"] += 1
            continue
        daily = sessions.setdefault(local.date().isoformat(), {})
        key = local.strftime("%H:%M")
        if key in daily: raise ValueError("DUPLICATE_SAME_SESSION_BAR")
        daily[key] = {"open":op,"high":hi,"low":lo,"close":cl,"source_utc":local.astimezone(UTC).isoformat()}
    expected = [(dt.datetime(2000,1,1,9,30)+D5*i).strftime("%H:%M") for i in range(78)]
    valid = {}
    invalid_days = {}
    for day,bars in sorted(sessions.items()):
        if sorted(bars) != expected:
            invalid_days[day] = {"bars":len(bars),"missing":sorted(set(expected)-set(bars))[:12]}
        else:valid[day] = bars
    return valid, {"raw_bars":len(stamps),"valid_sessions":len(valid),"invalid_sessions":invalid_days,"rejections":rejected}


def pnl(entry: float, exit: float, sign:int, side_bps:int=MAIN_COST_BPS, notional:float=NOTIONAL)->float:
    assert sign in (-1, 1) and entry>0 and exit>0 and side_bps>=0
    f=side_bps/10000
    if sign == 1:
        return notional*((exit*(1-f)-entry*(1+f))/entry)
    return notional*((entry*(1-f)-exit*(1+f))/entry)


def build_ledger(symbol:str, sessions:dict):
    dates=sorted(sessions)
    ledger=[]; excluded={"missing_prior_or_proximity":0,"before_october":0,"outside_window":0}
    for i,day in enumerate(dates):
        d=dt.date.fromisoformat(day)
        if d<dt.date(2026,10,1):
            excluded["before_october"]+=1;continue
        if d>dt.date(2026,10,28):
            excluded["outside_window"]+=1;continue
        if i==0 or (d-dt.date.fromisoformat(dates[i-1])).days>4:
            excluded["missing_prior_or_proximity"]+=1;continue
        b=sessions[day]
        prev=sessions[dates[i-1]]["15:55"]["close"]
        signal=b["15:25"]["close"] / prev -1.0
        sign=1 if signal>0 else -1 if signal<0 else 0
        cutoff_utc=b["15:25"]["source_utc"]
        if sign==0:
            ledger.append({"symbol":symbol,"date_et":day,"split":"test" if d>=CUTOVER else "exploration",
                           "decision":"WAIT","signal_return":0,"decision_from_bar_start_utc":cutoff_utc,
                           "entry":None,"exit":None,"net_usd":None})
            continue
        entry=b["15:35"]["open"]
        exit=b["15:55"]["close"]
        net=pnl(entry,exit,sign)
        gross=pnl(entry,exit,sign,0)
        ledger.append({"symbol":symbol,"date_et":day,"split":"test" if d>=CUTOVER else "exploration",
                       "decision":"LONG" if sign>0 else "SHORT", "sign":sign,
                       "previous_close":prev,"cutoff_close":b["15:25"]["close"],
                       "signal_return":round(signal,12),"decision_from_bar_start_utc":cutoff_utc,
                       "decision_effective_et":"15:30", "entry_et":"15:35", "exit_et":"16:00",
                       "entry":round(entry,10),"exit":round(exit,10),"gross_usd":round(gross,8),
                       "net_usd":round(net,8),"gross_bps":round(10000*gross/NOTIONAL,6),
                       "net_bps":round(10000*net/NOTIONAL,6),
                       "inverse_net_usd":round(pnl(entry,exit,-sign),8),
                       "net_stress15_usd":round(pnl(entry,exit,sign,15),8),
                       "net_delay5_usd":round(pnl(b["15:40"]["open"],exit,sign),8)})
    return ledger, excluded


def summarize(ledger):
    out={}
    for symbol in SYMS:
        out[symbol]={}
        for split in ("exploration","test"):
            rows=[x for x in ledger if x["symbol"]==symbol and x["split"]==split]
            deals=[r for r in rows if r["decision"]!="WAIT"]
            net=sum(x["net_usd"] for x in deals)
            out[symbol][split]={"sessions_evaluable":len(rows),"trades":len(deals),
                                "longs":sum(x["sign"]==1 for x in deals),
                                "shorts":sum(x["sign"]==-1 for x in deals),
                                "gross_usd":round(sum(x["gross_usd"] for x in deals),7),
                                "net_usd_illustrative":round(net,7),
                                "win_after_costs":sum(x["net_usd"]>0 for x in deals),
                                "inverse_net_usd":round(sum(x["inverse_net_usd"] for x in deals),7),
                                "stress15_net_usd":round(sum(x["net_stress15_usd"] for x in deals),7),
                                "delay5_net_usd":round(sum(x["net_delay5_usd"] for x in deals),7),
                                "cash_baseline_usd":0,
                                "small_sample":True}
    return out


def encrypt_sources(rawmap:dict, recipient:Path):
    """Envelope encrypt original raw JSON; only ciphertext uploaded to public GH artifact."""
    from cryptography.hazmat.primitives.asymmetric import padding as asympadding
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = AESGCM.generate_key(bit_length=256)
    nonce=os.urandom(12)
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,blob in sorted(rawmap.items()):z.writestr(f"{name}_5m_original.json",blob)
    packed=out.getvalue()
    pub=serialization.load_pem_public_key(recipient.read_bytes())
    wrapped=pub.encrypt(key,asympadding.OAEP(mgf=asympadding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
    ciphertext=AESGCM(key).encrypt(nonce,packed,b"ELISA_CLOSE_MOMENTUM_001")
    return ({"source_ciphertext.bin":ciphertext,"source_wrapped_key.bin":wrapped,"source_nonce.bin":nonce},
            {"raw_zip_plaintext_bytes":len(packed),"raw_zip_sha256":sha(packed),"encryption":"AES256_GCM_RSA3072_OAEP_SHA256", "aad":"ELISA_CLOSE_MOMENTUM_001"})


def main():
    OUT.mkdir(exist_ok=True)
    protocol=ROOT/"PREREGISTRATION.json"
    prereg=json.loads(protocol.read_text())
    assert prereg["symbols"]==list(SYMS)
    rawmap={}; receipts={}; all_sessions={}; data_quality={}; ledger=[]; errors={}
    for symbol in SYMS:
        try:
            raw,receipt,data=fetch(symbol)
            sessions,qc=valid_candles(data)
            rawmap[symbol]=raw;receipts[symbol]=receipt;data_quality[symbol]=qc
            all_sessions[symbol]=sessions
            print(f"ELISA_SOURCE={symbol} bytes={receipt['bytes']} sha256={receipt['sha256']} complete_sessions={len(sessions)}",flush=True)
        except Exception as exc:
            errors[symbol]={"error_type":type(exc).__name__,"message":str(exc)[:160]}
            print(f"ELISA_SOURCE_FAILED={symbol} {errors[symbol]}",flush=True)
    exclusions={}
    for symbol,sessions in all_sessions.items():
        rows,exc=build_ledger(symbol,sessions);ledger+=rows;exclusions[symbol]=exc
    (OUT/"research_results.json").write_bytes(canonical({"schema":"ELISA_INDEX_CLOSE_MOMENTUM_RESULT_001",
       "date_utc":dt.datetime.now(UTC).isoformat(),"pre_registration_sha256":sha(protocol.read_bytes()),
       "summary":summarize(ledger),"source_receipts":receipts,"source_quality":data_quality,
       "excluded":exclusions,"errors":errors,"source_type":"INDICATIVE_OHLC_NOT_EXECUTABLE_BIDASK",
       "not_traded_real":True,"no_verified_short_execution":True,
       "conclusion":"ENGINEERING_DESCRIPTIVE_ONLY_NOT_PROFIT_VALIDATED" if ledger else "DATA_UNAVAILABLE"}))
    (OUT/"virtual_decisions.json").write_bytes(canonical(ledger))
    # Independent verifier does not import the strategy module: it opens the market source independently.
    with tempfile.TemporaryDirectory() as temp:
        temp=Path(temp)
        for symbol,raw in rawmap.items(): (temp/f"{symbol}.json").write_bytes(raw)
        cp=subprocess.run([sys.executable,str(ROOT/"audit_independent.py"),str(temp),str(OUT)],capture_output=True,text=True)
        print("ELISA_INDEPENDENT_AUDIT_STATUS",cp.returncode, cp.stdout[-1500:],cp.stderr[-1500:],flush=True)
        if cp.returncode != 0: raise RuntimeError("INDEPENDENT_AUDITOR_FAILED")
    if rawmap:
        parts, info=encrypt_sources(rawmap,ROOT/"transfer_public.pem")
        for name,data in parts.items():(OUT/name).write_bytes(data)
        (OUT/"encryption_metadata.json").write_bytes(canonical(info))
    total_files = {x.name:sha(x.read_bytes()) for x in OUT.iterdir() if x.is_file()}
    (OUT/"SHA256SUMS.json").write_bytes(canonical(total_files))
    print("ELISA_CLOSE_MOMENTUM_SUMMARY="+json.dumps({"sources":list(rawmap),"errors":errors,
         "n_decisions":len(ledger),"summary":summarize(ledger),"artifact_file_hashes":len(total_files)},ensure_ascii=False),flush=True)
    # Workflow success means completed bounded process; not that any return is positive.
    return 0
if __name__=="__main__":
    raise SystemExit(main())
