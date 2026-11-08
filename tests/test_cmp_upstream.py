"""Exercise original upstream scripts/config and the narrow source-only boundary."""
import importlib.util,os,shutil,subprocess,sys,tarfile,tempfile,unittest,shlex
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import cmp_prepare

class Upstream(unittest.TestCase):
 def test_original_files_and_patch_inventory_are_pinned(self):
  meta,upstream=cmp_prepare.verify()
  self.assertNotIn('upstream_files',meta)
  self.assertEqual(set(meta['patch_order']),{p.name for p in (upstream/'driver/patches').glob('*.patch')})
 def test_modified_upstream_config_is_not_rejected(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);shutil.copytree(ROOT/'vendor',root/'vendor');shutil.copytree(ROOT/'patches',root/'patches');shutil.copy2(ROOT/'manifest.json',root/'manifest.json');shutil.copy2(ROOT/'supported-drivers.json',root/'supported-drivers.json')
   p=root/'vendor/cmpunlocker/common/constants.yaml';p.write_text(p.read_text()+'\n# tampered\n')
   meta,_=cmp_prepare.verify(root)
   self.assertNotIn('upstream_files',meta)
 def test_original_constants_validator_for_every_profile(self):
  _,up=cmp_prepare.verify()
  for profile,cfg,lmr,label in [('mixed','0x02779000','0x0000020B','mixed'),('8gb','0x02779000','0x0000020B','64GB'),('10gb','0x02669000','0x0000028A','40GB')]:
   r=subprocess.run([sys.executable,str(up/'tools/read-constants.py'),str(up/'common/constants.yaml'),str(up/'driver/patches'),str(up/'driver/build.sh'),profile],check=True,capture_output=True,text=True)
   values={k:shlex.split(v)[0]for k,_,v in (line.partition('=')for line in r.stdout.splitlines())}
   self.assertEqual((values['CFG1'],values['LMR'],values['UNLOCK_LABEL']),(cfg,lmr,label))
 def test_direct_script_profile_and_source_only_stop(self):
  for profile,expected in [('8gb','0x02779000'),('10gb','0x02669000'),('mixed','0x00000000')]:
   with self.subTest(profile=profile),tempfile.TemporaryDirectory()as tmp:
    root=Path(tmp);recipe=root/'recipe';script=cmp_prepare.adapt_recipe(recipe)
    original=(ROOT/'vendor/cmpunlocker/driver/build.sh').read_text();adapted=script.read_text()
    # The full original source transformation phase is retained verbatim.
    a=original.index('    info "Applying unlock patches..."');b=original.index('    printf',a)
    self.assertIn(original[a:b],adapted)
    src=root/'input';gsp=src/'src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c';gsp.parent.mkdir(parents=True)
    gsp.write_text('NvU32 cfg1Value = 0x00000000U;\nNvU32 lmrValue = 0x00000000U;\nNvU64 targetFbBytes = 0x0000000000000000ULL; /* fixture */\n')
    build=root/'build';build.mkdir();name='open-gpu-kernel-modules-610.43.02'
    with tarfile.open(build/(name+'.tar.gz'),'w:gz')as t:t.add(src,arcname=name)
    # Only patch application is stubbed in this tiny fixture; the real pinned
    # helper validates real upstream patches and the original profile code runs.
    # Full patch application is separately exercised on the official archive.
    bin=root/'bin';bin.mkdir();trace=root/'trace'
    for name,body in [('patch','cat >/dev/null;echo patch >> "$TRACE"'),('uname','echo UNEXPECTED-uname >> "$TRACE";exit 97'),('make','echo UNEXPECTED-make >> "$TRACE";exit 97'),('modprobe','echo UNEXPECTED-modprobe >> "$TRACE";exit 97'),('depmod','echo UNEXPECTED-depmod >> "$TRACE";exit 97'),('systemctl','echo UNEXPECTED-systemctl >> "$TRACE";exit 97')]:
     p=bin/name;p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o755)
    env=dict(os.environ,PATH=str(bin)+':'+os.environ['PATH'],TRACE=str(trace),CMPUNLOCKER_PREPARE_ONLY='1',CMPUNLOCKER_DRIVER_VERSION='610.43.02',CMPUNLOCKER_CARD_PROFILE=profile,CMPUNLOCKER_BUILD_DIR=str(build))
    r=subprocess.run(['bash',str(script)],cwd=root,env=env,capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    self.assertEqual(trace.read_text().splitlines(),['patch']*14)
    out=build/'open-gpu-kernel-modules-610.43.02'/gsp.relative_to(src)
    self.assertIn('cfg1Value = '+expected+'U;',out.read_text())
    self.assertIn('compilation and installation delegated to DKMS',r.stdout)
    self.assertIn('cfg1Value = 0x00000000U;',gsp.read_text())

 def test_missing_submodule_has_actionable_error(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);shutil.copy2(ROOT/'manifest.json',root/'manifest.json');shutil.copy2(ROOT/'supported-drivers.json',root/'supported-drivers.json')
   with self.assertRaisesRegex(ValueError,'git submodule update --init --recursive'):
    cmp_prepare.verify(root)
 def test_exported_toolkit_has_upstream_files_without_git_metadata(self):
  import package
  with tempfile.TemporaryDirectory()as tmp:
   destination=Path(tmp)/'toolkit';package.export_toolkit(destination)
   exported=destination/'nvidia-open-suite'
   cmp_prepare.verify(exported)
   self.assertFalse((exported/'vendor/cmpunlocker/.git').exists())
   script=cmp_prepare.adapt_recipe(Path(tmp)/'recipe',exported)
   self.assertTrue(script.is_file())
   self.assertFalse((script.parents[1]/'.git').exists())
