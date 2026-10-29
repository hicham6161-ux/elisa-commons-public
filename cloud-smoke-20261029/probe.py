"""Public synthetic-only CPU LLM inference verification. No ELISA project data."""
import json,hashlib,time,datetime,sys,platform
from pathlib import Path

MODEL="Qwen/Qwen2.5-0.5B-Instruct"
OUT=Path("cloud_smoke_artifacts");OUT.mkdir(exist_ok=True)
CODES={"NO_CLEAR_EDGE","COST_MARGIN_POOR","TREND_5M_SUPPORTIVE","MOMENTUM_1M","ABSTAIN_UNCERTAIN"}
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def canonical(o):return json.dumps(o,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def verify(d):
    if type(d) is not dict or set(d)!={"decision","holding_minutes","confidence","reason_codes","rationale"}:raise ValueError("keys")
    if d["decision"] not in ("WAIT","NO_ENTER","ENTER"):raise ValueError("decision")
    if d["holding_minutes"] not in ((5,10) if d["decision"]=="ENTER" else (None,)):raise ValueError("horizon")
    if type(d["confidence"]) not in (float,int) or not 0<=d["confidence"]<=1:raise ValueError("confidence")
    codes=d["reason_codes"]
    if type(codes) is not list or not 1<=len(codes)<=4 or any(v not in CODES for v in codes):raise ValueError("reason")
    if type(d["rationale"]) is not str or not 1<=len(d["rationale"])<=220:raise ValueError("rationale")
def validate_input(v):
    if type(v) is not dict or set(v)!={"case","one_minute_bps","five_minute_bps","roundtrip_cost_bps"}:raise ValueError("fields")
    if any(type(v[k]) not in (float,int) for k in ("one_minute_bps","five_minute_bps","roundtrip_cost_bps")):raise ValueError("invalid numbers")
def main():
    import torch,transformers
    from transformers import AutoTokenizer,AutoModelForCausalLM
    from lmformatenforcer import JsonSchemaParser
    from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
    torch.set_num_threads(2)
    tokenizer=AutoTokenizer.from_pretrained(MODEL,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(MODEL,torch_dtype=torch.float32,trust_remote_code=False).to("cpu").eval()
    revision=getattr(model.config,"_commit_hash",None)
    # Restrict only JSON syntax and frozen output enums; never prefill trading decisions.
    format_schema={"type":"object","properties":{
      "decision":{"type":"string","enum":["WAIT","NO_ENTER","ENTER"]},
      "holding_minutes":{"type":["integer","null"],"enum":[None,5,10]},
      "confidence":{"type":"number","minimum":0,"maximum":1},
      "reason_codes":{"type":"array","items":{"type":"string","enum":sorted(CODES)},"minItems":1,"maxItems":4},
      "rationale":{"type":"string","minLength":1,"maxLength":170}},
      "required":["decision","holding_minutes","confidence","reason_codes","rationale"],"additionalProperties":False}
    prefix_fn=build_transformers_prefix_allowed_tokens_fn(tokenizer,JsonSchemaParser(format_schema))
    instruction = '''This is a SYNTHETIC software verification of JSON response format, not investment advice.
Reply with ONE valid JSON object only, no Markdown or additional text.
Use EXACT keys: decision, holding_minutes, confidence, reason_codes, rationale.
Allowed decision: WAIT, NO_ENTER, ENTER. For WAIT or NO_ENTER, holding_minutes MUST be JSON null;
for ENTER it MUST be 5 or 10. confidence is numeric 0..1.
reason_codes is an ARRAY of STRING values: NO_CLEAR_EDGE, COST_MARGIN_POOR,
TREND_5M_SUPPORTIVE, MOMENTUM_1M, ABSTAIN_UNCERTAIN. rationale is a short STRING.
Use double quotes for every JSON string, and null without quotes. Never output Python objects.
Here is one VALID JSON example of formatting only, NOT a recommended decision:
{"decision":"WAIT","holding_minutes":null,"confidence":0.5,"reason_codes":["NO_CLEAR_EDGE"],"rationale":"No clear evidence after costs."}
Choose the decision from the current synthetic input. Never invent future prices.'''
    controls=[{"case":"SYNTHETIC_FLAT","one_minute_bps":0,"five_minute_bps":0,"roundtrip_cost_bps":166},
              {"case":"SYNTHETIC_TREND","one_minute_bps":55,"five_minute_bps":130,"roundtrip_cost_bps":166}]
    try:validate_input({"case":"INVALID","one_minute_bps":"future","five_minute_bps":0,"roundtrip_cost_bps":166});negative=False
    except ValueError:negative=True
    results=[]
    for item in controls:
        validate_input(item)
        request={"model":MODEL,"messages":[{"role":"system","content":instruction},{"role":"user","content":json.dumps(item,sort_keys=True)}],
                 "generation":{"do_sample":False,"max_new_tokens":180}}
        rb=canonical(request);folder=OUT/item["case"];folder.mkdir()
        (folder/"request.json").write_bytes(rb)
        tokens=tokenizer.apply_chat_template(request["messages"],tokenize=True,add_generation_prompt=True,return_tensors="pt")
        started=utc();start=time.monotonic()
        with torch.no_grad():generated=model.generate(tokens,max_new_tokens=230,do_sample=False,pad_token_id=tokenizer.eos_token_id,prefix_allowed_tokens_fn=prefix_fn)
        latency=round((time.monotonic()-start)*1000,3)
        txt=tokenizer.decode(generated[0][tokens.shape[-1]:],skip_special_tokens=True).strip()
        raw=txt.encode();(folder/"response_original.txt").write_bytes(raw)
        try:dec=json.loads(txt);verify(dec);valid=True;err=None
        except Exception as e:valid=False;dec=None;err=f"{type(e).__name__}: {str(e)}"
        trace={"case":item["case"],"backend":"LOCAL_CPU_TRANSFORMERS","model":MODEL,"model_revision_reported":revision,
               "model_identity_cryptographically_verified":False,"real_model_generate_called":True,"constrained_json_decoding":True,"request_sha256":sha(rb),
               "response_sha256":sha(raw),"started_at_utc":started,"latency_ms":latency,"input_tokens":int(tokens.shape[-1]),
               "output_tokens":int(generated.shape[-1]-tokens.shape[-1]),"decision":dec,"valid":valid,"error":err,
               "cost_usd":None,"is_economic_pilot":False}
        (folder/"trace.json").write_bytes(canonical(trace))
        results.append({"case":item["case"],"valid":valid,"error":err,"response_sha256":sha(raw)})
    manifest={"model":MODEL,"model_revision_reported":revision,"backend":"GitHub-hosted Ubuntu CPU",
              "python":sys.version,"torch":torch.__version__,"transformers":transformers.__version__,"utc":utc(),
              "invalid_input_rejected_before_inference":negative,"runs":results,
              "no_ELISA_proprietary_code_or_data":True,"original_ELISA_adapter_not_executed":True,
              "success":negative and len(results)==2 and all(r["valid"] for r in results)}
    (OUT/"manifest.json").write_bytes(canonical(manifest))
    print("PROBE_SUMMARY="+json.dumps(manifest,sort_keys=True),flush=True)
    sys.exit(0 if manifest["success"] else 2)
if __name__=="__main__":main()
