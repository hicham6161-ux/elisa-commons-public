#!/usr/bin/env python3
"""ELISA G0: lawful public-form read, integrity/QC, RSA-OAEP + AES256-GCM envelope.
Only encrypted vendor ZIP bytes and derived QC metadata leave this public CI runner.
This script DOES NOT trade, run a strategy or publish cleartext market prices.
"""
import collections
import datetime as dt
import hashlib
import http.cookiejar
import io
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SYMBOLS=('EURUSD','GBPUSD')
EXPECTED={
'EURUSD': {'zip':'09f1c164d36433e4a73958d0dcf153f9654488122ac397e2350f6c48b9df7b7a','csv':'96cf215fe8dde2405df7b56c6fc13914d266905fa3703b95430a9c4e1982330d'},
'GBPUSD': {'zip':'66a1ab6820d1fc293c1f480c2e4b53d866abbb29aebd2328d86f3e9285c55f56','csv':'8fc6f14c409f1b754a3ceb9011d63e085184cd8963c5c4a8f3a3881b40ae65c1'},
}
ROOT='https://www.histdata.com'
LIMIT=64*1024*1024
TIMEOUT_S=20
USER_AGENT='ELISA-Public-FX-G0-Quality-Control/1.0 (no credentials; bounded requests)'
OUT=Path('elisa_g0_private_ciphertext')
PUBLIC=Path(__file__).with_name('recipient_public_key.pem')
MAGIC=b'ELISA_G0_ENVELOPE_V1\0'

def sha(x): return hashlib.sha256(x).hexdigest()

def bounded_read(resp):
    if int(resp.headers.get('Content-Length') or 0)>LIMIT: raise ValueError('oversize response')
    o=bytearray()
    while True:
        chunk=resp.read(min(1<<20,LIMIT+1-len(o)))
        if not chunk: break
        o.extend(chunk)
        if len(o)>LIMIT: raise ValueError('oversize response')
    return bytes(o)

from html.parser import HTMLParser
class Form(HTMLParser):
    def __init__(self): super().__init__(); self.inside=False; self.fields={}
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=='form' and (d.get('id')=='file_down' or d.get('name')=='file_down'): self.inside=True
        if tag=='input' and self.inside:
            name=d.get('name') or d.get('id')
            if name in {'tk','date','datemonth','platform','timeframe','fxpair'}: self.fields[name]=d.get('value','')
    def handle_endtag(self,tag):
        if tag=='form': self.inside=False

def get_form(html,symbol):
    f=Form();f.feed(html)
    expected={'date':'2026','datemonth':'202608','platform':'ASCII','timeframe':'T','fxpair':symbol}
    for k,v in expected.items():
        if str(f.fields.get(k,'')).upper()!=v: raise ValueError('public form field mismatch: '+k)
    token=f.fields.get('tk','')
    if not re.fullmatch(r'[A-Za-z0-9]{8,128}',token): raise ValueError('public form token missing')
    return {k:f.fields[k] for k in ['tk','date','datemonth','platform','timeframe','fxpair']}

def read_vendor_file(symbol):
    # Exactly one GET and one POST; no retry or account/credential/bypass.
    url=f'{ROOT}/download-free-forex-historical-data/?/ascii/tick-data-quotes/{symbol.lower()}/2026/8'
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'text/html'})
    with opener.open(req,timeout=TIMEOUT_S) as r:
        if r.status!=200:raise ValueError('form GET not HTTP 200')
        html=bounded_read(r).decode('utf-8',errors='replace')
    fields=get_form(html,symbol)
    post=urllib.request.Request(ROOT+'/get.php',data=urllib.parse.urlencode(fields).encode('ascii'),headers={'User-Agent':USER_AGENT,'Content-Type':'application/x-www-form-urlencoded','Origin':ROOT,'Referer':url})
    with opener.open(post,timeout=TIMEOUT_S) as r:
        if r.status!=200:raise ValueError('download POST not HTTP 200')
        raw=bounded_read(r)
    return raw,url

