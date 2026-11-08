"""Source nesting must preserve the installed toolkit's importable layout."""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import package
import source

class ToolkitLayout(unittest.TestCase):
 def test_nested_component_is_the_active_patch_source(self):
  expected=ROOT/'components/nvidia-bar1-p2p'
  if not expected.is_dir():expected=ROOT.parent/'nvidia-bar1-p2p'
  self.assertEqual(source.BAR1,expected)
  self.assertEqual(source.digest(source.BAR1/'patches/full-bar1-p2p.patch'),source.META['p2p_sha256'])
  self.assertEqual(source.digest(source.BAR1/'patches/dynamic-bar1-p2p.patch'),source.META['dynamic_p2p_sha256'])
 def test_exported_toolkit_imports_and_cli_without_source_siblings(self):
  with tempfile.TemporaryDirectory() as tmp:
   destination=Path(tmp)/'toolkit'
   package.export_toolkit(destination)
   self.assertTrue((destination/'nvidia-bar1-p2p/patches/full-bar1-p2p.patch').is_file())
   self.assertTrue((destination/'nvidia-bar1-p2p/patches/dynamic-bar1-p2p.patch').is_file())
   self.assertTrue((destination/'nvidia-bar1-p2p/tests/dynamic_uvm_fixture.c').is_file())
   self.assertFalse((destination/'nvidia-open-suite/components').exists())
   self.assertFalse((destination/'nvidia-open-suite/tests/hardware').exists())
   self.assertFalse((destination/'nvidia-open-suite/.git').exists())
   self.assertFalse((destination/'nvidia-open-suite/release.json').exists())
   self.assertFalse((destination/'nvidia-open-suite/tools/check_release.py').exists())
   self.assertFalse((destination/'nvidia-open-suite/diagnostics').exists())
   self.assertTrue((destination/'nvidia-bar1-p2p/status.py').is_file())
   self.assertTrue((destination/'nvidia-bar1-p2p/tools/source_copy.py').is_file())
   self.assertFalse((destination/'nvidia-bar1-p2p/packaging').exists())
   self.assertFalse((destination/'nvidia-bar1-p2p/tools/build_deb.py').exists())
   helper=destination/'nvidia-open-suite/tools/source.py'
   code="import importlib.util;from pathlib import Path;p=Path(__import__('sys').argv[1]);s=importlib.util.spec_from_file_location('exported',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);assert m.BAR1==p.parents[2]/'nvidia-bar1-p2p';assert m.digest(m.BAR1/'patches/full-bar1-p2p.patch')==m.META['p2p_sha256']"
   subprocess.run([sys.executable,'-c',code,str(helper)],check=True,capture_output=True,text=True)
   subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(destination/'nvidia-open-suite/tests'),'-p','test_layout.py'],check=True,capture_output=True,text=True,env=dict(__import__('os').environ,SUITE_EXPORTED_TEST='1')) if not __import__('os').environ.get('SUITE_EXPORTED_TEST') else None
   subprocess.run([sys.executable,str(destination/'nvidia-open-suite/bin/nvidia-open-suite'),'--help'],check=True,capture_output=True,text=True)
