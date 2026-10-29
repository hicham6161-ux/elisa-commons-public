"""Public-data-only EURUSD Dukascopy quote capture. No ELISA private strategy code."""
from __future__ import annotations
import datetime,hashlib,json,lzma,os,pathlib,struct,time,urllib.request,urllib.error

ROOT=pathlib.Path("public_bidask_20261029")
ROOT.mkdir(exist_ok=True)
BASE="https://datafeed.dukascopy.com/datafeed/EURUSD/2026/09"
HOURS=[12,13,14,15,16,17]
resources=[(f"2026-10-29-{h:02d}",f"{BASE}/29/{h:02d}h_ticks.bi5","PILOT_FIXED_DATE") for h in HOURS]
resources.extend([("2026-10-29-BID",BASE+"/29/BID_candles_min_1.bi5","FALLBACK_BID_CANDLE"),
                  ("2026-10-29-ASK",BASE+"/29/ASK_candles_min_1.bi5","FALLBACK_ASK_CANDLE"),
                  ("2026-10-28-16",BASE+"/28/16h_ticks.bi5","FORMAT_ONLY_CONTROL")])
def sha(b):return hashlib.sha256(b).hexdigest()
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def inspect_ticks(data):
    try:
        raw=lzma.decompress(data)
        if len(raw)%20:raise ValueError("record length mismatch")
        rec=struct.Struct(">IIIff"); n=len(raw)//rec.size
        if n<1:raise ValueError("no records")
        mn=3600000;mx=0;inverted=0;badclock=0;examples=[]
        for i in range(n):
            ms,ask,bid,askv,bidv=rec.unpack_from(raw,i*20)
            if ms>=3600000:badclock+=1
            if ask<bid:inverted+=1
            mn=min(mn,ms);mx=max(mx,ms)
            if i in (0,n//2,n-1):examples.append({"ms":ms,"ask":ask/100000,"bid":bid/100000})
        return {"decode":"PASS","records":n,"ms_min":mn,"ms_max":mx,"inverted":inverted,"badclock":badclock,"examples":examples}
    except Exception as e:return {"decode":"ERROR","error":repr(e)}
audit=[]
for name,url,role in resources:
 entry={"name":name,"url":url,"role":role,"utc_start":utc(),"attempts":[]}
 for attempt in range(1,3):
  start=time.monotonic()
  try:
   rq=urllib.request.Request(url,headers={"User-Agent":"ELISA-public-quote-research/1.0","Accept":"application/octet-stream"})
   with urllib.request.urlopen(rq,timeout=12) as r:
    b=r.read(7_000_000)
    entry.update({"http_status":r.status,"bytes_received":len(b),"sha256_raw":sha(b),
                  "date_header":r.headers.get("Date"),"content_type":r.headers.get("Content-Type"),
                  "last_modified":r.headers.get("Last-Modified"),
                  "etag":r.headers.get("ETag"),"actual_time_utc":utc()})
   (ROOT/(name+".bi5")).write_bytes(b)
   if name.endswith("BID") or name.endswith("ASK"):
     entry["format"]="BID_ASK_CANDLE_NOT_TICK"
   else: entry["tick_validation"]=inspect_ticks(b)
   entry["attempts"].append({"number":attempt,"ok":True,"elapsed_ms":round((time.monotonic()-start)*1000)})
   break
  except urllib.error.HTTPError as ex:
   entry["attempts"].append({"number":attempt,"ok":False,"http_status":ex.code,"elapsed_ms":round((time.monotonic()-start)*1000),"error":str(ex)[:150]})
   if ex.code in (403,404,429):break
  except Exception as ex:
   entry["attempts"].append({"number":attempt,"ok":False,"elapsed_ms":round((time.monotonic()-start)*1000),"error":repr(ex)[:250]})
  time.sleep(.6)
 entry["utc_end"]=utc()
 audit.append(entry)
 print("FETCH_STATUS="+json.dumps({"name":name,"status":entry.get("http_status"),"bytes":entry.get("bytes_received"),"attempts":entry["attempts"],"valid":entry.get("tick_validation",{}).get("decode")}),flush=True)
manifest={"schema":"PUBLIC_EURUSD_BIDASK_HIST_CAPTURE_001","host":"GitHub-hosted Linux runner","utc_finished":utc(),
          "no_api_token":True,"source":"datafeed.dukascopy.com","preregistered_pilot_day":"2026-10-29",
          "no_trade_execution":True,"resources":audit}
(ROOT/"SOURCE_MANIFEST.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
print("MANIFEST_STATUS="+json.dumps({"success_tick_hour_count":sum(r.get("tick_validation",{}).get("decode")=="PASS" and r["role"]=="PILOT_FIXED_DATE" for r in audit),
                                    "bytes_total":sum(r.get("bytes_received",0) for r in audit)}),flush=True)
