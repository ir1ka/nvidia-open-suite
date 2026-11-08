"""Summarize eight retained runs per pair/mode from the documented sample experiment."""
import pathlib,re,collections,statistics,json,sys
if len(sys.argv)!=2:raise SystemExit("usage: summarize_cuda_samples.py LOG_DIRECTORY")
root=pathlib.Path(sys.argv[1]);data=collections.defaultdict(list)
for p in root.glob('*-*-*.log'):
 m=re.fullmatch(r'(A100|2080Ti)-(write|read)-(\d+)\.log',p.name)
 if not m or int(m[3])<2:continue
 lines=p.read_text().splitlines()
 if not any('NOTE: The CUDA Samples' in l for l in lines):raise RuntimeError(p)
 for i,l in enumerate(lines):
  if 'P2P=Enabled' not in l:continue
  if m[2]=='read' and 'P2P Writes' in l:continue
  kind='latency'if 'Latency'in l else 'bidir'if 'Bidirectional'in l else 'unidir'
  rows=[x.split() for x in lines[i+1:i+5]if re.match(r'^\s+[01]\s+\d',x)]
  if len(rows)!=2:raise RuntimeError((p,l,rows))
  for direction,value in [('cell_0_1',float(rows[0][2])),('cell_1_0',float(rows[1][1]))]:data[m[1],m[2],kind,direction].append(value)
expected={(p,m,k,d) for p in ('A100','2080Ti') for m in ('write','read') for k in ('unidir','bidir','latency') for d in ('cell_0_1','cell_1_0')}
if set(data)!=expected:raise SystemExit('Missing pair/mode/matrix results')
result={}
for key,v in sorted(data.items()):
 if len(v)!=8:raise RuntimeError((key,len(v)))
 result['/'.join(key)]={'n':len(v),'median':statistics.median(v),'min':min(v),'max':max(v)}
 print('/'.join(key),result['/'.join(key)])
(root/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
