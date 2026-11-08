#!/usr/bin/python3
"""Explicit DKMS-provider takeover. Never stop services or reload modules."""
import fcntl,json,os,subprocess
from pathlib import Path
from source import DRIVER,dkms_records
INSTALL_LOCK=Path('/run/lock/nvidia-open-suite-install.lock')
MODULES_ROOT=Path('/lib/modules')
from package import CONFLICTS

def run(args,**kw):return subprocess.run(list(map(str,args)),check=True,**kw)
def packages():
    found={}
    for name in CONFLICTS:
        result=subprocess.run(['dpkg-query','-W','-f=${db:Status-Status}\t${Version}',name],capture_output=True,text=True)
        if result.returncode==0 and result.stdout.startswith('installed\t'):found[name]=result.stdout.split('\t')[1].strip()
    return found

def provider_keys(records):return {(r['module'],r['version'])for r in records}

def install(deb,plan,work):
    if os.geteuid()!=0:raise ValueError('install requires root; prepare is non-system-mutating')
    with INSTALL_LOCK.open('a')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        original=plan['provider'];key=(original['module'],original['version'])
        before=dkms_records(subprocess.check_output(['dkms','status'],text=True))
        expected={(r['module'],r['version'],r['kernel'],r['arch'],r['state'])for r in plan['nvidia_records']}
        current={(r['module'],r['version'],r['kernel'],r['arch'],r['state'])for r in before if r['module'].startswith('nvidia')}
        if current!=expected:raise ValueError('NVIDIA DKMS state changed since preparation; refusing takeover')
        keys=provider_keys(plan['nvidia_records'])
        if keys and keys!={key}:raise ValueError('Multiple original NVIDIA providers/versions require manual review: '+repr(keys))
        if not any(p.is_file()for p in MODULES_ROOT.glob('*/build/Makefile')):raise ValueError('No prepared target kernel headers')
        simulation=subprocess.check_output(['apt-get','-s','install',str(deb)],text=True)
        print(simulation,flush=True)
        for line in simulation.splitlines():
            if line.startswith('Remv ')and line.split()[1].split(':')[0]not in CONFLICTS:
                raise ValueError('Unexpected package removal; refusing takeover: '+line)
        installed_packages=packages()
        owned=subprocess.run(['dpkg-query','-S',str(Path(original['source'])/'dkms.conf')],capture_output=True,text=True)
        owners={name.strip().split(':')[0]for name in owned.stdout.split(': ',1)[0].split(',')}if owned.returncode==0 else set()
        source_package='nvidia-kernel-source-'+DRIVER.split('.')[0]
        source_only={source_package,source_package+'-open'}
        unknown=owners-set(CONFLICTS)-source_only-{'nvidia-open-suite-dkms'}
        if unknown:raise ValueError('Unadapted original source package owner; review takeover before proceeding: '+', '.join(sorted(unknown)))

        managed=bool(owners)and(bool(installed_packages)or 'nvidia-open-suite-dkms'in owners)
        if not managed:
            raise ValueError('Unmanaged NVIDIA DKMS provider; preserve it and migrate using the package manager before retrying')
        # Only APT/dpkg and their standard DKMS maintscripts may replace the
        # installed provider. Never remove registrations or rename source trees.
        (work/'install-plan.json').write_text(json.dumps({'plan':plan,'packages':installed_packages,'records':before},indent=2)+'\n')
        try:
            run(['apt-get','install','--reinstall','--yes',*(['--no-remove']if not any(line.startswith('Remv ')for line in simulation.splitlines())else[]),str(deb)])
        except (OSError,subprocess.CalledProcessError)as error:
            raise RuntimeError('APT installation failed; no manual source or DKMS rollback was performed. Review and repair the APT/dpkg transaction.')from error
    print('Suite installed through APT/DKMS. Active NVIDIA modules/services unchanged; no enable step is needed.')
