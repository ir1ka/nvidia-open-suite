#!/usr/bin/python3
"""Pinned combined patch preparation; original DKMS source is read-only."""
import hashlib,importlib.util,sys,json,os,platform,re,shutil,subprocess,tarfile,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parent
BAR1=ROOT/'components/nvidia-bar1-p2p'
if not BAR1.is_dir():BAR1=REPO/'nvidia-bar1-p2p'
META=json.loads((ROOT/'manifest.json').read_text());DRIVER=META['driver_version'];RELEASE=META['suite_version'];VERSION=RELEASE+'+nvidia.'+DRIVER
spec=importlib.util.spec_from_file_location('bar1_source',BAR1/'tools/source_copy.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
REQUIRED=json.loads((ROOT/'required-source.json').read_text())
DKMS_ROOT=Path('/var/lib/dkms')
LIVE_VERSION=Path('/sys/module/nvidia/version')
SOURCE_ROOT=Path('/usr/src')

def require_supported(version):
    """Fail closed before download, preparation, or Debian packaging."""
    registry=json.loads((ROOT/'supported-drivers.json').read_text())
    entries=registry.get('drivers',{})
    if registry.get('schema_version')!=1 or version not in entries:
        raise ValueError('Unsupported NVIDIA open version '+str(version)+'; supported: '+', '.join(sorted(entries)))
    entry=entries[version]
    # Listing a version is not sufficient without its matching reviewed profile.
    if (entry.get('status')!='supported' or entry.get('manifest')!='manifest.json' or
        entry.get('source')!='components/nvidia-bar1-p2p/vendor.json' or
        version!=DRIVER or base.VENDOR['driver_version']!=version):
        raise ValueError('Supported-driver profile mismatch: '+str(version))
    return entry

def tool(name):
    for path in (shutil.which(name),'/usr/sbin/'+name,'/sbin/'+name):
        if path and os.access(path,os.X_OK):return path
    raise ValueError('Required tool missing: '+name)

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def tree_files(path):return {str(p.relative_to(path)):digest(p)for p in sorted(path.rglob('*'))if p.is_file()and p.name!='nvidia-suite-source.json'}
def complete(path):return all((path/name).is_file()for name in REQUIRED)

def dkms_records(text):
    records=[]
    for line in text.splitlines():
        m=re.fullmatch(r'([^/,]+)/([^,:]+),\s*([^,]+),\s*([^:]+):\s*(\w+)(?:\s+\(.*\))?',line.strip())
        if m:records.append(dict(module=m[1],version=m[2],kernel=m[3],arch=m[4].strip(),state=m[5]))
        else:
            m=re.fullmatch(r'([^/,]+)/([^,:]+):\s*(added|broken.*)',line.strip())
            if m:records.append(dict(module=m[1],version=m[2],kernel=None,arch=None,state=m[3]))
            elif line.strip():raise ValueError('Unrecognized DKMS state: '+line)
    return records

def detect(kernel=None):
    kernel=kernel or platform.release()
    if not re.fullmatch(r'[0-9][A-Za-z0-9.+_~-]*',kernel):raise ValueError('Invalid kernel ABI')
    def field(name):return subprocess.check_output([tool('modinfo'),'-k',kernel,'-F',name,'nvidia'],text=True).strip()
    version=field('version');license=field('license');filename=field('filename')
    require_supported(version)
    if 'GPL'not in license:raise ValueError('Original driver must be NVIDIA open, not proprietary')
    if '/updates/dkms/'not in filename:raise ValueError('Original NVIDIA module must resolve to a DKMS installation: '+filename)
    live=LIVE_VERSION
    if live.exists()and live.read_text().strip()!=version:raise ValueError('Loaded/on-disk NVIDIA versions differ; resolve before takeover')
    records=dkms_records(subprocess.check_output([tool('dkms'),'status'],text=True))
    providers=[]
    for r in records:
        if not r['module'].startswith('nvidia')or r['kernel']!=kernel or r['state']!='installed':continue
        source=DKMS_ROOT/r['module']/r['version']/'source'
        if not(source/'dkms.conf').is_file():continue
        if not re.search(r'BUILT_MODULE_NAME\[[0-9]+\]\s*=\s*[\x27\x22]?nvidia[\x27\x22]?(?:\s|$)',(source/'dkms.conf').read_text(),re.M):continue
        providers.append(dict(r,source=str(source.resolve())))
    if len(providers)!=1:raise ValueError('Expected exactly one installed NVIDIA DKMS provider for '+kernel+'; found '+str(len(providers)))
    if providers[0]['arch']!='x86_64':raise ValueError('This delivery supports x86_64 NVIDIA open only')
    return dict(driver_version=version,kernel=kernel,module_file=filename,provider=providers[0],nvidia_records=[r for r in records if r['module'].startswith('nvidia')])

def build_plan(driver_version=None,kernel=None,require_installed=False):
    """An explicit supported version permits packaging without host DKMS/GPU."""
    if driver_version is not None:require_supported(driver_version)
    if driver_version is not None and not require_installed:
        if kernel is not None:raise ValueError('--kernel inspects installed DKMS; omit it for explicit-version prepare')
        return dict(driver_version=DRIVER,mode='explicit-version',
                    provider={'source':str(SOURCE_ROOT/('nvidia-'+DRIVER))},nvidia_records=[])
    plan=detect(kernel)
    plan['mode']='installed-driver'
    return plan

def fetch_original(archive,work):
    require_supported(DRIVER)
    v=base.VENDOR
    if archive is None:
        archive=work/'nvidia-official-source.tar.gz';partial=work/'nvidia-official-source.download'
        print('Downloading SHA256-pinned NVIDIA source: '+v['url'],flush=True)
        with urllib.request.urlopen(v['url'],timeout=60)as response,partial.open('xb')as out:shutil.copyfileobj(response,out)
        if digest(partial)!=v['sha256']:raise ValueError('Official download SHA256 mismatch')
        partial.rename(archive)
    if digest(archive)!=v['sha256']:raise ValueError('Official source archive SHA256 mismatch')
    target=work/'official';target.mkdir()
    with tarfile.open(archive)as tar:tar.extractall(target,filter='data')
    return target/('open-gpu-kernel-modules-'+DRIVER)

def acquire(plan,work,source=None,archive=None):
    # Never implicitly reuse installed or retained driver trees. The pinned
    # release archive is the reproducible default, including Suite rebuilds.
    if source is None:
        return fetch_original(archive,work),'official-archive' if archive is not None else 'official-download'
    if archive is not None:
        raise ValueError('Use either --source or --archive, not both')
    original=source.resolve()
    if any((original/name).exists()for name in ('nvidia-suite-source.json','full-bar1-source.json')):
        raise ValueError('Explicit source is already patched; supply original source or use the official download')
    if not complete(original):raise ValueError('Explicit source must be a complete NVIDIA open source tree')
    if base.source_version(original)!=DRIVER:raise ValueError('Source/driver version mismatch')
    return original,'explicit-local-source'

def finalize(stage):
    if not(stage/'COPYING').exists():shutil.copyfile(ROOT/'licenses/NVIDIA-COPYING',stage/'COPYING')
    for name in ('dkms.conf','suite-build.sh','check-modules.sh'):shutil.copyfile(ROOT/'packaging'/name,stage/name)
    (stage/'suite-build.sh').chmod(0o755)
    (stage/'check-modules.sh').chmod(0o755)
    return dict(suite_version=RELEASE,suite_manifest_sha256=digest(ROOT/'manifest.json'),cmpunlocker_commit=META['commit'])

def prepare(plan,work,source=None,archive=None):
    require_supported(plan['driver_version'])
    checks={'dynamic_p2p_sha256':BAR1/'patches/dynamic-bar1-p2p.patch','nvidia_copying_sha256':ROOT/'licenses/NVIDIA-COPYING','integration_sha256':ROOT/'patches/integration.patch','p2p_sha256':BAR1/'patches/full-bar1-p2p.patch','required_source_sha256':ROOT/'required-source.json','suite_build_sha256':ROOT/'packaging/suite-build.sh','dkms_conf_sha256':ROOT/'packaging/dkms.conf','check_modules_sha256':ROOT/'packaging/check-modules.sh'}
    for key,path in checks.items():
        if digest(path)!=META[key]:raise ValueError('Suite input hash mismatch: '+key)
    original,origin=acquire(plan,work,source,archive)
    cmp_present=all((original/name).is_file()and digest(original/name)==expected for name,expected in META['cmp_expected_sha256'].items())
    if not cmp_present and '_kgspSec2PostblTimingEnabled' in (original/'src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c').read_text():
        raise ValueError('Existing CMP modifications are not the complete pinned canonical set; provide reviewed original source or an explicit official archive')
    import cmp_prepare
    cmp_prepare.verify(ROOT)
    chain=[BAR1/'patches/full-bar1-p2p.patch',ROOT/'patches/integration.patch',BAR1/'patches/dynamic-bar1-p2p.patch']
    path=base.prepare_local(original,work/'patched-source',patch_paths=chain,finalize=finalize,
        metadata_name='nvidia-suite-source.json',prepare_hook=lambda stage:cmp_prepare.prepare(stage,canonical=cmp_present,root=ROOT))
    meta=json.loads((path/'nvidia-suite-source.json').read_text())
    if base.source_version(path)!=DRIVER:raise ValueError('Copied source version changed during preparation')
    if cmp_present and any(meta['original_files'].get(name)!=expected for name,expected in META['cmp_expected_sha256'].items()):raise ValueError('CMP source changed during preparation')
    meta.update(source_origin=origin,detected_install=plan,cmp_patch_state='canonical-already-present'if cmp_present else'upstream-build-script')
    (path/'nvidia-suite-source.json').write_text(json.dumps(meta,indent=2)+'\n')
    base.run([sys.executable,ROOT/'tests/check_cmp.py','--source',path])
    return path
