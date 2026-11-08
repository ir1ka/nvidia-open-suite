#!/usr/bin/python3
"""Internal read-only source-copy and patch preparation helpers for Suite."""
import hashlib,json,re,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VENDOR=json.loads((ROOT/'vendor.json').read_text())
IGNORES=shutil.ignore_patterns('.git','_out','build','__pycache__','*.o','*.ko','*.ko.*','*.o_binary','*.mod','*.mod.c','.*.cmd','Module.symvers','modules.order','*.rej','*.orig','*.key','*.pem','*.p12','*.pfx')

def run(args,**kwargs):
    return subprocess.run([str(x)for x in args],check=True,**kwargs)

def manifest(source):
    return {str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(source.rglob('*'))if p.is_file()and p.name!='full-bar1-source.json'}

def source_version(source):
    text=(source/'version.mk').read_text()
    match=re.search(r'^NVIDIA_VERSION\s*=\s*([0-9.]+)\s*$',text,re.M)
    if not match:raise ValueError('Missing NVIDIA_VERSION in full open source')
    return match.group(1)

def complete(source):
    return all((source/p).is_file()for p in ('version.mk','Makefile','kernel-open/nvidia/nv.c','src/nvidia/src/kernel/gpu/bus/kern_bus.c','src/nvidia/src/kernel/mem_mgr/io_vaspace.c'))

def prepare_local(source,destination,patch_paths=None,finalize=None,metadata_name="nvidia-suite-source.json",prepare_hook=None):
    source=source.resolve();destination=destination.resolve()
    if not complete(source):raise ValueError('Incomplete open RM source; kernel interface sources alone are insufficient')
    if source_version(source)!=VENDOR['driver_version']:raise ValueError('Unvalidated NVIDIA version: '+source_version(source))
    if any((source/name).exists()for name in ('full-bar1-source.json','nvidia-suite-source.json')):raise ValueError('Already patched source: use the Suite package builder or supply original source')
    if destination.exists()or source==destination or source in destination.parents:raise ValueError('Use a new destination outside the source tree')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.installed-bar1-',dir=destination.parent)as tmp:
        stage=Path(tmp)/'source'
        # No external links may be followed into the build/source package.
        def ignore(directory,names):
            skipped=set(IGNORES(directory,names))
            for name in set(names)-skipped:
                if (Path(directory)/name).is_symlink():raise ValueError('Source symlink requires review: '+str(Path(directory)/name))
            return skipped
        shutil.copytree(source,stage,ignore=ignore)
        baseline=manifest(stage)
        for path in stage.rglob('*'):
            if path.is_file():path.chmod(path.stat().st_mode|0o200)
        preparation=prepare_hook(stage)if prepare_hook is not None else {}
        patch=ROOT/'patches/full-bar1-p2p.patch'
        chain=list(patch_paths)if patch_paths is not None else [patch]
        for item in chain:
            run(['patch','--no-backup-if-mismatch','--dry-run','--batch','--fuzz=0','--forward','-p1','-i',item],cwd=stage)
            run(['patch','--no-backup-if-mismatch','--batch','--fuzz=0','--forward','-p1','-i',item],cwd=stage)
        for test in ('check_driver.py','check_registry.py','check_lifetime.py'):
            run([sys.executable,ROOT/'tests'/test,'--source',stage])
        extra=finalize(stage)if finalize is not None else {}
        meta=dict(VENDOR,origin='installed-source',original_source=str(source),
                  original_files=baseline,original_tree_sha256=hashlib.sha256(json.dumps(baseline,sort_keys=True).encode()).hexdigest(),
                  patch_sha256=hashlib.sha256(patch.read_bytes()).hexdigest(),prepared_files=manifest(stage))
        meta.update(preparation)
        meta.update(extra)
        if patch_paths is not None:meta['patch_chain']=[{'name':str(p), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}for p in chain]
        (stage/metadata_name).write_text(json.dumps(meta,indent=2)+'\n')
        # Detect changes to copied inputs during preparation; never edit originals.
        for name,digest in baseline.items():
            if not (source/name).is_file()or hashlib.sha256((source/name).read_bytes()).hexdigest()!=digest:
                raise ValueError('Original source changed during preparation: '+name)
        shutil.move(stage,destination)
    return destination
