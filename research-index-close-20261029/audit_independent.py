#!/usr/bin/env python3
"""Independent reconstruction of ELISA index close momentum using raw source JSON.
Does NOT import the research strategy engine. Operates on strictly local files only.
"""
import datetime as dt
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

EASTERN=ZoneInfo("America/New_York")
UTC=dt.timezone.utc
ZERO=Decimal(0)
N=Decimal(10)


def check(ok:bool,message:str):
    global CHECKS
    CHECKS+=1
    if not ok:raise AssertionError(message)


def close(a,b,tol=0.000000011):
    return abs(float(a)-float(b))<=tol


def calc(x,y,sign,cost):
    b=Decimal(str(x));s=Decimal(str(y));f=Decimal(cost)/Decimal(10000)
    if sign==1:return N*((s*(1-f)-b*(1+f))/b)
    if sign==-1:return N*((b*(1-f)-s*(1+f))/b)
    raise ValueError("invalid sign")


def parse(raw:bytes):
    d=json.loads(raw)["chart"]["result"][0]
    prices=d["indicators"]["quote"][0];tss=d["timestamp"]
    check(len(tss)==len(set(tss)),"duplicate source timestamp")
    check(tss==sorted(tss),"unsorted source timestamp")
    days={}
    for i,ts in enumerate(tss):
        stamp=dt.datetime.fromtimestamp(ts,UTC).astimezone(EASTERN)
        tim=stamp.strftime("%H:%M")
        if tim<"09:30" or tim>"15:55" or stamp.minute%5:continue
        vals=[prices[k][i] for k in ("open","high","low","close")]
        if any(v is None for v in vals):continue
        op,hi,lo,cl=vals
        if not min(vals)>0 or hi+1e-8<max(vals) or lo-1e-8>min(vals):continue
        day=stamp.date().isoformat()
        check(tim not in days.setdefault(day,{}),"duplicate daily bar")
        days[day][tim]=(float(op),float(cl),stamp.astimezone(UTC).isoformat())
    start=dt.datetime(2001,1,1,9,30)
    exp={(start+dt.timedelta(minutes=5*j)).strftime("%H:%M") for j in range(78)}
    return {k:v for k,v in days.items() if set(v)==exp}


def main(folder:Path,out:Path):
    global CHECKS
    CHECKS=0
    results=json.loads((out/"research_results.json").read_bytes())
    actual=json.loads((out/"virtual_decisions.json").read_bytes())
    check(results["source_type"]=="INDICATIVE_OHLC_NOT_EXECUTABLE_BIDASK","source type")
    check(results["not_traded_real"] is True,"funds")
    reconstructed=[]
    per={}
    for sym in ("SPY","QQQ"):
        raw_path=folder/f"{sym}.json"
        if not raw_path.exists():
            check(sym not in results["source_receipts"],"missing source receipt")
            continue
        raw=raw_path.read_bytes()
        check(hashlib.sha256(raw).hexdigest()==results["source_receipts"][sym]["sha256"],"raw sha")
        sessions=parse(raw)
        dates=sorted(sessions)
        excluded=0
        for j,day in enumerate(dates):
            d=dt.date.fromisoformat(day)
            if not(dt.date(2026,10,1)<=d<=dt.date(2026,10,28)):continue
            if j==0 or (d-dt.date.fromisoformat(dates[j-1])).days>4:
                excluded+=1;continue
            recent=sessions[day];prior=sessions[dates[j-1]]
            ref=prior["15:55"][1]
            last_close=recent["15:25"][1]
            sign=1 if last_close>ref else -1 if last_close<ref else 0
            row={"symbol":sym,"date_et":day,"split":"test" if d>=dt.date(2026,10,21) else "exploration",
                 "decision":"WAIT" if sign==0 else "LONG" if sign==1 else "SHORT"}
            if sign:
                entry=recent["15:35"][0]
                exit=recent["15:55"][1]
                row.update({"sign":sign,"entry":entry,"exit":exit,"previous_close":ref,"cutoff_close":last_close,
                   "gross_usd":calc(entry,exit,sign,0),"net_usd":calc(entry,exit,sign,10),
                   "inverse_net_usd":calc(entry,exit,-sign,10),
                   "net_stress15_usd":calc(entry,exit,sign,15),
                   "net_delay5_usd":calc(recent["15:40"][0],exit,sign,10),
                   "decision_from_bar_start_utc":recent["15:25"][2]})
            reconstructed.append(row)
        per[sym]={"valid_sessions":len(dates),"excluded_missing_prior":excluded}
    actual_sorted=sorted(actual,key=lambda x:(x["symbol"],x["date_et"]))
    exp_sorted=sorted(reconstructed,key=lambda x:(x["symbol"],x["date_et"]))
    check(len(actual_sorted)==len(exp_sorted),"ledger length")
    for old,new in zip(actual_sorted,exp_sorted):
        for key in ("symbol","date_et","split","decision"):
            check(old[key]==new[key],f"ledger {key}")
        if new["decision"]=="WAIT":
            check(old.get("net_usd") is None,"wait profit")
            continue
        for key in ("entry","exit","previous_close","cutoff_close","gross_usd","net_usd","inverse_net_usd","net_stress15_usd","net_delay5_usd"):
            check(close(old[key],new[key]),f"ledger {key}")
        check(old["sign"]==new["sign"],"long short sign")
        check(old["decision_from_bar_start_utc"]==new["decision_from_bar_start_utc"],"cutoff time")
        check(old["entry_et"]=="15:35" and old["decision_effective_et"]=="15:30","entry causal order")
        check(old["exit_et"]=="16:00","exit time")
    # Independently aggregate sums, do not trust summary as calculated by the strategy.
    for sym in ("SPY","QQQ"):
        for split in ("exploration","test"):
            a=[t for t in exp_sorted if t["symbol"]==sym and t["split"]==split]
            t=[x for x in a if x["decision"]!="WAIT"]
            got=results["summary"][sym][split]
            check(len(t)==got["trades"],"aggregate count")
            check(len(a)==got["sessions_evaluable"],"aggregate days")
            check(sum(x["sign"]==1 for x in t)==got["longs"],"aggregate long")
            check(sum(x["sign"]==-1 for x in t)==got["shorts"],"aggregate short")
            check(sum(x["net_usd"]>0 for x in t)==got["win_after_costs"],"win count")
            for field,input_field in [("net_usd_illustrative","net_usd"),("gross_usd","gross_usd"),
                                       ("inverse_net_usd","inverse_net_usd"),("stress15_net_usd","net_stress15_usd"),
                                       ("delay5_net_usd","net_delay5_usd")]:
                check(close(got[field],sum(x[input_field] for x in t),0.00000015),"aggregate "+field)
    audit={"schema":"ELISA_CLOSE_MOMENTUM_INDEPENDENT_AUDIT_001","status":"PASS" if reconstructed else "NO_EVALUABLE_DATA",
           "checks":CHECKS,"errors":[],"reconstructed_decisions":len(reconstructed),"source_sessions":per,
           "uses_strategy_engine":False,"market_order_executed":False,"broker_quotes_validated":False}
    (out/"independent_audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
    print("ELISA_AUDIT="+json.dumps(audit,sort_keys=True),flush=True)
    return 0
if __name__=="__main__":
    raise SystemExit(main(Path(sys.argv[1]),Path(sys.argv[2])))
