#!/usr/bin/env python3
"""Read-only delivery checks for the split debhelper packages."""
import io,subprocess,sys,tarfile
from pathlib import Path

def archive(path,flag):
    return tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['dpkg-deb',flag,str(path)])))

main,tools=map(Path,sys.argv[1:])
with archive(main,'--ctrl-tarfile')as t:
    post=t.extractfile('./postinst').read().decode();pre=t.extractfile('./prerm').read().decode()
    assert 'Automatically added by dh_dkms/'in post and 'common.postinst'in post
    assert 'Automatically added by dh_dkms/'in pre and 'dkms remove'in pre
    assert 'nvidia-open-suite-gen2.service'in post
    assert 'deb-systemd-invoke start'not in post
    preinst=t.extractfile('./preinst').read().decode();assert 'project payload ownership guard'in preinst
    assert '--force'not in post and 'nvidia-open-suite refresh'not in post
    assert '/etc/modprobe.d/nvidia-open-suite.conf'in t.extractfile('./conffiles').read().decode()
with archive(main,'--fsys-tarfile')as t:
    files=[m.name for m in t if m.isfile()]
    assert all(p.startswith(('./usr/src/','./usr/share/doc/','./etc/modprobe.d/','./usr/lib/nvidia-open-suite/','./usr/lib/systemd/system/'))for p in files)
    assert not any('/toolkit/'in p for p in files)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
    from gen2_deployment import script
    assert t.extractfile('./usr/lib/nvidia-open-suite/gen2-hammer').read()==script().encode()
    assert not any('/initramfs-tools/'in p or '/initramfs-runtime'in p for p in files)
from source import VERSION
assert subprocess.check_output(['dpkg-deb','-f',str(main),'Version'],text=True).strip().startswith('1:'+VERSION+'.')
control=subprocess.check_output(['dpkg-deb','-f',str(main)],text=True)
assert 'dkms (>='in control and 'firmware-nvidia-gsp (= 610.43.02-1)'in control
assert '\nProvides: nvidia-kernel-open-dkms (= 610.43.02-1)\n'in control
assert '\nReplaces: nvidia-kernel-open-dkms\n'in control
deps=next(l for l in control.splitlines()if l.startswith('Depends:'))
assert 'liblzma5'not in deps and 'libzstd1'not in deps and 'findutils'not in deps
with archive(tools,'--fsys-tarfile')as t:
    names=t.getnames()
    assert './usr/sbin/nvidia-open-suite'in names
    assert './usr/share/nvidia-open-suite/toolkit/nvidia-open-suite/supported-drivers.json'in names
    assert any('/tests/check_cmp.py'in p for p in names)
    assert not any(p.startswith('./usr/src/')or '/initramfs-tools/hooks/'in p for p in names)
with archive(tools,'--ctrl-tarfile')as t:
    assert './postinst'not in t.getnames() and './prerm'not in t.getnames()
control=subprocess.check_output(['dpkg-deb','-f',str(tools)],text=True)
deps=next(x for x in control.splitlines()if x.startswith('Depends:'))
assert 'firmware-nvidia-gsp'not in deps and 'nvidia-open-suite-dkms'not in deps
assert 'Suggests: nvidia-open-suite-dkms'in control
print('PASS: split payloads, generated dh_dkms scripts/dependency, conffile and optional tools relationship')
