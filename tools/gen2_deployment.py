"""Journal-only deployment adaptation; pinned upstream remains intact."""
from pathlib import Path
import cmp_prepare
ROOT=Path(__file__).resolve().parents[1]
def script():
 cmp_prepare.verify(ROOT)
 text=(ROOT/'vendor/cmpunlocker/tools/hammer.sh').read_text()
 # Keep upstream stdout logging and all PCI logic; remove file-only logging.
 for line in ('readonly LOG_FILE="/var/log/gen2.log"\n',
              '    echo "${line}" >> "${LOG_FILE}" 2>/dev/null || true\n',
              '    : > "${LOG_FILE}"\n'):
  assert text.count(line)==1, 'Upstream logging changed; review journal adapter'
  text=text.replace(line,'')
 return text