def parse_csv_and_qc(raw,symbol):
    if not raw.startswith(b'PK\x03\x04'):raise ValueError('not ZIP bytes')
    if sha(raw)!=EXPECTED[symbol]['zip']:raise ValueError('source ZIP checksum differs from frozen G0')
    z=zipfile.ZipFile(io.BytesIO(raw))
    if z.testzip() is not None:raise ValueError('vendor ZIP CRC failure')
    files=[x for x in z.infolist() if x.filename.lower().endswith('.csv')]
    if len(files)!=1:raise ValueError('unexpected vendor CSV count')
    info=files[0]
    csvsha=hashlib.sha256(); rowcount=0; accepted=0
    err=collections.Counter(); backsteps_raw=0; backsteps_strict=0
    backstep_hist=collections.Counter(); magnitude_max=0; seconds_gt1=0; minutes_crossed=0
    prev_raw=prev_strict=None
    zero_spread=0; crossed=0; same_ms=0; gaps_gt_60s=0
    first=last=None; spread_min=1e9; spread_max=0
    tz=dt.timezone(dt.timedelta(hours=-5))
    for line_bytes in z.open(info):
        csvsha.update(line_bytes)
        if not line_bytes.strip():continue
        rowcount+=1
        try:
            line=line_bytes.decode('ascii').strip();s=line.split(',')
            if len(s)!=4:raise ValueError('columns')
            if not re.fullmatch(r'\d{8} \d{9}',s[0]):raise ValueError('stamp_regex')
            base=dt.datetime.strptime(s[0][:15],'%Y%m%d %H%M%S')
            ms=int(s[0][-3:]);tm=base.replace(tzinfo=tz,microsecond=ms*1000).astimezone(dt.timezone.utc)
            bid=float(s[1]);ask=float(s[2]);float(s[3])
            if not (math.isfinite(bid) and math.isfinite(ask) and 0<bid<10000 and 0<ask<10000):raise ValueError('price')
            if ask<bid:crossed+=1
            if ask==bid:zero_spread+=1
            sp=ask-bid;spread_min=min(spread_min,sp);spread_max=max(spread_max,sp)
            if prev_raw is not None:
                ds=(tm-prev_raw).total_seconds()
                if ds==0:same_ms+=1
                elif ds<0:
                    backsteps_raw+=1
                    magnitude_max=max(magnitude_max,-ds)
                    if -ds<=0.001:backstep_hist['<=1ms']+=1
                    elif -ds<=0.01:backstep_hist['<=10ms']+=1
                    elif -ds<=0.1:backstep_hist['<=100ms']+=1
                    elif -ds<=1:backstep_hist['<=1s']+=1
                    elif -ds<=60:backstep_hist['<=60s']+=1
                    else:backstep_hist['>60s']+=1
                    if ds< -1:seconds_gt1+=1
                    if tm.replace(second=0,microsecond=0)!=prev_raw.replace(second=0,microsecond=0):minutes_crossed+=1
                elif ds>60:gaps_gt_60s+=1
            if prev_strict is not None and tm<prev_strict:
                backsteps_strict+=1
            else:
                prev_strict=tm
            prev_raw=tm
            if first is None:first=tm
            last=tm;accepted+=1
        except Exception as e:
            err[str(e) if isinstance(e,ValueError) else type(e).__name__]+=1
    digest=csvsha.hexdigest()
    if digest!=EXPECTED[symbol]['csv']:raise ValueError('source CSV checksum differs from frozen G0')
    return {'symbol':symbol,'month':'2026-08','zip_sha256':sha(raw),'csv_sha256':digest,'zip_bytes':len(raw),'csv_bytes':info.file_size,'crc_pass':True,'total_rows':rowcount,'parsed_rows':accepted,'format_or_price_errors':dict(err),'crossed_bidask':crossed,'zero_spread':zero_spread,'spread_min_pips':round(spread_min/0.0001,4),'spread_max_pips':round(spread_max/0.0001,4),'duplicate_ms_in_sequence':same_ms,'backsteps_previous_row':backsteps_raw,'backsteps_strict_previous_accepted':backsteps_strict,'backstep_magnitude_bucket':dict(backstep_hist),'largest_backstep_seconds':round(magnitude_max,6),'backsteps_over_1s':seconds_gt1,'backsteps_crossing_minute_boundary':minutes_crossed,'forward_gaps_gt_60s_in_raw_order':gaps_gt_60s,'first_utc':first.isoformat() if first else None,'last_utc':last.isoformat() if last else None,'vendor_timezone':'fixed_EST_UTC-05_no_DST'}

def encrypt_for_library(raw,symbol,public_key):
    aes_key=os.urandom(32);nonce=os.urandom(12)
    aad=('ELISA_FX_G0_20261029_'+symbol).encode('ascii')
    cipher=AESGCM(aes_key).encrypt(nonce,raw,aad)
    wrapped=public_key.encrypt(aes_key,padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
    return MAGIC + struct.pack('>I',len(wrapped))+wrapped+nonce+struct.pack('>I',len(aad))+aad+cipher

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    pub_pem=PUBLIC.read_bytes();public_key=serialization.load_pem_public_key(pub_pem)
    res={'schema':'ELISA_G0_QC_PRIVATE_ARCHIVE_001','utc':dt.datetime.now(dt.timezone.utc).isoformat(),'public_key_sha256':sha(pub_pem),'raw_source_published':False,'workflow_output':'encrypted_vendor_zips_and_qc_metadata_only','economic_results':None,'rows':[]}
    for symbol in SYMBOLS:
        record={'symbol':symbol,'status':'FAILED','attempt_limit':2}
        try:
            raw,url=read_vendor_file(symbol)
            qc=parse_csv_and_qc(raw,symbol)
            enc=encrypt_for_library(raw,symbol,public_key)
            (OUT/(symbol+'_202608_original.zip.enc')).write_bytes(enc)
            record.update({'status':'INTEGRITY_PASS_QC_OBSERVED','source':url,'qc':qc,'sealed_sha256':sha(enc),'sealed_bytes':len(enc)})
            print('QC_'+symbol+'='+json.dumps(qc,sort_keys=True),flush=True)
        except Exception as e:
            record.update({'error_class':type(e).__name__,'error_message':str(e)[:200]})
            print('QC_'+symbol+'_FAIL='+json.dumps({'error_class':record['error_class'],'message':record['error_message']}),flush=True)
        res['rows'].append(record)
    (OUT/'manifest.json').write_text(json.dumps(res,sort_keys=True,indent=2),encoding='utf-8')
    print('ELISA_QC_PRIVATE_ARCHIVE_RESULT='+json.dumps({'status':[x['status'] for x in res['rows']],'public_key_sha256':res['public_key_sha256'],'utc':res['utc']}),flush=True)
    # Failed source acquisition is a legitimate recorded result, not a trading pass.
    return 0
if __name__=='__main__':sys.exit(main())