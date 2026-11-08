"""Summarize a completed latency_breakdown run; no GPU access."""
import csv,collections,statistics,json,sys
from pathlib import Path
if len(sys.argv)!=2:raise SystemExit("usage: analyze_latency.py RESULT_DIRECTORY (containing samples.csv)")
root=Path(sys.argv[1])
if not (root/"samples.csv").read_text().rstrip().endswith("PASS cleanup without reset"):
 raise SystemExit("Incomplete or failed benchmark; refusing summary")
mhz={};rates={};data=collections.defaultdict(list);per=collections.defaultdict(list)
for row in csv.reader(open(root/'samples.csv')):
 if row[0]=='CLOCK':mhz[int(row[1]),row[2],int(row[3])]=float(row[4])
 elif row[0]=='RATE':rates[int(row[1]),row[2],int(row[3]),row[4]]=float(row[5])
 elif row[0]=='S' and int(row[1])>=2:
  r,p,g,m=int(row[1]),row[2],int(row[3]),row[4];ns=int(row[6])*1000/rates[r,p,g,m]
  data[p,m].append(ns);per[p,m,r].append(ns)
result={}
for (pair,metric),v in sorted(data.items()):
 v.sort();q=lambda f:v[int((len(v)-1)*f)]
 medians=[statistics.median(x) for (p,m,r),x in per.items() if p==pair and m==metric]
 result[pair+'/'+metric]={'n':len(v),'mean_ns':statistics.mean(v),'p50_ns':q(.5),'p95_ns':q(.95),'p99_ns':q(.99),'round_p50_min_ns':min(medians),'round_p50_max_ns':max(medians)}
 print(pair,metric,'p50/p95/p99 ns',*[round(q(x),1) for x in [.5,.95,.99]],'round-median range',round(min(medians),1),round(max(medians),1))
print('CLOCK', {p:[min(v for (r,p2,g),v in mhz.items() if p2==p and r>=2),max(v for (r,p2,g),v in mhz.items() if p2==p and r>=2)] for p in sorted({p for r,p,g in mhz})})
(root/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
