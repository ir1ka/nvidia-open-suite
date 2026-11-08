#!/usr/bin/python3
"""Source-bearing five-module DKMS Debian package; no host registration."""
from email.utils import formatdate
import json,os,re,shutil,subprocess,tempfile
from pathlib import Path
from source import ROOT,BAR1,DRIVER,RELEASE,VERSION,META,digest,tree_files,require_supported,driver_registry
NAME='nvidia-open-suite-dkms'
STOCK=('nvidia-kernel-dkms','nvidia-open-kernel-dkms','nvidia-kernel-open-dkms','nvidia-dkms-'+DRIVER.split('.')[0],'nvidia-dkms-'+DRIVER.split('.')[0]+'-open')
TARGET_PROVIDER='nvidia-kernel-open-dkms'
FIRMWARE_PACKAGE='firmware-nvidia-gsp'
# All these packages install the same NVIDIA module names; they cannot coexist.
CONFLICTS=(*STOCK,'nvidia-bar1-p2p-dkms','nvidia-bar1-p2p-prebuilt')
REPLACES=(TARGET_PROVIDER,)

def provided_packages(versions):
    return (TARGET_PROVIDER,)

def validate_provides(versions):
    for name,version in versions.items():
        if name != TARGET_PROVIDER or not re.fullmatch(r'(?:[0-9]+:)?'+re.escape(DRIVER)+r'(?:[-+~][A-Za-z0-9.+:~\-]+)?',version):
            raise ValueError('Expected '+TARGET_PROVIDER+'=<full NVIDIA '+DRIVER+' package version>')
    return dict(versions)

def provide_versions(arguments=(),installed=None):
    versions={k:v for k,v in (installed or {}).items()if k==TARGET_PROVIDER}
    overrides={}
    for item in arguments:
        name,sep,version=item.partition('=')
        if not sep or name in overrides:raise ValueError('Use --provide-version PACKAGE=VERSION once')
        overrides[name]=version
    versions.update(overrides)
    return validate_provides(versions)

def installed_version(name):
    result=subprocess.run(['dpkg-query','-W','-f=${db:Status-Status}\t${Version}',name],capture_output=True,text=True)
    if result.returncode==0 and result.stdout.startswith('installed\t'):
        return result.stdout.split('\t',1)[1].strip()
    raise ValueError('Installed '+name+' metadata unavailable; specify target --provide-version and --firmware-package explicitly')

def target_metadata(arguments=(),firmware=None,detect=True):
    # Explicit target metadata takes precedence and never needs host packages.
    versions=provide_versions(arguments)
    if not versions:
        if not detect:raise ValueError('Cross-system builds require --provide-version '+TARGET_PROVIDER+'=VERSION')
        versions=validate_provides({TARGET_PROVIDER:installed_version(TARGET_PROVIDER)})
    if firmware is None:
        if not detect:raise ValueError('Cross-system builds require --firmware-package PACKAGE=VERSION')
        firmware=FIRMWARE_PACKAGE+'='+installed_version(FIRMWARE_PACKAGE)
    firmware_dependency(firmware)
    return versions,firmware

def firmware_dependency(spec=None):
    """Exact independent target firmware metadata; never infer from DKMS."""
    if spec is None:raise ValueError('Specify --firmware-package PACKAGE=VERSION')
    name,sep,version=spec.partition('=')
    if not sep or not re.fullmatch(r'[a-z0-9][a-z0-9+.-]+',name):
        raise ValueError('Use --firmware-package PACKAGE=VERSION')
    if not re.fullmatch(r'(?:[0-9]+:)?'+re.escape(DRIVER)+r'(?:[-+~][A-Za-z0-9.+:~\-]+)?',version):
        raise ValueError('Firmware package version must match NVIDIA '+DRIVER)
    return name+' (= '+version+')'

def export_toolkit(destination):
    ignored=shutil.ignore_patterns('.git','__pycache__','build','dist','diagnostics','*.pyc','release.json','history-map.json','check_release.py')
    # Keep the installed toolkit layout stable; source uses a nested component.
    def suite_ignored(path,names):
        result=ignored(path,names)
        if Path(path)==ROOT and 'components' in names:result.add('components')
        return result
    shutil.copytree(ROOT,destination/'nvidia-open-suite',ignore=suite_ignored)
    shutil.copytree(BAR1,destination/'nvidia-bar1-p2p',ignore=ignored)


