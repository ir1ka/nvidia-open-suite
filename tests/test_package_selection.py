"""Explicit-version packaging must not inspect/misrepresent the build host."""
import importlib.machinery,importlib.util,subprocess,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import source,package
class Selection(unittest.TestCase):
 def test_explicit_version_needs_no_installed_driver(self):
  with patch.object(source,'detect',side_effect=AssertionError('must not inspect host')):
   plan=source.build_plan('610.43.02')
  self.assertEqual(plan['mode'],'explicit-version');self.assertEqual(plan['nvidia_records'],[])
 def test_default_still_validates_installed_open_dkms(self):
  with patch.object(source,'detect',return_value={'driver_version':'610.43.02'})as detect:
   self.assertEqual(source.build_plan(kernel='target')['mode'],'installed-driver')
  detect.assert_called_once_with('target')
 def test_install_never_skips_host_validation(self):
  with patch.object(source,'detect',return_value={'driver_version':'610.43.02'})as detect:
   self.assertEqual(source.build_plan('610.43.02',require_installed=True)['mode'],'installed-driver')
  detect.assert_called_once()
 def test_unknown_version_fails_without_host_detection(self):
  with patch.object(source,'detect')as detect:
   with self.assertRaisesRegex(ValueError,'Unsupported NVIDIA open'):source.build_plan('610.43.03')
  detect.assert_not_called()
 def test_offline_kernel_inspection_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'--kernel'):source.build_plan('610.43.02','target')
 def test_exact_target_revision_override(self):
  self.assertEqual(package.provide_versions(['nvidia-kernel-open-dkms=610.43.02-1']),{'nvidia-kernel-open-dkms':'610.43.02-1'})
 def test_installed_metadata_only_used_when_supplied(self):
  self.assertEqual(package.provide_versions(),{})
  self.assertEqual(package.provide_versions(installed={'nvidia-kernel-open-dkms':'610.43.02-1','unrelated':'1'}),{'nvidia-kernel-open-dkms':'610.43.02-1'})
 def test_cannot_advertise_another_driver_or_unrelated_package(self):
  for declaration in ['nvidia-kernel-open-dkms=610.43.03-1','cuda-toolkit=610.43.02-1','nvidia-kernel-open-dkms=610.43.02evil','nvidia-kernel-open-dkms=bad']:
   with self.subTest(declaration=declaration),self.assertRaises(ValueError):package.provide_versions([declaration])
 def test_epoch_version_supported(self):
  self.assertEqual(package.provide_versions(['nvidia-kernel-open-dkms=1:610.43.02-1'])['nvidia-kernel-open-dkms'],'1:610.43.02-1')
 def test_duplicate_declaration_refused(self):
  with self.assertRaises(ValueError):package.provide_versions(['nvidia-kernel-open-dkms=610.43.02-1']*2)
 def test_explicit_cli_never_queries_host_packages(self):
  loader=importlib.machinery.SourceFileLoader('selection_cli',str(ROOT/'bin/nvidia-open-suite'));spec=importlib.util.spec_from_loader(loader.name,loader);cli=importlib.util.module_from_spec(spec);loader.exec_module(cli)
  with tempfile.TemporaryDirectory()as tmp:
   work=Path(tmp)/'work';deb=Path(tmp)/'test.deb';deb.write_bytes(b'fixture')
   a=SimpleNamespace(driver_version='610.43.02',kernel=None,work=work,source=None,archive=None,provide_version=['nvidia-kernel-open-dkms=610.43.02-1'])
   with patch('install.packages',side_effect=AssertionError('must not inspect build host packages')),patch.object(source,'detect',side_effect=AssertionError('must not inspect host DKMS')),patch.object(source,'prepare',return_value=Path(tmp)),patch.object(package,'build',return_value=deb)as build:
    cli.make_package(a)
   self.assertEqual(build.call_args.args[2],{'nvidia-kernel-open-dkms':'610.43.02-1'})

 def test_full_installed_source_without_copying_gets_pinned_license(self):
  with tempfile.TemporaryDirectory()as tmp:
   stage=Path(tmp);source.finalize(stage)
   self.assertEqual(source.digest(stage/'COPYING'),source.META['nvidia_copying_sha256'])

 def test_firmware_target_mapping(self):
  self.assertEqual(package.firmware_dependency(), 'firmware-nvidia-gsp (= 610.43.02-1)')
  self.assertEqual(package.firmware_dependency('nvidia-firmware-610=610.43.02-0ubuntu1'), 'nvidia-firmware-610 (= 610.43.02-0ubuntu1)')
  self.assertEqual(package.firmware_dependency('firmware-nvidia-gsp=1:610.43.02-2'), 'firmware-nvidia-gsp (= 1:610.43.02-2)')
  with self.assertRaisesRegex(ValueError,'Non-Debian'):package.firmware_dependency(versions={'nvidia-dkms-610-open':'610.43.02-0ubuntu1'})
  for value in ('bad', 'pkg=610.43.03-1', 'pkg=610.43.02;bad', 'pkg=610.43.02-1, evil', '../pkg=610.43.02'):
   with self.subTest(value=value), self.assertRaises(ValueError):package.firmware_dependency(value)

class OpenProviderAliases(unittest.TestCase):
 def test_defaults_do_not_conflict_with_open_meta_package(self):
  names=package.provided_packages({'nvidia-kernel-open-dkms':'610.43.02-1'})
  self.assertIn('nvidia-kernel-open-dkms',names)
  self.assertNotIn('nvidia-kernel-dkms',names)
  self.assertNotIn('nvidia-dkms-610',names)
 def test_explicit_generic_provider_alias_remains_available(self):
  names=package.provided_packages({'nvidia-kernel-dkms':'610.43.02-1'})
  self.assertIn('nvidia-kernel-dkms',names)
