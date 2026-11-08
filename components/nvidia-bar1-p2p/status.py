"""Read-only NVIDIA module diagnostics; configuration uses native parameters."""
import subprocess
from pathlib import Path

def status():
    report={'note':'Read-only module information; disk markers do not prove live P2P operation.'}
    for name in ('RegistryDwords','RegistryDwordsPerDevice'):
        path=Path('/sys/module/nvidia/parameters')/name
        report['loaded_'+name]=path.read_text().strip()if path.exists()else None
    module=Path('/sys/module/nvidia')
    report['loaded_driver_version']=(module/'version').read_text().strip()if (module/'version').exists()else None
    report['loaded_srcversion']=(module/'srcversion').read_text().strip()if (module/'srcversion').exists()else None
    for field in ('version','srcversion','full_bar1_p2p'):
        r=subprocess.run(['modinfo','-F',field,'nvidia'],capture_output=True,text=True)
        report['on_disk_'+field]=r.stdout.strip()if r.returncode==0 else None
    report['loaded_matches_on_disk']=bool(report['loaded_srcversion']and report['loaded_srcversion']==report['on_disk_srcversion'])
    return report
