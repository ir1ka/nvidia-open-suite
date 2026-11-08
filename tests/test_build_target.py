import os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class BuildTarget(unittest.TestCase):
 def test_explicit_headers_and_jobs_reach_make(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);headers=root/'target-headers';headers.mkdir();(headers/'Makefile').write_text('fixture')
   common=root/'common';(common/'include/linux').mkdir(parents=True);(common/'include/linux/pci.h').write_text('fixture')
   for name,body in [('make','if [ "$1" = -s ];then printf "%s\\n" "$TARGET_SOURCES";exit 0;fi\n'+'printf "%s\\n" "$@" > "$BUILD_ARGS"'),('bash','exit 0')]:
    p=root/name;p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o755)
   env=dict(os.environ,PATH=str(root)+':'+os.environ['PATH'],BUILD_ARGS=str(root/'args'),TARGET_SOURCES=str(common),NV_SUITE_JOBS='2',CC='target-cc')
   subprocess.run(['/bin/bash',str(ROOT/'packaging/suite-build.sh'),'target-abi',str(headers)],env=env,check=True)
   args=(root/'args').read_text().splitlines()
   for arg in ('-j2','CC=target-cc','KERNEL_UNAME=target-abi','SYSSRC='+str(common),'SYSOUT='+str(headers)):self.assertIn(arg,args)
   env['NV_SUITE_JOBS']='0'
   self.assertNotEqual(subprocess.run(['/bin/bash',str(ROOT/'packaging/suite-build.sh'),'target-abi',str(headers)],env=env,capture_output=True).returncode,0)
