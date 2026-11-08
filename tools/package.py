#!/usr/bin/python3
"""Source-bearing five-module DKMS Debian package; no host registration."""
import json,os,re,shutil,subprocess,tempfile
from pathlib import Path
from source import ROOT,REPO,BAR1,DRIVER,RELEASE,VERSION,META,digest,tree_files,require_supported
NAME='nvidia-open-suite-dkms'
STOCK=('nvidia-kernel-dkms','nvidia-open-kernel-dkms','nvidia-kernel-open-dkms','nvidia-dkms-610','nvidia-dkms-610-open')
CONFLICTS=(*STOCK,'nvidia-bar1-p2p-dkms','nvidia-bar1-p2p-prebuilt')

def validate_provides(versions):
    for name,version in versions.items():
        if name not in STOCK or not re.fullmatch(r'[0-9][A-Za-z0-9.+:~\-]*',version):
            raise ValueError('Invalid Provides declaration: '+name+'='+version)
        if not re.fullmatch(r'(?:[0-9]+:)?'+re.escape(DRIVER)+r'(?:[-+~].*)?',version):
            raise ValueError('Provided version must match NVIDIA '+DRIVER+': '+name+'='+version)
    return dict(versions)

def provide_versions(arguments=(),installed=None):
    versions={k:v for k,v in (installed or {}).items()if k in STOCK}
    overrides={}
    for item in arguments:
        name,sep,version=item.partition('=')
        if not sep or name in overrides:raise ValueError('Use each --provide-version PACKAGE=VERSION once')
        overrides[name]=version
    versions.update(overrides)
    return validate_provides(versions)

def firmware_dependency(spec=None, versions=None):
    """Target metadata only: never query packages on the build host.

    Default Debian dependency is explicit; other distributions supply the exact
    package/version (including epochs and distribution revisions).
    """
    if spec is None:
        if versions and not set(versions)&{'nvidia-kernel-open-dkms','nvidia-open-kernel-dkms','nvidia-kernel-dkms'}:
            raise ValueError('Non-Debian target metadata requires explicit --firmware-package PACKAGE=VERSION')
        spec='firmware-nvidia-gsp='+((versions or {}).get('nvidia-kernel-open-dkms',DRIVER+'-1'))
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
    if meta['suite_version']!=RELEASE or meta['suite_manifest_sha256']!=digest(ROOT/'manifest.json'):raise ValueError('Source suite manifest mismatch')
    if tree_files(source)!=meta['prepared_files']:raise ValueError('Prepared source changed since validation')
    # Revision precedes the source hash, so source changes cannot downgrade APT.
    version='1:'+VERSION+'.pkg'+str(META['package_revision'])+'.local.'+meta['original_tree_sha256'][:12]+'-'+str(META['package_revision'])
    versions=validate_provides(provides_versions or {})
    firmware=firmware_dependency(firmware_package,versions)
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
Provides: nvidia-kernel-{DRIVER}, {', '.join(p+' (= '+versions.get(p,DRIVER)+')'for p in STOCK)}
Conflicts: {', '.join(CONFLICTS)}
Replaces: {', '.join(CONFLICTS)}
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

  * Split optional tools; use standard dh_dkms lifecycle.

 -- IriKa Qiu <qiujie.jq@gmail.com>  Tue, 03 Nov 2026 00:00:00 +0000
""")
        (debian/'rules').write_text("#!/usr/bin/make -f\n%:\n\tdh $@ --with dkms\n\noverride_dh_installsystemd:\n\tdh_installsystemd --no-start\n\noverride_dh_auto_configure:\noverride_dh_auto_build:\noverride_dh_auto_test:\noverride_dh_auto_install:\n\tcp -a payload/main/. debian/nvidia-open-suite-dkms/\n\tcp -a payload/tools/. debian/nvidia-open-suite-tools/\n")
        (debian/'rules').chmod(0o755)
        subprocess.run(['dpkg-buildpackage','-b','-us','-uc','-d'],cwd=root,check=True,
                       env=dict(os.environ,SOURCE_DATE_EPOCH='1793664000'))
        for artifact in root.parent.glob('*.deb'):shutil.copy2(artifact,output/artifact.name)
        return output/(NAME+'_'+version.split(':',1)[-1]+'_amd64.deb')
