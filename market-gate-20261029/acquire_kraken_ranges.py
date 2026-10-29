"""ELISA market economics gate: PUBLIC Kraken OHLCVT, exact ZIP entry HTTP range acquisition.

Public code only; no account secrets, no historical trading logic. The selection dates are
frozen separately in PREREGISTRATION_FROZEN.json before acquiring new prices.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import struct
import time
import urllib.request
import zlib
from pathlib import Path

URL = 'https://assets.kraken.com/marketing/institutions/Kraken_OHLCVT_2026Q3.zip'
PAIRS = ('XBTEUR_1.csv', 'ETHEUR_1.csv')
START = int(dt.datetime(2026,9,3,tzinfo=dt.timezone.utc).timestamp())
END = int(dt.datetime(2026,10,1,tzinfo=dt.timezone.utc).timestamp())
OUT = Path('kraken_2026q3_evidence')
OUT.mkdir(exist_ok=True)
BUDGET_BYTES, BUDGET_CALLS = 25_000_000, 20
log=[]
sha=lambda b: hashlib.sha256(b).hexdigest()
now=lambda: dt.datetime.now(dt.timezone.utc).isoformat()
archive_etag=None

def fetch(url, *, method='GET', range_header=None):
    global archive_etag
    if len(log)>=BUDGET_CALLS: raise RuntimeError('MAX_HTTP_CALLS')
    hdr={'User-Agent':'ELISA-Markets-Gate-001/1.0','Accept':'application/octet-stream'}
    if range_header:
        hdr['Range']=range_header
        if archive_etag: hdr['If-Range']=archive_etag
    req=urllib.request.Request(url,method=method,headers=hdr)
    started=now();t=time.monotonic(); body=b''
    try:
        with urllib.request.urlopen(req,timeout=35) as res:
            if method!='HEAD':
                limit=BUDGET_BYTES-sum(x.get('bytes',0) for x in log)
                body=res.read(limit+1)
                if len(body)>limit:raise RuntimeError('MAX_HTTP_BYTES')
            status=res.status
            headers={k:res.headers.get(k) for k in ['Date','Content-Type','Content-Length','Content-Range','Accept-Ranges','ETag','Last-Modified']}
        log.append({'started_utc':started,'completed_utc':now(),'elapsed_ms':round((time.monotonic()-t)*1000,1),
                    'url':url,'method':method,'range':range_header,'status':status,'headers':headers,
                    'bytes':len(body),'response_sha256':sha(body)})
        if range_header and status!=206:raise RuntimeError('EXPECTED_HTTP_206_GOT_'+str(status))
        if url==URL and headers.get('ETag'):
            if archive_etag and archive_etag!=headers['ETag']:raise RuntimeError('ETAG_CHANGED')
            archive_etag=headers['ETag']
        return body,headers
    except Exception as e:
        log.append({'started_utc':started,'completed_utc':now(),'url':url,'method':method,'range':range_header,'error':repr(e)})
        raise

def inspect_archive():
    _,hdr=fetch(URL,method='HEAD')
    length=int(hdr['Content-Length'])
    tail,_=fetch(URL,range_header='bytes=-65557')
    idx=tail.rfind(b'PK\x05\x06')
    if idx<0:raise ValueError('ZIP_EOCD_MISSING')
    eocd=struct.unpack_from('<4s4H2LH',tail,idx)
    n,cd_size,cd_offset=eocd[4],eocd[5],eocd[6]
    if cd_offset+cd_size>length:raise ValueError('ZIP_DIRECTORY_OUT_OF_BOUNDS')
    cd,_=fetch(URL,range_header=f'bytes={cd_offset}-{cd_offset+cd_size-1}')
    if len(cd)!=cd_size:raise ValueError('ZIP_DIRECTORY_TRUNCATED')
    items={};off=0
    for _ in range(n):
        if cd[off:off+4]!=b'PK\x01\x02':raise ValueError('BAD_ZIP_CENTRAL_ENTRY')
        v=struct.unpack_from('<4s6H3L5H2L',cd,off)
        crc,comp,unc,namelen,extra,comment,local=v[7],v[8],v[9],v[10],v[11],v[12],v[16]
        name=cd[off+46:off+46+namelen].decode('utf-8')
        if name in PAIRS or name=='MANIFEST.json':
            items[name]={'crc32':crc,'compressed_bytes':comp,'raw_bytes':unc,'local_offset':local,'compression_method':v[4]}
        off+=46+namelen+extra+comment
    if off!=len(cd): raise ValueError('ZIP_CENTRAL_TRAILING_BYTES')
    return {'archive_url':URL,'archive_content_length':length,'archive_etag':archive_etag,'archive_last_modified':hdr.get('Last-Modified'),
            'central_directory_entries':n,'central_directory_sha256':sha(cd),'zip_total_sha256':None,
            'zip_total_sha256_reason':'Full 576MB archive deliberately not downloaded; only checksum of exact extracted CSV entries is verifiable',
            'selected_entries_metadata':items}

def extract_entry(name,metadata):
    info=metadata['selected_entries_metadata'][name]
    offset=info['local_offset'];header,_=fetch(URL,range_header=f'bytes={offset}-{offset+255}')
    if header[:4]!=b'PK\x03\x04':raise ValueError('BAD_ZIP_LOCAL_HEADER')
    a=struct.unpack_from('<4s5H3L2H',header,0)
    if a[3]!=info['compression_method']:raise ValueError('ZIP_METHOD_MISMATCH')
    start=offset+30+a[-2]+a[-1]
    compressed,_=fetch(URL,range_header=f'bytes={start}-{start+info["compressed_bytes"]-1}')
    if len(compressed)!=info['compressed_bytes']:raise ValueError('ZIP_MEMBER_COMPRESSED_SIZE_MISMATCH')
    if a[3]==8: raw=zlib.decompress(compressed,-15)
    elif a[3]==0: raw=compressed
    else:raise ValueError('ZIP_UNSUPPORTED_METHOD')
    if len(raw)!=info['raw_bytes'] or (zlib.crc32(raw)&0xffffffff)!=info['crc32']:
        raise ValueError('ZIP_MEMBER_CRC_OR_SIZE_FAIL')
    (OUT/name).write_bytes(raw)
    if name=='MANIFEST.json':
        return {'name':name,'source_crc32':info['crc32'],'raw_bytes':len(raw),'raw_sha256':sha(raw),'archive_integrity':'SOURCE_ZIP_ENTRY_CRC_VALIDATED'}
    selected=[];timestamps=[]
    for line in raw.splitlines(keepends=True):
        if not line.strip():continue
        t=int(float(line.split(b',',1)[0]))
        if START<=t<END:
            selected.append(line);timestamps.append(t)
    sl=b''.join(selected)
    (OUT/name.replace('.csv','_SELECTED_2026_09_03_30.csv')).write_bytes(sl)
    return {'name':name,'source_crc32':info['crc32'],'archive_raw_size':len(raw),'archive_raw_sha256':sha(raw),
            'archive_member_compressed_sha256':sha(compressed),'selected_bytes':len(sl),'selected_sha256':sha(sl),
            'selected_rows':len(timestamps),'selected_min_ts':min(timestamps) if timestamps else None,
            'selected_max_ts':max(timestamps) if timestamps else None,
            'archive_integrity':'SOURCE_ZIP_ENTRY_CRC_VALIDATED_NOT_WHOLE_ARCHIVE_SHA256'}

try:
    metadata=inspect_archive()
    out={'schema':'ELISA_KRAKEN_Q3_RANGE_EXPORT_1','utc':now(),'source':metadata,'selected_period_utc':'2026-09-03T00:00Z--2026-10-01T00:00Z','pairs':{}}
    for name in PAIRS:out['pairs'][name]=extract_entry(name,metadata)
    if 'MANIFEST.json' in metadata['selected_entries_metadata']:
        out['official_zip_manifest']=extract_entry('MANIFEST.json',metadata)
    # Public current symbol metadata, not evidence of historical spread or account-specific fees.
    url='https://api.kraken.com/0/public/AssetPairs?pair=XBTEUR,ETHEUR'
    pairdata,_=fetch(url)
    (OUT/'KRAKEN_PUBLIC_ASSETPAIRS.json').write_bytes(pairdata)
    out['public_asset_pairs_sha256']=sha(pairdata)
    out['http_requests']=len(log)
    out['http_bytes_received']=sum(x.get('bytes',0) for x in log)
    out['source_authenticity']='HTTPS/CDN headers + ZIP CRC, NOT Kraken-signed archive digest'
    (OUT/'SOURCE_MANIFEST.json').write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+'\n')
    print('ELISA_KRAKEN_DOWNLOAD_RESULT='+json.dumps({'status':'PASS','manifest':out,'bytes':out['http_bytes_received']},separators=(',',':')),flush=True)
except Exception as e:
    (OUT/'FAILURE.json').write_text(json.dumps({'error':repr(e),'utc':now()},indent=2)+'\n')
    print('ELISA_KRAKEN_DOWNLOAD_ERROR='+repr(e),flush=True)
    raise
finally:
    (OUT/'HTTP_ACQUISITION_LOG.json').write_text(json.dumps(log,indent=2,ensure_ascii=False)+'\n')