#!/usr/bin/env python3
"""ELISA research-only: bounded official HistData public-form acquisition, encrypted-only outbound.

Never commits or uploads plaintext market data, credentials, or any ELISA private engine.
2 public HTTP requests per symbol; no retries or access-control bypass.
"""
import datetime as dt
import hashlib
from html.parser import HTMLParser
from http.cookiejar import CookieJar
import io
import json
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import secrets

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'encrypted_evidence'
OUT.mkdir(exist_ok=True)
BASE='https://www.histdata.com'
SYMBOLS=('EURUSD','GBPUSD')
YEAR,MONTH=2026,9
MAX_SIZE=40*1024*1024
TIMEOUT=20
UA='ELISA-FX-Session-Research/1.0 (bounded, no-account, no-trades)'
FIELDS={'tk','date','datemonth','platform','timeframe','fxpair'}
PUBLIC_KEY = ROOT/'research_recipient.pem'

def sha256(b):return hashlib.sha256(b).hexdigest()

class Form(HTMLParser):
    def __init__(self):
        super().__init__();self.active=False;self.f={}
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=='form' and (d.get('id')=='file_down' or d.get('name')=='file_down'): self.active=True
        if tag=='input' and self.active:
            key=d.get('name') or d.get('id')
            if key in FIELDS:self.f[key]=d.get('value','')
    def handle_endtag(self,tag):
        if tag=='form':self.active=False

def limited_response(resp):
    declared=int(resp.headers.get('Content-Length') or 0)
    if declared>MAX_SIZE:raise ValueError('DOWNLOAD_DECLARED_OVER_BUDGET')
    b=resp.read(MAX_SIZE+1)
    if len(b)>MAX_SIZE:raise ValueError('DOWNLOAD_OVER_BUDGET')
    return b

def capture(pair,recipient):
    path=f'/download-free-forex-historical-data/?/ascii/tick-data-quotes/{pair.lower()}/{YEAR}/{MONTH}'
    url=BASE+path
    result={'symbol':pair,'period':f'{YEAR}-{MONTH:02d}','website':url,'requests':0,'status':'NO_DATA'}
    client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    def get(req):
        result['requests']+=1
        with client.open(req,timeout=TIMEOUT) as r:return r.status,limited_response(r)
    try:
        st,html=get(urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/html'}))
        result['page_http_status']=st
        f=Form();f.feed(html.decode('utf8','replace'))
        if set(f.f)!=FIELDS:raise ValueError('INVALID_OR_PROTECTED_FORM')
        if f.f['date']!=str(YEAR) or f.f['datemonth']!=f'{YEAR}{MONTH:02d}' or f.f['fxpair']!=pair or f.f['timeframe']!='T' or f.f['platform']!='ASCII':raise ValueError('WRONG_FORM')
        if not re.fullmatch(r'[A-Za-z0-9]{8,128}',f.f['tk']):raise ValueError('NO_AUTHORIZED_TOKEN')
        st,raw=get(urllib.request.Request(BASE+'/get.php',data=urllib.parse.urlencode(f.f).encode(),headers={'User-Agent':UA,'Origin':BASE,'Referer':url,'Content-Type':'application/x-www-form-urlencoded'}))
        result['zip_http_status']=st; result['zip_bytes']=len(raw)
        if not raw.startswith(b'PK\x03\x04'):raise ValueError('NOT_ZIP')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if z.testzip() is not None:raise ValueError('ZIP_CRC_ERROR')
            csv=[i for i in z.infolist() if i.filename.endswith('.csv')]
            if len(csv)!=1 or csv[0].file_size<1000 or csv[0].file_size>120*1024*1024:raise ValueError('UNEXPECTED_CSV')
            result['csv_member']=csv[0].filename;result['csv_size']=csv[0].file_size
            with z.open(csv[0]) as fh:
                digest=hashlib.sha256();num=0
                for chunk in iter(lambda:fh.read(65536),b''):
                    num+=len(chunk);digest.update(chunk)
            assert num==csv[0].file_size
            result['csv_sha256']=digest.hexdigest()
        # Encrypt on runner using only the receiver's public key. GitHub artifact holds no raw vendor quotes.
        session_key=secrets.token_bytes(32);nonce=secrets.token_bytes(12)
        aad=f'ELISA_FX_SESSION_EFFECT_001:{pair}:2026-09'.encode()
        encrypted=AESGCM(session_key).encrypt(nonce,raw,aad)
        encrypted_key=recipient.encrypt(session_key,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
        fname=f'{pair}_202609.zip.aesgcm'
        (OUT/fname).write_bytes(encrypted)
        result.update({'status':'ENCRYPTED_RAW_PRESERVED','raw_sha256':sha256(raw),'cipher_sha256':sha256(encrypted),'cipher_bytes':len(encrypted),'wrapped_key_hex':encrypted_key.hex(),'nonce_hex':nonce.hex(),'aad':aad.decode(),'cipher_file':fname,'zip_crc':'PASS'})
    except Exception as exc:
        result['status']='DOWNLOAD_OR_VALIDATION_FAILED';result['error_type']=type(exc).__name__;result['error_code']=str(exc)[:120]
    return result

def main():
    recipient=serialization.load_pem_public_key(PUBLIC_KEY.read_bytes())
    r=[capture(x,recipient) for x in SYMBOLS]
    manifest={'schema':'ELISA_FX_SESSION_RAW_ENCRYPTED_001','utc':dt.datetime.now(dt.timezone.utc).isoformat(),'research_only':True,'source_data_public_in_github':False,'private_key_in_runner':False,'pairs':r}
    (OUT/'MANIFEST.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print('ELISA_FX_SEP_CAPTURE='+json.dumps({"pairs":[{k:v for k,v in row.items() if k not in ('wrapped_key_hex','nonce_hex')} for row in r]},sort_keys=True),flush=True)
    if not all(x['status']=='ENCRYPTED_RAW_PRESERVED' for x in r):sys.exit(2)

if __name__=='__main__': main()