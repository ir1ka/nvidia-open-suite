import re,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class RuntimePackaging(unittest.TestCase):
 def test_registry_keys_are_merged_and_match_upstream_defaults(self):
  config=(ROOT/'packaging/modprobe.conf').read_text()
  self.assertEqual(config.count('NVreg_RegistryDwords='),1)
  for key in ('RMFullBar1P2P=1','RmForceEnableGen2=1','RMPcieLinkSpeed=0x1'):self.assertIn(key,config)
  original=(ROOT/'vendor/cmpunlocker/install.sh').read_text()
  self.assertIn('RmForceEnableGen2=1;RMPcieLinkSpeed=0x1',original)
 def test_dynamic_bar1_preview_requires_explicit_opt_in(self):
  self.assertNotIn("RMDynamicBar1P2P=1",(ROOT/"packaging/modprobe.conf").read_text())
 def test_service_is_enabled_without_install_time_start_and_has_no_target_cycle(self):
  unit=(ROOT/'packaging/nvidia-open-suite-gen2.service').read_text()
  self.assertIn('WantedBy=multi-user.target',unit);self.assertNotIn('WantedBy=sysinit.target',unit)
  self.assertIn('After=sysinit.target',unit)
  self.assertIn('dh_installsystemd --no-start',(ROOT/'tools/package.py').read_text())
 def test_payload_keeps_driver_and_cmp_service_without_custom_boot_environment(self):
  package=(ROOT/'tools/package.py').read_text()
  self.assertIn('gen2_script()',package)
  self.assertNotIn('initramfs-runtime',package)
  self.assertNotIn('initramfs-hook',package)
  self.assertFalse((ROOT/'packaging/initramfs-hook').exists())
  self.assertNotIn("copy(ROOT/'vendor/cmpunlocker/tools/passthrough",package)

 def test_journal_only_and_upstream_remains_unmodified(self):
  import sys
  sys.path.insert(0,str(ROOT/'tools'))
  from gen2_deployment import script
  self.assertNotIn('LOG_FILE',script())
  self.assertNotIn('/var/log/',script())
  self.assertIn('readonly LOG_FILE="/var/log/gen2.log"',(ROOT/'vendor/cmpunlocker/tools/hammer.sh').read_text())
  unit=(ROOT/'packaging/nvidia-open-suite-gen2.service').read_text()
  self.assertNotIn('LogsDirectory=',unit)
  self.assertIn('StandardOutput=journal',unit)
  self.assertIn('StandardError=journal',unit)
