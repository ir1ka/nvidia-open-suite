"""Single source of NVIDIA driver release and build metadata."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def profile(version=None, root=ROOT):
    registry = json.loads((root / 'supported-drivers.json').read_text())
    entries = registry.get('drivers', {})
    if registry.get('schema_version') != 1 or not entries:
        raise ValueError('Unsupported NVIDIA driver registry schema or empty supported list')
    if version is None:
        defaults = [v for v, p in entries.items() if p.get('default', False)]
        if len(defaults) != 1:
            raise ValueError('Exactly one supported driver must be the default')
        version = defaults[0]
    if version not in entries:
        raise ValueError('Unsupported NVIDIA open version '+str(version)+'; supported: '+', '.join(sorted(entries)))
    item = entries[version]
    if item.get('status') != 'supported' or item.get('manifest') != 'manifest.json' or not isinstance(item.get('source'),dict):
        raise ValueError('Supported-driver profile mismatch: '+version)
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)+', version):
        raise ValueError('Invalid NVIDIA version')
    vendor = dict(item['source'], driver_version=version)
    # Construct the official release URL from the version key, without a second
    # independently maintained version in an archive URL.
    vendor['url'] = 'https://codeload.github.com/NVIDIA/open-gpu-kernel-modules/tar.gz/refs/tags/'+version
    return dict(item, driver_version=version, source=vendor)
