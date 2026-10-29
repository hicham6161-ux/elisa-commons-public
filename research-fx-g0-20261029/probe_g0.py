#!/usr/bin/env python3
"""Public, bounded, no-secret data-access gate. No trading, no secret/private ELISA code.

Uses HistData's normal free download form. Does not bypass 403/429, login,
anti-bot requirements, or publish underlying third-party market data.
"""
import datetime as dt
import hashlib
from html.parser import HTMLParser
import http.cookiejar
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

SYMBOLS = ("EURUSD", "GBPUSD")
YEAR, MONTH = 2026, 8
MAX_BYTES = 64 * 1024 * 1024
TIMEOUT = 18
BASE = "https://www.histdata.com"
OUT = Path("research_gate_artifacts")
FIELDS = {"tk", "date", "datemonth", "platform", "timeframe", "fxpair"}
USER_AGENT = "ELISA-Research-DataGate/1.0 (public research; bounded requests)"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class DownloadForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_form = False
        self.inputs = {}
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "form" and (d.get("id") == "file_down" or d.get("name") == "file_down"):
            self.in_form = True
        if tag == "input" and self.in_form:
            name = d.get("name") or d.get("id")
            if name in FIELDS:
                self.inputs[name] = d.get("value", "")
    def handle_endtag(self, tag):
        if tag == "form":
            self.in_form = False


def parse_form(html, symbol):
    f = DownloadForm()
    f.feed(html)
    if not FIELDS.issubset(f.inputs):
        raise ValueError("PUBLIC_FORM_UNAVAILABLE_OR_LOGIN_REQUIRED")
    if f.inputs["date"] != str(YEAR) or f.inputs["datemonth"] != f"{YEAR}{MONTH:02d}":
        raise ValueError("FORM_MONTH_MISMATCH")
    if f.inputs["platform"].upper() != "ASCII" or f.inputs["timeframe"].upper() != "T":
        raise ValueError("FORM_FORMAT_MISMATCH")
    if f.inputs["fxpair"].upper() != symbol:
        raise ValueError("FORM_SYMBOL_MISMATCH")
    if not re.fullmatch(r"[A-Za-z0-9]{8,128}", f.inputs["tk"]):
        raise ValueError("MISSING_FORM_TOKEN")
    return {k: f.inputs[k] for k in sorted(FIELDS)}


def inspect_tick_csv(archive):
    tickfiles = [i for i in archive.infolist() if i.filename.lower().endswith(".csv")]
    if len(tickfiles) != 1:
        raise ValueError(f"UNEXPECTED_CSV_FILES:{len(tickfiles)}")
    info = tickfiles[0]
    rows = bad = invalid_spreads = duplicates = 0
    prev = first = last = None
    max_gap_s = 0.0
    csv_hash = hashlib.sha256()
    est = dt.timezone(dt.timedelta(hours=-5))
    with archive.open(info) as fh:
        for raw_line in fh:
            csv_hash.update(raw_line)
            if not raw_line.strip():
                continue
            rows += 1
            try:
                line = raw_line.decode("ascii").strip()
                fields = line.split(",")
                if len(fields) < 3: raise ValueError("badcols")
                stamp, bid, ask = fields[:3]
                if not re.fullmatch(r"\d{8} \d{9}", stamp): raise ValueError("badtime")
                parsed = dt.datetime.strptime(stamp[:15], "%Y%m%d %H%M%S")
                ms = int(stamp[-3:]); parsed = parsed.replace(microsecond=ms*1000, tzinfo=est)
                this = parsed.astimezone(dt.timezone.utc)
                b, a = float(bid), float(ask)
                if not (b > 0 and a > 0 and b < 100000 and a < 100000): raise ValueError("badprice")
                if a < b: invalid_spreads += 1
                if prev:
                    gap = (this - prev).total_seconds()
                    if gap < 0: raise ValueError("NONMONOTONIC_TICKS")
                    if gap == 0: duplicates += 1
                    max_gap_s = max(max_gap_s, gap)
                if first is None: first = this
                last = this; prev = this
            except Exception:
                bad += 1
    return {"csv_member": info.filename, "csv_bytes": info.file_size,
            "csv_sha256": csv_hash.hexdigest(), "ticks": rows,
            "unparseable_rows": bad, "crossed_bidask_rows": invalid_spreads,
            "same_timestamp_rows": duplicates, "max_observed_gap_seconds": round(max_gap_s,3),
            "first_utc": first.isoformat() if first else None,
            "last_utc": last.isoformat() if last else None,
            "source_time_zone": "EST_FIXED_UTC_MINUS_5_NO_DST"}


