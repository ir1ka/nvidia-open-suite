import importlib,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
inst=importlib.import_module('install')
class Takeover(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.work=self.root/'work';self.work.mkdir();self.source=self.root/'dkms/nvidia/610.43.02/source';self.source.mkdir(parents=True);(self.source/'dkms.conf').write_text('original')
  modules=self.root/'modules';(modules/'7.test/build').mkdir(parents=True);(modules/'7.test/build/Makefile').write_text('headers')
  row=dict(module='nvidia',version='610.43.02',kernel='7.test',arch='x86_64',state='installed')
  self.plan={'provider':dict(row,source=str(self.source)),'nvidia_records':[row]}
  self.status='nvidia/610.43.02, 7.test, x86_64: installed\n'
  for name,value in [('INSTALL_LOCK',self.root/'lock'),('MODULES_ROOT',modules)]:
   p=patch.object(inst,name,value);p.start();self.addCleanup(p.stop)
  self.root_patch=patch.object(inst.os,'geteuid',return_value=0);self.root_patch.start();self.addCleanup(self.root_patch.stop)
 def test_changed_state_aborts_before_apt_or_backup(self):
  with patch.object(inst.subprocess,'check_output',return_value=''),patch.object(inst,'run')as run:
   with self.assertRaisesRegex(ValueError,'changed'):inst.install(self.root/'x.deb',self.plan,self.work)
   run.assert_not_called()
  self.assertFalse((self.work/'rollback').exists())
 def test_unrelated_apt_removal_is_rejected(self):
  with patch.object(inst.subprocess,'check_output',side_effect=[self.status,'Remv cuda-toolkit [1]\n']),patch.object(inst,'run')as run:
   with self.assertRaisesRegex(ValueError,'Unexpected package removal'):inst.install(self.root/'x.deb',self.plan,self.work)
   run.assert_not_called()
  self.assertFalse((self.work/'rollback').exists())
 def test_multiple_providers_abort_without_removal(self):
  row=dict(self.plan['nvidia_records'][0],module='nvidia-other');self.plan['nvidia_records'].append(row)
  status=self.status+'nvidia-other/610.43.02, 7.test, x86_64: installed\n'
  with patch.object(inst.subprocess,'check_output',return_value=status),patch.object(inst,'run')as run:
   with self.assertRaisesRegex(ValueError,'Multiple'):inst.install(self.root/'x.deb',self.plan,self.work)
   run.assert_not_called()
 def test_manual_provider_is_preserved_and_refused(self):
  with patch.object(inst.subprocess,'check_output',side_effect=[self.status,'Inst suite\n']),patch.object(inst,'packages',return_value={}),patch.object(inst.subprocess,'run',return_value=subprocess.CompletedProcess([],1)),patch.object(inst,'run')as run:
   with self.assertRaisesRegex(ValueError,'Unmanaged'):inst.install(self.root/'x.deb',self.plan,self.work)
   run.assert_not_called()
  self.assertEqual((self.source/'dkms.conf').read_text(),'original')
  self.assertFalse((self.work/'rollback').exists())
 def test_managed_provider_removal_is_delegated_to_apt(self):
  with patch.object(inst.subprocess,'check_output',side_effect=[self.status,'Remv nvidia-kernel-dkms [610.43.02]\n']),patch.object(inst,'packages',return_value={'nvidia-kernel-dkms':'610.43.02'}),patch.object(inst.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout='nvidia-kernel-dkms: source\n')),patch.object(inst,'run')as run:
   inst.install(self.root/'x.deb',self.plan,self.work)
   self.assertEqual(run.call_count,1);self.assertEqual(run.call_args.args[0][0],'apt-get')
 def test_failed_apt_never_renames_or_restores_package_sources(self):
  calls=[]
  def execute(args,**kw):
   calls.append(list(args));(self.source/'dkms.conf').write_text('package-transaction-partial')
   raise subprocess.CalledProcessError(1,args)
  with patch.object(inst.subprocess,'check_output',side_effect=[self.status,'Remv nvidia-kernel-dkms [610.43.02]\n']),patch.object(inst,'packages',return_value={'nvidia-kernel-dkms':'610.43.02'}),patch.object(inst.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout='nvidia-kernel-dkms: source\n')),patch.object(inst,'run',side_effect=execute):
   with self.assertRaisesRegex(RuntimeError,'no manual source or DKMS rollback'):inst.install(self.root/'x.deb',self.plan,self.work)
  self.assertEqual(len(calls),1);self.assertEqual(calls[0][0],'apt-get')
  self.assertEqual((self.source/'dkms.conf').read_text(),'package-transaction-partial')
  self.assertFalse((self.work/'rollback').exists())

 def test_unknown_package_owner_refused_before_mutation(self):
  with patch.object(inst.subprocess,'check_output',side_effect=[self.status,'Inst suite\n']),patch.object(inst,'packages',return_value={}),patch.object(inst.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout='unrelated-gpu-manager: source\n')),patch.object(inst,'run')as run:
   with self.assertRaisesRegex(ValueError,'Unadapted original source package'):inst.install(self.root/'x.deb',self.plan,self.work)
   run.assert_not_called()
  self.assertFalse((self.work/'rollback').exists())
