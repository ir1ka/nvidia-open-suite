import importlib.machinery,importlib.util,json,shlex,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import source,package

def load(name,path):
 loader=importlib.machinery.SourceFileLoader(name,str(path));spec=importlib.util.spec_from_loader(name,loader);m=importlib.util.module_from_spec(spec);loader.exec_module(m);return m

class Detection(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.a=patch.object(source,'DKMS_ROOT',self.root);self.a.start();self.addCleanup(self.a.stop)
  live=self.root/'live';live.write_text('610.43.02');self.b=patch.object(source,'LIVE_VERSION',live);self.b.start();self.addCleanup(self.b.stop)
  self.fields={'version':'610.43.02','license':'Dual MIT/GPL','filename':'/lib/modules/7.0.test/updates/dkms/nvidia.ko.zst'}
  self.status='nvidia/610.43.02, 7.0.test, x86_64: installed\n'
  self.provider('nvidia','610.43.02')
 def provider(self,name,version):
  p=self.root/name/version/'source';p.mkdir(parents=True);(p/'dkms.conf').write_text('BUILT_MODULE_NAME[0]="nvidia"\n')
 def output(self,args,**kw):
  return self.fields[args[args.index('-F')+1]]if '-F'in args else self.status
 def detect(self):
  with patch.object(source.subprocess,'check_output',side_effect=self.output):return source.detect('7.0.test')
 def test_accepts_exact_open_dkms(self):self.assertEqual(self.detect()['provider']['module'],'nvidia')
 def test_proprietary_refused(self):
  self.fields['license']='NVIDIA'
  with self.assertRaisesRegex(ValueError,'open'):self.detect()
 def test_unknown_driver_refused(self):
  self.fields['version']='610.43.03'
  with self.assertRaisesRegex(ValueError,'610.43.02'):self.detect()
 def test_manual_module_not_dkms_refused(self):
  self.fields['filename']='/lib/modules/7.0.test/kernel/drivers/nvidia.ko'
  with self.assertRaisesRegex(ValueError,'DKMS'):self.detect()
 def test_missing_registration_refused(self):
  self.status=''
  with self.assertRaisesRegex(ValueError,'exactly one'):self.detect()
 def test_unrelated_dkms_notes_allowed(self):
  self.status+='i915-sriov-dkms/2026, 7.0.test, x86_64: installed (Original modules exist)\n'
  self.assertEqual(self.detect()['provider']['module'],'nvidia')
 def test_wrong_kernel_registration_refused(self):
  self.status=self.status.replace('7.0.test','6.8.other')
  with self.assertRaisesRegex(ValueError,'exactly one'):self.detect()
 def test_multiple_providers_refused(self):
  self.provider('nvidia-alternate','610.43.02');self.status+='nvidia-alternate/610.43.02, 7.0.test, x86_64: installed\n'
  with self.assertRaisesRegex(ValueError,'exactly one'):self.detect()
 def test_loaded_disk_mismatch_refused(self):
  source.LIVE_VERSION.write_text('600.0')
  with self.assertRaisesRegex(ValueError,'differ'):self.detect()
 def test_binary_only_is_not_complete(self):
  p=self.root/'binary';p.mkdir();(p/'nv-kernel.o_binary').write_bytes(b'ELF')
  self.assertFalse(source.complete(p))
 def test_bad_archive_rejected_without_extract(self):
  archive=self.root/'bad.tar.gz';archive.write_bytes(b'bad')
  with self.assertRaisesRegex(ValueError,'SHA256'):source.fetch_original(archive,self.root)
  self.assertFalse((self.root/'official').exists())
 def test_pinned_patch_integrity(self):
  for name in source.META['patch_order']:self.assertEqual(source.digest(ROOT/'vendor/cmpunlocker/driver/patches'/name),source.META['patches'][name]['sha256'])
  self.assertEqual(len(source.META['patch_order']),14)
  self.assertEqual(source.digest(ROOT/'patches/integration.patch'),source.META['integration_sha256'])

class SourceDiscovery(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.usr=self.root/'usr';self.usr.mkdir();self.partial=self.usr/'nvidia-610.43.02';self.partial.mkdir()
  self.work=self.root/'work';self.work.mkdir();self.plan={'provider':{'source':str(self.partial)}}
  for name,value in [('SOURCE_ROOT',self.usr),('REQUIRED',['version.mk','full.c'])]:
   p=patch.object(source,name,value);p.start();self.addCleanup(p.stop)
 def full(self,name):
  p=self.usr/name;p.mkdir();(p/'version.mk').write_text('NVIDIA_VERSION = 610.43.02\n');(p/'full.c').write_text('complete');return p
 def test_unique_usr_src_full_tree_preferred_to_binary_registration(self):
  expected=self.full('nvidia-full-610.43.02')
  with patch.object(source,'fetch_original')as fetch:
   result,origin=source.acquire(self.plan,self.work)
  self.assertEqual(result,expected);self.assertEqual(origin,'installed-full-source');fetch.assert_not_called()
 def test_ambiguous_full_trees_refused(self):
  self.full('nvidia-a');self.full('nvidia-b')
  with self.assertRaisesRegex(ValueError,'Multiple complete'):source.acquire(self.plan,self.work)
 def test_interface_only_falls_back_to_verified_archive(self):
  with patch.object(source,'fetch_original',return_value=self.root/'official')as fetch:
   _,origin=source.acquire(self.plan,self.work,archive=Path('/offline.tar.gz'))
  self.assertEqual(origin,'official-fallback');fetch.assert_called_once()
 def test_retained_original_after_suite_install_is_reused(self):
  original=self.full('nvidia-original');(self.partial/'nvidia-suite-source.json').write_text(json.dumps({'original_source':str(original)}))
  with patch.object(source,'fetch_original')as fetch:result,_=source.acquire(self.plan,self.work)
  self.assertEqual(result,original);fetch.assert_not_called()
 def test_prepatched_missing_original_never_silently_discards_changes(self):
  (self.partial/'nvidia-suite-source.json').write_text('{}')
  with self.assertRaisesRegex(ValueError,'already patched'):source.acquire(self.plan,self.work)