def bounded_read(response):
    if int(response.headers.get("Content-Length") or 0) > MAX_BYTES:
        raise ValueError("SOURCE_FILE_EXCEEDS_FIXED_BUDGET")
    buf = io.BytesIO()
    while True:
        chunk = response.read(min(1024 * 1024, MAX_BYTES + 1 - buf.tell()))
        if not chunk: break
        buf.write(chunk)
        if buf.tell() > MAX_BYTES:
            raise ValueError("SOURCE_FILE_EXCEEDS_FIXED_BUDGET")
    return buf.getvalue()


def attempt(symbol):
    date = f"{YEAR}/{MONTH}"
    page = f"{BASE}/download-free-forex-historical-data/?/ascii/tick-data-quotes/{symbol.lower()}/{date}"
    result = {"symbol":symbol,"month":f"{YEAR}-{MONTH:02d}","source":page,"requests_max":2,"requests_made":0,"data_ready":False,"status":"NOT_ATTEMPTED"}
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    def request(req):
        result["requests_made"] += 1
        return opener.open(req,timeout=TIMEOUT)
    try:
        req = urllib.request.Request(page,headers={"User-Agent":USER_AGENT,"Accept":"text/html"})
        with request(req) as resp:
            result["page_status"] = resp.status
            html = bounded_read(resp).decode("utf-8",errors="replace")
        fields = parse_form(html,symbol)
        result["form_valid"] = True
        body = urllib.parse.urlencode(fields).encode("ascii")
        req = urllib.request.Request(f"{BASE}/get.php",data=body,headers={"User-Agent":USER_AGENT,"Origin":BASE,"Referer":page,"Content-Type":"application/x-www-form-urlencoded"})
        with request(req) as resp:
            result["download_status"] = resp.status
            raw = bounded_read(resp)
        result["download_bytes"] = len(raw)
        if not raw.startswith(b"PK\x03\x04"):
            result["status"] = "NOT_ZIP_OR_ACCESS_BLOCKED"
            return result
        result["zip_sha256"] = sha256(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            corrupt = zf.testzip()
            if corrupt:
                result["status"] = "ZIP_CRC_ERROR"
                return result
            result["crc_pass"] = True
            result.update(inspect_tick_csv(zf))
        result["data_ready"] = bool(result["ticks"] and result["unparseable_rows"] == 0 and result["crossed_bidask_rows"] == 0)
        result["status"] = "PASS_DATA_ACQUIRED" if result["data_ready"] else "FAIL_DATA_QUALITY"
        # Third-party raw tick bytes intentionally NOT published or uploaded to this public repository.
        return result
    except urllib.error.HTTPError as e:
        result["status"] = "HTTP_BLOCKED_OR_UNAVAILABLE"
        result["http_status"] = e.code
    except Exception as e:
        result["status"] = "FAILED_OR_UNAVAILABLE"
        result["error_class"] = type(e).__name__
        result["error_description"] = str(e)[:180]
    return result


def main():
    OUT.mkdir(exist_ok=True)
    rows = [attempt(s) for s in SYMBOLS]
    summary = {"schema":"ELISA_FX_G0_001","utc":dt.datetime.now(dt.timezone.utc).isoformat(),
               "purpose":"PUBLIC_DATA_ACCESS_ENGINEERING_ONLY_NOT_TRADING",
               "source":"HistData.com official free web form", "months":[f"{YEAR}-{MONTH:02d}"],
               "data_ready_count":sum(bool(x["data_ready"]) for x in rows),
               "total_http_requests":sum(x["requests_made"] for x in rows),
               "source_data_not_published":True,
               "results":rows}
    (OUT/"manifest.json").write_text(json.dumps(summary,sort_keys=True,indent=2,ensure_ascii=False),encoding="utf-8")
    print("ELISA_FX_G0_RESULT="+json.dumps(summary,sort_keys=True),flush=True)
    return 0 # completed access probe; SUCCESS here does not mean data gate passed

if __name__ == "__main__":
    sys.exit(main())