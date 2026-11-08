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
 def test_installed_full_tree_does_not_override_download(self):
  self.full('nvidia-full-610.43.02')
  with patch.object(source,'fetch_original',return_value=self.root/'official')as fetch:
   result,origin=source.acquire(self.plan,self.work)
  self.assertEqual(result,self.root/'official');self.assertEqual(origin,'official-download')
  fetch.assert_called_once_with(None,self.work)
 def test_multiple_local_trees_do_not_change_default(self):
  self.full('nvidia-a');self.full('nvidia-b')
  with patch.object(source,'fetch_original')as fetch:source.acquire(self.plan,self.work)
  fetch.assert_called_once_with(None,self.work)
 def test_offline_archive_is_explicit_and_verified(self):
  with patch.object(source,'fetch_original')as fetch:
   _,origin=source.acquire(self.plan,self.work,archive=Path('/offline.tar.gz'))
  self.assertEqual(origin,'official-archive');fetch.assert_called_once_with(Path('/offline.tar.gz'),self.work)
 def test_prior_suite_install_does_not_prevent_download(self):
  original=self.full('nvidia-original');(self.partial/'nvidia-suite-source.json').write_text(json.dumps({'original_source':str(original)}))
  with patch.object(source,'fetch_original')as fetch:source.acquire(self.plan,self.work)
  fetch.assert_called_once_with(None,self.work)
 def test_explicit_source_is_an_opt_in_override(self):
  original=self.full('nvidia-original')
  with patch.object(source,'fetch_original')as fetch:
   result,origin=source.acquire(self.plan,self.work,source=original)
  self.assertEqual(result,original);self.assertEqual(origin,'explicit-local-source');fetch.assert_not_called()
 def test_explicit_source_and_archive_conflict(self):
  with self.assertRaisesRegex(ValueError,'either'):
   source.acquire(self.plan,self.work,source=self.partial,archive=Path('/offline.tar.gz'))
 def test_explicit_prepatched_source_refused(self):
  (self.partial/'nvidia-suite-source.json').write_text('{}')
  with self.assertRaisesRegex(ValueError,'already patched'):source.acquire(self.plan,self.work,source=self.partial)

class SupportedDrivers(unittest.TestCase):
 def test_removing_entry_blocks_prepare_and_package(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'supported-drivers.json').write_text('{"schema_version":1,"drivers":{}}')
   with patch.object(source,'ROOT',root),patch.object(source,'acquire')as acquire:
    with self.assertRaisesRegex(ValueError,'Unsupported'):source.build_plan('610.43.02')
    with self.assertRaisesRegex(ValueError,'Unsupported'):source.prepare({'driver_version':'610.43.02'},root)
    with self.assertRaisesRegex(ValueError,'Unsupported'):package.build(root,root/'out')
    acquire.assert_not_called()
 def test_unreviewed_profile_is_not_enabled_by_listing(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'supported-drivers.json').write_text(json.dumps({'schema_version':1,'drivers':{'610.43.03':{'status':'supported','manifest':'manifest.json','source':'components/nvidia-bar1-p2p/vendor.json'}}}))
   with patch.object(source,'ROOT',root):
    with self.assertRaisesRegex(ValueError,'profile mismatch'):source.build_plan('610.43.03')
 def test_suite_version_and_upgrade_order(self):
  self.assertTrue(source.VERSION.startswith(source.RELEASE+'+nvidia.'))
  new='1:'+source.VERSION+'.pkg1.local.abcdef-1'
  subprocess.run(['dpkg','--compare-versions',new,'gt','610.43.02+suite.2.0.0.pkg14.local.abcdef-14'],check=True)
  with tempfile.TemporaryDirectory() as tmp:
   stage=Path(tmp);source.finalize(stage)
   self.assertIn('PACKAGE_VERSION="'+source.VERSION+'"',(stage/'dkms.conf').read_text())
   self.assertNotIn('@DRIVER_VERSION@',(stage/'check-modules.sh').read_text())
   self.assertIn(source.DRIVER,(stage/'check-modules.sh').read_text())

class CentralDriverMetadata(unittest.TestCase):
 def test_no_duplicate_production_version(self):
  self.assertNotIn('driver_version',source.META)
  self.assertFalse((source.BAR1/'vendor.json').exists())
  for directory in ('tools','packaging','bin'):
   for path in (ROOT/directory).rglob('*'):
    if path.is_file() and '__pycache__' not in path.parts:
     self.assertNotIn(source.DRIVER,path.read_text(),str(path))
 def test_registry_is_shared_by_component_and_cmp(self):
  import cmp_prepare
  entry=source.require_supported(source.DRIVER)
  self.assertEqual(source.base.VENDOR,entry['source'])
  self.assertEqual(cmp_prepare.verify()[0]['driver_version'],entry['driver_version'])
 def test_template_output_uses_selected_metadata(self):
  with tempfile.TemporaryDirectory() as tmp:
   stage=Path(tmp)
   with patch.object(source,'DRIVER','999.12.34'),patch.object(source,'VERSION','9.0+nvidia.999.12.34'):
    source.finalize(stage)
   self.assertIn('PACKAGE_VERSION="9.0+nvidia.999.12.34"',(stage/'dkms.conf').read_text())
   self.assertIn('999.12.34',(stage/'check-modules.sh').read_text())
   self.assertNotIn('@DRIVER_VERSION@',(stage/'check-modules.sh').read_text())