def build(source,output,provides_versions=None,firmware_package=None):
    """Build both packages with debhelper; dh_dkms owns DKMS maintscripts."""
    require_supported(DRIVER)
    meta=json.loads((source/'nvidia-suite-source.json').read_text())
    require_supported(meta['detected_install']['driver_version'])
    if meta.get('driver_registry_sha256')!=digest(ROOT/'supported-drivers.json'):raise ValueError('Prepared driver registry changed; prepare source again')
    if meta['suite_version']!=RELEASE or meta['suite_manifest_sha256']!=digest(ROOT/'manifest.json'):raise ValueError('Source suite manifest mismatch')
    if tree_files(source)!=meta['prepared_files']:raise ValueError('Prepared source changed since validation')
    # Revision precedes the source hash, so source changes cannot downgrade APT.
    version='1:'+VERSION+'.pkg'+str(META['package_revision'])+'.local.'+meta['original_tree_sha256'][:12]+'-'+str(META['package_revision'])
    versions,firmware_package=target_metadata(
        [name+"="+value for name,value in (provides_versions or {}).items()],firmware_package)
    firmware=firmware_dependency(firmware_package)
    epoch=int(driver_registry.profile()['source']['source_date_epoch'])
    changelog_date=formatdate(epoch,localtime=False)
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='nvidia-suite-deb-')as tmp:
        root=Path(tmp)/'source';debian=root/'debian';debian.mkdir(parents=True)
        main=root/'payload/main';tools=root/'payload/tools'
        def copy(src,stage,name,mode=0o644):
            p=stage/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,p);p.chmod(mode)
        shutil.copytree(source,main/'usr/src'/('nvidia-open-suite-'+VERSION))
        export_toolkit(tools/'usr/share/nvidia-open-suite/toolkit')
        copy(ROOT/'bin/nvidia-open-suite',tools,'usr/sbin/nvidia-open-suite',0o755)
        for stage,name in ((main,NAME),(tools,'nvidia-open-suite-tools')):
            for f in ('README.md','README.zh-CN.md'):copy(ROOT/f,stage,'usr/share/doc/'+name+'/'+f)
            copy(ROOT/'vendor/cmpunlocker/LICENSE',stage,'usr/share/doc/'+name+'/cmpunlocker-LICENSE')
            copy(ROOT/'vendor/cmpunlocker/CREDITS.md',stage,'usr/share/doc/'+name+'/cmpunlocker-CREDITS.md')
            copy(ROOT/'LICENSE',stage,'usr/share/doc/'+name+'/suite-LICENSE')
            copy(source/'COPYING',stage,'usr/share/doc/'+name+'/copyright')
        copy(ROOT/'packaging/modprobe.conf',main,'etc/modprobe.d/nvidia-open-suite.conf')
        from gen2_deployment import script as gen2_script
        hammer=main/'usr/lib/nvidia-open-suite/gen2-hammer';hammer.parent.mkdir(parents=True,exist_ok=True);hammer.write_text(gen2_script());hammer.chmod(0o755)
        copy(ROOT/'packaging/nvidia-open-suite-gen2.service',main,'usr/lib/systemd/system/nvidia-open-suite-gen2.service')
        control=f"""Source: nvidia-open-suite
Section: kernel
Priority: optional
Maintainer: IriKa Qiu <qiujie.jq@gmail.com>
Build-Depends: debhelper-compat (= 13), dh-sequence-dkms
Standards-Version: 4.7.0
Rules-Requires-Root: no
Homepage: https://github.com/ir1ka/nvidia-open-suite
Vcs-Git: https://github.com/ir1ka/nvidia-open-suite.git
Vcs-Browser: https://github.com/ir1ka/nvidia-open-suite

Package: {NAME}
Architecture: amd64
Depends: ${{misc:Depends}}, {firmware}, g++, bash, pciutils, coreutils, gawk | mawk
Provides: {', '.join(p+' (= '+versions[p]+')'for p in provided_packages(versions))}
Conflicts: {', '.join(CONFLICTS)}
Replaces: {', '.join(REPLACES)}
Suggests: nvidia-open-suite-tools
Description: NVIDIA open {DRIVER} CMP/PCIe P2P DKMS source
 Patched source for five NVIDIA kernel modules, built by standard DKMS.
 Kernel updates rebuild from installed source when matching headers are present.
 Includes default CMP/P2P options and the CMP Gen2 boot service.
 No PF recovery, GRUB/IOMMU edits or passthrough configuration are included.

Package: nvidia-open-suite-tools
Architecture: all
Depends: ${{misc:Depends}}, python3, python3-yaml, git, kmod, make, gcc, g++, patch, dkms, debhelper, dh-sequence-dkms
Suggests: {NAME} (= {version})
Breaks: {NAME} (<< {version})
Replaces: {NAME} (<< {version})
Description: Optional preparation and test tools for NVIDIA Open Suite
 Source selection, patch preparation, Debian package building and tests.
 Can be installed on a build host without the NVIDIA driver package.
"""
        (debian/'control').write_text(control)
        from file_guard import text as ownership_guard
        for name,stage,allowed,modules in ((NAME,main,[NAME,*CONFLICTS],['nvidia*']),('nvidia-open-suite-tools',tools,['nvidia-open-suite-tools'],[])):
            preinst=debian/(name+'.preinst');preinst.write_text('#!/bin/sh\nset -e\n'+ownership_guard(stage,allowed,modules,[(NAME,'lt',version)]if name=='nvidia-open-suite-tools'else[],['nvidia','nvidia-modeset','nvidia-drm','nvidia-uvm','nvidia-peermem']if name==NAME else[])+'#DEBHELPER#\n');preinst.chmod(0o755)
        shutil.copyfile(source/'dkms.conf',debian/(NAME+'.dkms'))
        (debian/'changelog').write_text(f"""nvidia-open-suite ({version}) unstable; urgency=medium

  * Build Suite {RELEASE} for NVIDIA open {DRIVER}.

 -- IriKa Qiu <qiujie.jq@gmail.com>  {changelog_date}
""")
        (debian/'rules').write_text("#!/usr/bin/make -f\n%:\n\tdh $@ --with dkms\n\noverride_dh_installsystemd:\n\tdh_installsystemd --no-start\n\noverride_dh_auto_configure:\noverride_dh_auto_build:\noverride_dh_auto_test:\noverride_dh_auto_install:\n\tcp -a payload/main/. debian/nvidia-open-suite-dkms/\n\tcp -a payload/tools/. debian/nvidia-open-suite-tools/\n")
        (debian/'rules').chmod(0o755)
        subprocess.run(['dpkg-buildpackage','-b','-us','-uc','-d'],cwd=root,check=True,
                       env=dict(os.environ,SOURCE_DATE_EPOCH=str(epoch)))
        for artifact in root.parent.glob('*.deb'):shutil.copy2(artifact,output/artifact.name)
        return output/(NAME+'_'+version.split(':',1)[-1]+'_amd64.deb')
