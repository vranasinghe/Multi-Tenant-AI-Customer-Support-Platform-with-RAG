"""Audit-only subprocess evidence capture. No application mutations."""
import sys,subprocess,json,time,re,os
from pathlib import Path
sys.stdout.reconfigure(errors="replace")
root=Path(__file__).resolve().parents[3]
out=root/'docs/audit/evidence';out.mkdir(exist_ok=True)
name,command=sys.argv[1:3]
t=time.perf_counter()
try:
 p=subprocess.run(['pwsh','-NoProfile','-Command',command],cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=900)
 code=p.returncode; data=p.stdout+'\n'+p.stderr
except subprocess.TimeoutExpired as e:
 code=124;data='AUDIT COMMAND TIMEOUT'
# Redact credential-bearing URL authority and raw auth tokens from diagnostic failures.
data=re.sub(r'(postgres(?:ql)?(?:\+psycopg)?://[^:/\s]+:)[^@\s]+@',r'\1[REDACTED]@',data)
data=re.sub(r'(?i)(Bearer |__Host-session=)[A-Za-z0-9_.-]+',r'\1[REDACTED]',data)
(out/(name+'.log')).write_text(data,encoding='utf-8')
record={'id':name,'command':command,'exit_code':code,'duration_seconds':round(time.perf_counter()-t,3),'log':'evidence/'+name+'.log'}
(out/(name+'.json')).write_text(json.dumps(record,indent=2))
print(json.dumps(record))
print(data[-1600:])
sys.exit(code)
