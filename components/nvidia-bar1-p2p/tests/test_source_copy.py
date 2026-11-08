import importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
PATH=Path(__file__).resolve().parents[1]/'tools/source_copy.py'
spec=importlib.util.spec_from_file_location('source_copy',PATH);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class InstalledSourceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.work=Path(self.temp.name)
 def minimal(self,version='610.43.02'):
  source=self.work/'original';source.mkdir()
  for name in ('version.mk','Makefile','kernel-open/nvidia/nv.c','src/nvidia/src/kernel/gpu/bus/kern_bus.c','src/nvidia/src/kernel/mem_mgr/io_vaspace.c'):
   p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('NVIDIA_VERSION = '+version+'\n'if name=='version.mk'else 'original\n')
  return source
 def test_missing_version_has_actionable_error(self):
  with self.assertRaisesRegex(ValueError,'missing version.mk'):m.prepare_local(self.work,self.work/'copy')
 def test_unknown_version_rejected_without_output(self):
  source=self.minimal('610.43.03')
  with self.assertRaisesRegex(ValueError,'Unvalidated'):m.prepare_local(source,self.work/'copy')
  self.assertFalse((self.work/'copy').exists())
 def test_copy_may_not_live_under_original(self):
  source=self.minimal()
  with self.assertRaisesRegex(ValueError,'outside'):m.prepare_local(source,source/'copy')
 def test_symlink_refused(self):
  source=self.minimal();(source/'external').symlink_to('/etc/passwd')
  with self.assertRaisesRegex(ValueError,'symlink'):m.prepare_local(source,self.work/'copy')
 def test_patch_failure_never_publishes_or_modifies_original(self):
  source=self.minimal();before=m.manifest(source)
  with self.assertRaisesRegex(ValueError,'precompiled RM'),patch.object(m,'run',side_effect=lambda args,**kw:subprocess.run(list(map(str,args)),check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,**kw)):
   m.prepare_local(source,self.work/'copy')
  self.assertEqual(m.manifest(source),before);self.assertFalse((self.work/'copy').exists())
 def test_prepatched_source_is_not_double_patched(self):
  source=self.minimal();(source/'full-bar1-source.json').write_text('{}')
  with self.assertRaisesRegex(ValueError,'Already patched'):m.prepare_local(source,self.work/'copy')

 def test_offset_patch_does_not_leave_unshipped_backup_in_manifest(self):
  source=self.minimal();nv=source/'kernel-open/nvidia/nv.c';nv.write_text('prefix\noriginal\n')
  change=self.work/'change.patch';change.write_text('--- a/kernel-open/nvidia/nv.c\n+++ b/kernel-open/nvidia/nv.c\n@@ -1 +1 @@\n-original\n+changed\n')
  def run(args,**kwargs):
   if args[0]=='patch':return subprocess.run(list(map(str,args)),check=True,capture_output=True,**kwargs)
  with patch.object(m,'run',side_effect=run):result=m.prepare_local(source,self.work/'copy',patch_paths=[change])
  self.assertEqual((result/'kernel-open/nvidia/nv.c').read_text(),'prefix\nchanged\n')
  self.assertFalse(list(result.rglob('*.orig')))
  meta=json.loads((result/'nvidia-suite-source.json').read_text())
  self.assertFalse(any(name.endswith('.orig')for name in meta['prepared_files']))
  self.assertEqual(nv.read_text(),'prefix\noriginal\n')

 def test_prepare_hook_failure_never_publishes_or_modifies_original(self):
  source=self.minimal();before=m.manifest(source)
  def fail(stage):
   (stage/'Makefile').write_text('private change')
   raise RuntimeError('prepare failed')
  with self.assertRaisesRegex(RuntimeError,'prepare failed'):
   m.prepare_local(source,self.work/'copy',prepare_hook=fail)
  self.assertEqual(m.manifest(source),before)
  self.assertFalse((self.work/'copy').exists())

 def test_interface_only_tree_reaches_patch_and_fails_actionably(self):
  source=self.work/'interface';source.mkdir()
  (source/'version.mk').write_text('NVIDIA_VERSION = '+m.VENDOR['driver_version']+'\n')
  (source/'nv-kernel.o_binary').write_bytes(b'precompiled RM fixture')
  patchfile=self.work/'missing-source.patch'
  patchfile.write_text('--- a/src/missing.c\n+++ b/src/missing.c\n@@ -1 +1 @@\n-old\n+new\n')
  with self.assertRaisesRegex(ValueError,'precompiled RM'):
   m.prepare_local(source,self.work/'result',patch_paths=[patchfile])
  self.assertFalse((self.work/'result').exists())
  self.assertEqual((source/'nv-kernel.o_binary').read_bytes(),b'precompiled RM fixture')
