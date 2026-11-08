#!/bin/bash
# Disposable container only; read-only repository/archive, no host devices/config.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
mkdir -p /work
cd /source
make check > /out/unit.log 2>&1
python3 - <<'PY'
import sys,json,subprocess,shutil,hashlib
from pathlib import Path
sys.path.insert(0,'/source/tools')
import source,cmp_prepare,package
original=source.fetch_original(Path('/archive/nvidia-610.43.02-upstream.tar.gz'),Path('/work'))
plan=source.build_plan('610.43.02')
prepared=[]
for n in range(2):
 work=Path('/work/run'+str(n));work.mkdir()
 p=source.prepare(plan,work,source=original)
 prepared.append(p)
assert source.tree_files(original)==json.load(open(prepared[0]/'nvidia-suite-source.json'))['original_files']
assert (prepared[0]/'nvidia-suite-source.json').read_bytes()==(prepared[1]/'nvidia-suite-source.json').read_bytes()
assert source.tree_files(prepared[0])==source.tree_files(prepared[1])
for n,p in enumerate(prepared):
 package.build(p,Path('/out/packages')if n==0 else Path('/work/repeat'),{'nvidia-kernel-open-dkms':'610.43.02-1'})
for f in Path('/out/packages').glob('*.deb'):assert f.read_bytes()==(Path('/work/repeat')/f.name).read_bytes()
for folder,f in [('/work/old',next(Path('/old').glob('*dkms*.deb'))),('/work/current',next(Path('/out/packages').glob('*dkms*.deb'))),('/work/tools',next(Path('/out/packages').glob('*tools*.deb')))]:
 subprocess.run(['dpkg-deb','-x',str(f),folder],check=True)
a=next(Path('/work/old/usr/src').iterdir());b=next(Path('/work/current/usr/src').iterdir())
assert source.tree_files(a)==source.tree_files(b)
assert source.tree_files(b)==json.load(open(b/'nvidia-suite-source.json'))['prepared_files']
meta=json.load(open(prepared[0]/'nvidia-suite-source.json'))
assert meta['cmp_upstream']['direct_script']=='driver/build.sh'
assert '${CMP_WORK}'in meta['cmp_upstream']['stdout']
assert 'with fuzz 1'in meta['cmp_upstream']['stdout']
Path('/out/upstream-execution.json').write_text(json.dumps(meta['cmp_upstream'],indent=2)+'\n')
# Verify cache reuse invokes the same script without applying CMP twice.
canonical=Path('/work/canonical');shutil.copytree(original,canonical)
cmp_prepare.prepare(canonical)
before=source.tree_files(canonical)
r=cmp_prepare.prepare(canonical,canonical=True)
assert before==source.tree_files(canonical)
assert r['cmp_upstream']['canonical_cache_reuse']
subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','/work/tools/usr/share/nvidia-open-suite/toolkit/nvidia-open-suite/tests','-p','test_*.py'],check=True)
Path('/out/result.json').write_text(json.dumps({'upstream_script_executed':True,'original_source_unchanged':True,'independent_preparations_equal':True,'fresh_preparation_debs_reproducible':True,'packaged_source_manifest_matches':True,'driver_and_build_files_equal_previous':True,'files':len(source.tree_files(b)),'canonical_cache_reuse_verified':True},indent=2)+'\n')
PY
