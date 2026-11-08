#!/usr/bin/python3
"""Compile actual patched eligibility and peer-mask functions against GPU fixtures."""
import argparse,re,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);a=p.parse_args()
def extract(file,name):
 s=(a.source/file).read_text();m=re.search(r'(?:static )?(?:NvBool|NV_STATUS|void)\s*\n'+name+r'\s*\(',s)
 if not m:raise ValueError(name)
 start=m.start();brace=s.index('{',m.end());end=brace+1;depth=1
 while depth:depth+=(s[end]=='{')-(s[end]=='}');end+=1
 return s[start:end]+'\n'
common='src/nvidia/src/kernel/gpu/bus/kern_bus.c';gh='src/nvidia/src/kernel/gpu/bus/arch/hopper/kern_bus_gh100.c';caps='src/nvidia/src/kernel/platform/p2p/p2p_caps.c'
pre=r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t NvU8;typedef uint32_t NvU32;typedef uint64_t NvU64;typedef int NvBool;typedef int NV_STATUS;
#define NV_TRUE 1
#define NV_FALSE 0
#define NV_OK 0
#define NV_ERR_NOT_SUPPORTED 1
#define NV_U64_MAX UINT64_MAX
#define NVCPU_IS_ARM 0
#define NV_REG_STR_RM_PCIEP2P_TYPE_BAR1 1
#define NV_REG_STR_RM_PCIEP2P_TYPE_AUTO 2
#define NV_REG_STR_RM_PCIEP2P_TYPE "RMPcieP2PType"
#define NV_REG_STR_RM_FORCE_P2P_TYPE_DEFAULT 0
#define NV_REG_STR_RM_FORCE_P2P_TYPE_PCIEP2P 1
#define BIF_P2P_NOT_OVERRIDEN UINT32_MAX
#define NV_REG_STR_CL_FORCE_P2P_READ_DISABLE 2
#define NV_REG_STR_CL_FORCE_P2P_READ_ENABLE 1
#define NV_REG_STR_CL_FORCE_P2P_WRITE_DISABLE 2
#define NV_REG_STR_CL_FORCE_P2P_WRITE_ENABLE 1
#define NV_REG_STR_CL_FORCE_P2P_ATOMICS_DISABLE 2
#define NV_REG_STR_CL_FORCE_P2P_ATOMICS_ENABLE 1
#define NV0000_P2P_CAPS_STATUS_OK 0
#define NV0000_P2P_CAPS_STATUS_NOT_SUPPORTED 1
#define NV0000_P2P_CAPS_STATUS_DISABLED_BY_REGKEY 2
#define DRF_VAL(a,b,c,v) DRF_VAL##c(v)
#define DRF_VAL_READ(v) ((v)&15)
#define DRF_VAL_WRITE(v) (((v)>>4)&15)
#define DRF_VAL_ATOMICS(v) (((v)>>8)&15)
#define PDB_PROP_KBUS_SUPPORT_BAR1_P2P_BY_DEFAULT 1
typedef struct{unsigned pcieP2PType,forceP2PType,p2pOverride;}KernelBif;
typedef struct{struct{NvU64 fbAddrSpaceSizeMb;}Ram;}MemoryManager;
typedef struct OBJGPU{unsigned instance,arch,req,virt,mig,enabled;KernelBif bif;MemoryManager*mem;}OBJGPU;
typedef struct KernelBus{NvU64 bar;unsigned native_default;struct{unsigned peerNumberMask[2];}p2pPcie;int(*getProperty)(struct KernelBus*,int);}KernelBus;
static KernelBus buses[2];static OBJGPU g[2];
#define GPU_GET_MEMORY_MANAGER(x) ((x)->mem)
#define GPU_GET_KERNEL_BIF(x) (&(x)->bif)
#define GPU_GET_KERNEL_BUS(x) (&buses[(x)->instance])
#define IS_VIRTUAL(x) ((x)->virt)
#define IS_MIG_ENABLED(x) ((x)->mig)
#define gpuGetInstance(x) ((x)->instance)
static int osReadRegistryDword(OBJGPU*x,const char*name,NvU32*out){if(strcmp(name,"RMFullBar1P2P"))return 1;*out=x->req;return NV_OK;}
static NvU64 kbusGetPciBarSize(KernelBus*b,int index){(void)index;return b->bar;}
static int kbusIsStaticBar1Enabled(OBJGPU*x,KernelBus*b){(void)b;return x->enabled;}
static int prop(KernelBus*b,int property){(void)property;return b->native_default;}
NvBool kbusIsPcieBar1P2PMappingSupported_GH100(OBJGPU*,KernelBus*,OBJGPU*,KernelBus*);
'''
pre += '\nstatic NvBool kbusDynamicBar1P2PPair(OBJGPU*a,OBJGPU*b){(void)a;(void)b;return NV_FALSE;}\nstatic NvBool _kp2pDynamicBar1Override(NvU32 mask){(void)mask;return NV_FALSE;}\n'
functions=extract(common,'kbusFullBar1P2PRequested')+extract(common,'kbusFullBar1P2PEligible')+extract(gh,'kbusIsPcieBar1P2PMappingSupported_GH100')+extract(common,'kbusIsPcieBar1P2PMappingSupported_FULLBAR1')
functions+=r'''
static unsigned get_calls,create_calls,remove_calls;
static NV_STATUS kbusGetBar1P2PDmaInfo_GH100(OBJGPU*a,OBJGPU*b,KernelBus*c,NvU64*d,NvU64*e){(void)a;(void)b;(void)c;*d=1;*e=2;get_calls++;return NV_OK;}
static NV_STATUS kbusCreateP2PMappingForBar1P2P_GH100(OBJGPU*a,KernelBus*b,OBJGPU*c,KernelBus*d,NvU32 e){(void)e;b->p2pPcie.peerNumberMask[c->instance]=0;d->p2pPcie.peerNumberMask[a->instance]=0;create_calls++;return NV_OK;}
static NvBool kbusHasPcieBar1P2PMapping_GH100(OBJGPU*a,KernelBus*b,OBJGPU*c,KernelBus*d){return b->native_default&&d->native_default&&(a!=c);}
static NV_STATUS kbusRemoveP2PMappingForBar1P2P_GH100(OBJGPU*a,KernelBus*b,OBJGPU*c,KernelBus*d,NvU32 e){(void)a;(void)c;(void)e;b->native_default=d->native_default=0;remove_calls++;return NV_OK;}
'''
functions+=''.join(extract(common,n)for n in ('kbusGetBar1P2PDmaInfo_FULLBAR1','kbusCreateP2PMappingForBar1P2P_FULLBAR1','kbusHasPcieBar1P2PMapping_FULLBAR1','kbusRemoveP2PMappingForBar1P2P_FULLBAR1'))
functions+=r'''
#define kbusIsPcieBar1P2PMappingSupported_HAL kbusIsPcieBar1P2PMappingSupported_FULLBAR1
static unsigned gpumgrGetSubDeviceCount(unsigned mask){return __builtin_popcount(mask);}
static OBJGPU*gpumgrGetNextGpu(unsigned mask,unsigned*index){while(*index<2){unsigned i=(*index)++;if(mask&(1u<<i))return &g[i];}return NULL;}
'''+extract(caps,'_kp2pFullBar1Override')+extract(caps,'_kp2pCapsCheckStatusOverridesForPcie')
main=r'''
static unsigned count;
#define T(expr) do{count++;if(!(expr)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#expr);return 1;}}while(0)
#define PAIR() kbusIsPcieBar1P2PMappingSupported_FULLBAR1(&g[0],&buses[0],&g[1],&buses[1])
int main(void){
 MemoryManager mem[2]={{{40960}},{{40960}}};
 for(int i=0;i<2;i++){g[i]=(OBJGPU){.instance=i,.arch=0x170,.req=1,.enabled=1,.bif={0,0,UINT32_MAX},.mem=&mem[i]};buses[i]=(KernelBus){.bar=64ULL<<30,.getProperty=prop};}
 T(PAIR());T(_kp2pFullBar1Override(3));T(!_kp2pFullBar1Override(1));T(!_kp2pFullBar1Override(0));
 unsigned capacities[]={4,8,11,12,24,40,48,80,96,192};
 unsigned arches[]={0x160,0x170,0x172,0x190,0x200,0x210};
 for(unsigned j=0;j<sizeof(capacities)/sizeof(*capacities);j++){
  for(int i=0;i<2;i++){mem[i].Ram.fbAddrSpaceSizeMb=(NvU64)capacities[j]<<10;buses[i].bar=(NvU64)capacities[j]<<30;}
  for(unsigned k=0;k<sizeof(arches)/sizeof(*arches);k++){g[0].arch=arches[k];g[1].arch=arches[(k+1)%6];T(PAIR());}
  for(int i=0;i<2;i++){buses[i].bar--;T(!PAIR());buses[i].bar++;}
 }
 for(int i=0;i<2;i++){
  g[i].req=0;T(!PAIR());T(!_kp2pFullBar1Override(3));g[i].req=1;
  g[i].virt=1;T(!PAIR());g[i].virt=0;
  g[i].mig=1;T(!PAIR());g[i].mig=0;
  g[i].enabled=0;T(!PAIR());g[i].enabled=1;
  NvU64 mb=mem[i].Ram.fbAddrSpaceSizeMb;mem[i].Ram.fbAddrSpaceSizeMb=0;T(!PAIR());mem[i].Ram.fbAddrSpaceSizeMb=UINT64_MAX;T(!PAIR());mem[i].Ram.fbAddrSpaceSizeMb=mb;
  g[i].mem=NULL;T(!PAIR());g[i].mem=&mem[i];
 }
 NvU64 address=0,size=0;
 T(kbusGetBar1P2PDmaInfo_FULLBAR1(&g[0],&g[1],&buses[1],&address,&size)==NV_OK);T(get_calls==1);
 g[0].req=0;
 T(kbusGetBar1P2PDmaInfo_FULLBAR1(&g[0],&g[1],&buses[1],&address,&size)==NV_ERR_NOT_SUPPORTED);T(get_calls==1);
 T(kbusCreateP2PMappingForBar1P2P_FULLBAR1(&g[0],&buses[0],&g[1],&buses[1],0)==NV_ERR_NOT_SUPPORTED);T(create_calls==0);
 /* Cleanup is allowed even if eligibility has disappeared after a mapping. */
 buses[0].native_default=buses[1].native_default=1;
 T(kbusHasPcieBar1P2PMapping_FULLBAR1(&g[0],&buses[0],&g[1],&buses[1]));
 T(kbusRemoveP2PMappingForBar1P2P_FULLBAR1(&g[0],&buses[0],&g[1],&buses[1],0)==NV_OK);T(remove_calls==1);
 g[0].req=1;g[0].bif.forceP2PType=2;T(!PAIR());g[0].bif.forceP2PType=0;
 T(!kbusFullBar1P2PEligible(NULL,&buses[0]));T(!kbusFullBar1P2PEligible(&g[0],NULL));
 T(!kbusIsPcieBar1P2PMappingSupported_FULLBAR1(&g[0],&buses[0],&g[0],&buses[0]));
 buses[0].p2pPcie.peerNumberMask[1]=1;T(!PAIR());buses[0].p2pPcie.peerNumberMask[1]=0;
 NvU8 read=99,write=99,atomics=99;
 T(_kp2pCapsCheckStatusOverridesForPcie(3,&write,&read,&atomics));T(read==0&&write==0&&atomics==1);
 g[0].bif.p2pOverride=0x222;read=write=atomics=99;
 T(_kp2pCapsCheckStatusOverridesForPcie(3,&write,&read,&atomics));T(read==2&&write==2&&atomics==2);
 g[0].bif.p2pOverride=UINT32_MAX;g[0].req=0;read=write=atomics=99;
 T(!_kp2pCapsCheckStatusOverridesForPcie(3,&write,&read,&atomics));T(read==99&&write==99&&atomics==99);
 g[0].req=1;
 /* Untouched native GH support still works on partial apertures without opt-in. */
 g[0].req=g[1].req=0;buses[0].bar=buses[1].bar=256ULL<<20;buses[0].native_default=1;
 T(kbusIsPcieBar1P2PMappingSupported_GH100(&g[0],&buses[0],&g[1],&buses[1]));T(!PAIR());T(!_kp2pFullBar1Override(3));
 printf("PASS %u actual-function assertions: capacities, mixed architectures, small BAR1, opt-out, MIG/VF, static mapping, overflow, mailbox/loopback, native behavior\n",count);
 return 0;
}
'''
with tempfile.TemporaryDirectory()as temp:
 c=Path(temp)/'guard.c';binary=Path(temp)/'guard';c.write_text(pre+functions+main)
 subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror',str(c),'-o',str(binary)],check=True);subprocess.run([str(binary)],check=True)
