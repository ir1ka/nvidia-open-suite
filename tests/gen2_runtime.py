#!/usr/bin/python3
"""Container-only hammer logic; only PATH/sysfs paths rebound to fixtures."""
import os,subprocess,tempfile,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from gen2_deployment import script as deployment_script
assert os.geteuid()==0,'Use disposable root container without hardware access'
results=[]
for scenario in ('gen1','already-gen2','foreign-id','no-cmp'):
 with tempfile.TemporaryDirectory(prefix='suite-gen2-')as tmp:
  root=Path(tmp);bindir=root/'bin';bindir.mkdir();devices=root/'sysfs';devices.mkdir()
  gpu='0000:01:00.0';bridge='0000:00:03.1';parent=root/'topology'/bridge;device=parent/gpu;device.mkdir(parents=True)
  for path,values in [(parent,{'class':'0x060400'}),(device,{'vendor':'0x10de','device':'0x20f1'if scenario=='foreign-id'else'0x20c2'})]:
   for k,v in values.items():(path/k).write_text(v+'\n')
  for bdf,p in ((gpu,device),(bridge,parent)):(devices/bdf).symlink_to(p)
  if scenario=='already-gen2':(root/'trained').touch()
  def script(name,text):
   p=bindir/name;p.write_text('#!/bin/sh\n'+text+'\n');p.chmod(0o755)
  script('lspci','case "$*" in *10de:20c2*) '+(':'if scenario=='no-cmp'else'echo "'+gpu+' fixture"')+';; esac')
  script('setpci','''echo "$*" >> "$FIXTURE/pci-trace"
case "$*" in
 *CAP_EXP+12.w) if [ -f "$FIXTURE/trained" ]; then echo 0002; else echo 0001; fi;;
 *CAP_EXP+2c.l) echo 00000006;;
 *CAP_EXP+10.w=*) : > "$FIXTURE/trained";;
esac''')
  original=deployment_script()
  text=original.replace('PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','PATH='+str(bindir)+':/usr/bin:/bin').replace('/sys/bus/pci/devices',str(devices))
  hammer=root/'hammer.sh';hammer.write_text(text)
  (root/'existing.log').write_text('administrator log')
  p=subprocess.run(['bash',str(hammer)],capture_output=True,text=True,env=dict(os.environ,FIXTURE=str(root),CMP170HX_GEN2_MAX_ITERATIONS='2',CMP170HX_GEN2_RETRAIN_INTERVAL='0.01'))
  trace=(root/'pci-trace').read_text()if(root/'pci-trace').exists()else'';writes=[l for l in trace.splitlines()if '='in l]
  if scenario=='gen1':assert p.returncode==0 and len(writes)==3,(p.stdout,p.stderr,writes)
  elif scenario=='foreign-id':assert p.returncode==1 and not writes,(p.stdout,p.stderr,writes)
  else:assert p.returncode==0 and not writes,(p.stdout,p.stderr,writes)
  assert (root/'existing.log').read_text()=='administrator log'
  assert 'LOG_FILE'not in original and '/var/log/'not in original
  assert 'early retrain started'in p.stdout
  results.append({'case':scenario,'returncode':p.returncode,'writes':writes,'log':p.stdout})
print(json.dumps({'fixture_path_rebinding_only':True,'real_pci_access':False,'cases':results},indent=2))
