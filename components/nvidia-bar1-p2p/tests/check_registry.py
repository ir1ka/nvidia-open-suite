#!/usr/bin/python3
"""Compile the actual per-device parser and verify opt-in group isolation."""
import argparse,ast,re,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);a=p.parse_args()
s=(a.source/'kernel-open/nvidia/os-registry.c').read_text()
def function(name):
 m=re.search(r'(?:static )?(?:NV_STATUS|NvBool)\s+'+name+r'\s*\(',s)
 if not m:raise ValueError(name)
 b=s.index('{',m.end());end=b+1;depth=1
 while depth:depth+=(s[end]=='{')-(s[end]=='}');end+=1
 return s[m.start():end]+'\n'
pre=r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
typedef uint32_t NvU32;typedef int NvBool;typedef int NV_STATUS;typedef int nvidia_stack_t;
#define nv_printf(...) ((void)0)
#define NV_DBG_ERRORS 1
#define NV_OK 0
#define NV_ERR_GENERIC 1
#define NV_ERR_INVALID_ARGUMENT 2
#define NV_FALSE 0
#define NV_TRUE 1
#define NV_REG_PCI_DEVICE_BDF "pci"
#define NV_STATE_PTR(p) (&(p)->nv)
#define simple_strtoul strtoul
#define os_free_mem free
typedef struct {struct{NvU32 domain,bus,slot,function;}pci_info;unsigned flag;}nv_state_t;
typedef struct{nv_state_t nv;}nv_linux_state_t;
static nv_linux_state_t published={.nv={.pci_info={0,0x16,0,0}}};
static nv_state_t probing={.pci_info={0,0x17,0,0}};
static unsigned probing_writes;
static char*NVreg_RegistryDwordsPerDevice;
static char*rm_remove_spaces(char*s){return strdup(s);}
static nv_linux_state_t*find_pci(unsigned d,unsigned b,unsigned s,unsigned f){return d==0&&b==0x16&&s==0&&f==0?&published:NULL;}
static void rm_write_registry_dword(nvidia_stack_t*sp,nv_state_t*nv,char*name,unsigned value){(void)sp;if(nv==&probing)probing_writes++;if(!strcmp(name,"RMFullBar1P2P"))nv->flag=value;}
'''
main=r'''
#define CHECK(string,flag,writes) do{probing.flag=9;probing_writes=0;NVreg_RegistryDwordsPerDevice=(string);if(nv_parse_per_device_option_string(NULL,&probing)!=NV_OK||probing.flag!=(flag)||probing_writes!=(writes)){fprintf(stderr,"FAIL %s\n",string);return 1;}}while(0)
int main(void){
 CHECK("pci=0000:16:00.0;RMFullBar1P2P=1;pci=0000:17:00.0;RMFullBar1P2P=1;",1,1);
 CHECK("pci=0000:17:00.0;RMFullBar1P2P=0;",0,1);
 CHECK("pci=0000:17:00.1;RMFullBar1P2P=1;",9,0);
 CHECK("pci=0001:17:00.0;RMFullBar1P2P=1;",9,0);
 CHECK("pci=0000:18:00.0;RMFullBar1P2P=1;",9,0);
 CHECK("pci=0000:17:00.0;RMPcieP2PType=1;",9,0);
 CHECK("pci=0000:17:00.0;RMPcieP2PType=1;pci=0000:18:00.0;RMFullBar1P2P=1;",9,0);
 CHECK("pci=0000:17:00.0;FooRMFullBar1P2P=1;",9,0);
 CHECK("pci=0000:17:00.0;RMPcieP2PType=1;RMFullBar1P2P=1;",1,1);
 CHECK("pci=0000:17:00.0;ForceP2P=17;RMForceStaticBar1=1;RMFullBar1P2P=1;",1,1);
 puts("PASS 10 actual parser cases: selected/unpublished GPU, opt-out, BDF/domain/function isolation, no cross-group leakage, legacy non-opt-in groups unchanged");return 0;
}
'''
# Avoid macro parameter substitution of the field name .flag.
main=main.replace('#define CHECK(string,flag,writes)','#define CHECK(string,expect,writes)').replace('probing.flag!=(flag)','probing.flag!=(expect)')
for key in ('RMFullBar1P2P', 'RMDynamicBar1P2P'):
 with tempfile.TemporaryDirectory()as temp:
  c=Path(temp)/'parser.c';b=Path(temp)/'parser'
  c.write_text(pre.replace('RMFullBar1P2P',key)+function('pci_str_to_bdf')+function('nv_parse_per_device_option_string')+main.replace('RMFullBar1P2P',key))
  subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror',str(c),'-o',str(b)],check=True)
  print('Registry key:',key,flush=True)
  subprocess.run([str(b)],check=True)
