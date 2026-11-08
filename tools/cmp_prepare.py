#!/usr/bin/python3
"""Run the pinned upstream build.sh directly, through its prepare-only adapter."""
import hashlib,json,os,re,shutil,subprocess,tarfile,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def verify(root=ROOT):
    meta=json.loads((root/'manifest.json').read_text());upstream=root/'vendor/cmpunlocker'
    if not (upstream/'driver/build.sh').is_file():
        raise ValueError('Missing cmpunlocker submodule; run git submodule update --init --recursive')
    actual={str(p.relative_to(upstream)):digest(p)for p in upstream.rglob('*')if p.is_file()and not {'.git','__pycache__'}.intersection(p.relative_to(upstream).parts)}
    if actual!=meta['upstream_files']:raise ValueError('Pinned cmpunlocker scripts/configuration/patch inventory changed')
    order=re.search(r'PATCH_ORDER=\(\n(.*?)\n\)',(upstream/'driver/build.sh').read_text(),re.S)
    if not order or order.group(1).split()!=meta['patch_order']:raise ValueError('Upstream patch order differs from manifest')
    if meta['driver_version']not in (upstream/'driver/VERSION').read_text().splitlines():raise ValueError('Driver version absent from upstream support list')
    if digest(root/'patches/cmpunlocker-prepare-only.patch')!=meta['cmp_prepare_only_sha256']:raise ValueError('CMP prepare-only adapter hash mismatch')
    return meta,upstream

def adapt_recipe(destination,root=ROOT):
    meta,upstream=verify(root)
    shutil.copytree(upstream,destination,ignore=shutil.ignore_patterns('.git','__pycache__','*.pyc'))
    subprocess.run(['patch','--batch','--fuzz=0','--forward','-p1','-i',str((root/'patches/cmpunlocker-prepare-only.patch').resolve())],cwd=destination,check=True,capture_output=True,text=True)
    return destination/'driver/build.sh'

def prepare(stage,canonical=False,profile='mixed',root=ROOT):
    meta,upstream=verify(root)
    if profile not in ('mixed','8gb','10gb'):raise ValueError('Unknown CMP profile')
    # Every path the original script may extract/remove is private to this call.
    with tempfile.TemporaryDirectory(prefix='.cmp-upstream-',dir=stage.parent)as tmp:
        work=Path(tmp);recipe=work/'recipe';script=adapt_recipe(recipe,root);script_hash=digest(script)
        build=work/'build';build.mkdir();name='open-gpu-kernel-modules-'+meta['driver_version'];output=build/name
        # Supply the caller's validated source, never download or touch /usr/src.
        archive=build/(name+'.tar.gz')
        with tarfile.open(archive,'w:gz',compresslevel=1)as tar:tar.add(stage,arcname=name)
        if canonical:
            shutil.copytree(stage,output)
            patch_hash=hashlib.sha256(b''.join((recipe/'driver/patches'/n).read_bytes()for n in meta['patch_order'])).hexdigest()
            (output/'.cmpunlocker-stamp').write_text(':'.join([meta['driver_version'],'source-preparation',profile,patch_hash,script_hash])+'\n')
        env=dict(os.environ,CMPUNLOCKER_PREPARE_ONLY='1',CMPUNLOCKER_DRIVER_VERSION=meta['driver_version'],CMPUNLOCKER_CARD_PROFILE=profile,CMPUNLOCKER_BUILD_DIR=str(build))
        for key in ('BASH_ENV','ENV'):env.pop(key,None)
        env['LC_ALL']='C'
        env['PATH']=str(Path(sys.executable).parent)+os.pathsep+env.get('PATH','')
        result=subprocess.run(['bash',str(script)],cwd=work,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True)
        print(result.stdout,end='',flush=True)
        if result.returncode:
            raise RuntimeError('Upstream CMP source preparation failed:\n'+result.stdout+result.stderr)
        if 'Source preparation complete; compilation and installation delegated to DKMS'not in result.stdout:raise RuntimeError('Upstream did not reach the source-only completion boundary')
        for name,expected in meta['cmp_expected_sha256'].items():
            if digest(output/name)!=expected:raise ValueError('Upstream CMP result differs from adapted canonical source: '+name)
        # GNU patch backups and its build cache stamp are not driver sources.
        for p in output.rglob('*'):
            if p.is_file()and(p.suffix in ('.orig','.rej')or p.name=='.cmpunlocker-stamp'):p.unlink()
        for p in list(stage.iterdir()):
            if p.is_dir():shutil.rmtree(p)
            else:p.unlink()
        shutil.copytree(output,stage,dirs_exist_ok=True)
        return {'cmp_upstream':{'commit':meta['commit'],'direct_script':'driver/build.sh','original_script_sha256':meta['upstream_files']['driver/build.sh'],'executed_private_script_sha256':script_hash,'prepare_only_adapter_sha256':meta['cmp_prepare_only_sha256'],'constants_sha256':meta['upstream_files']['common/constants.yaml'],'profile':profile,'canonical_cache_reuse':canonical,'patch_order':meta['patch_order'],'stdout':result.stdout.replace(str(work),'${CMP_WORK}'),'stderr':result.stderr.replace(str(work),'${CMP_WORK}')}}
