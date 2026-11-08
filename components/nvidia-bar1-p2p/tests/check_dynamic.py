#!/usr/bin/env python3
"""Execute actual dynamic BAR1 manager/encoder with allocation, DMA and lock fault injection.
No GPU access. These fixtures do not establish CUDA/GSP or hardware acceptance.
"""
import argparse
import re
import subprocess
import tempfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
p.add_argument('--compile-only', action='store_true', help='Compile fixtures and inspect integration without executing synthetic runtime tests')
a=p.parse_args()
rm=a.source/'src/nvidia/src/kernel/rmapi'
def extract(s,name):
 m=re.search(r'(?:static\s+)?(?:NV_STATUS|NvBool|void|bool)\s+'+name+r'\s*\([^;{]*\)\s*\{',s);assert m,name
 end=m.end();depth=1
 while depth:depth+=(s[end]=='{')-(s[end]=='}');end+=1
 return s[m.start():end]+'\n'
pre=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
typedef uint64_t NvU64;typedef uint32_t NvU32;typedef uint32_t NvHandle;
typedef uint64_t RmPhysAddr;typedef int NvBool;typedef int NV_STATUS;
#define NV_TRUE 1
#define NV_FALSE 0
#define NV_OK 0
#define NV_ERR_NOT_SUPPORTED 1
#define NV_ERR_INVALID_LIMIT 2
#define NV_ERR_INSUFFICIENT_RESOURCES 3
#define NV_ERR_INVALID_LOCK_STATE 4
#define NV_ERR_NO_MEMORY 5
#define NV_ERR_INVALID_STATE 6
#define NV_ERR_INVALID_ADDRESS 7
#define NV_U64_MAX UINT64_MAX
#define NV_MIN(a,b) ((a)<(b)?(a):(b))
#define NV_ASSERT assert
#define NV_ASSERT_OR_RETURN(x,e) do {if(!(x)) return (e);}while(0)
#define NV_PRINTF(...) ((void)0)
#define BUS_MAP_FB_FLAGS_MAP_UNICAST 1
#define BUS_MAP_FB_FLAGS_KEEP_AREA_ON_ERROR 2
#define BUS_MAP_FB_FLAGS_PAGE_SIZE_4K 4
#define BUS_MAP_FB_FLAGS_PAGE_SIZE_64K 8
#define BUS_MAP_FB_FLAGS_PAGE_SIZE_2M 16
#define BUS_MAP_FB_FLAGS_ALLOW_RESOURCE_FAILURE 32
#define MEMDESC_FLAGS_ENCRYPTED 1
#define MEMDESC_FLAGS_GPU_PRIVILEGED 2
#define MEMDESC_FLAGS_NONE 0
#define NV_MEMORY_CONTIGUOUS 1
#define NV_MEMORY_UNCACHED 0
#define ADDR_SYSMEM 0
#define ADDR_FBMEM 1
#define AT_GPU 1
#define RMAPI_LOCK_FLAGS_READ 1
#define THREAD_STATE_FLAGS_NONE 0
#define MIB (1ULL<<20)
#define NVCPU_IS_ARM 0
#define GPU_ARCHITECTURE_AMPERE 0x170
#define GPU_ARCHITECTURE_ADA 0x190
#define GPU_ARCHITECTURE_TURING 0x160
#define GPU_IMPLEMENTATION_TU102 2
#define NV_REG_STR_RM_FORCE_P2P_TYPE_DEFAULT 0
#define NV_REG_STR_RM_FORCE_P2P_TYPE_PCIEP2P 1
#define NV_REG_STR_RM_PCIEP2P_TYPE_BAR1 1
#define NV_REG_STR_RM_PCIEP2P_TYPE_AUTO 2
#define NV_REG_STR_RM_PCIEP2P_TYPE "RMPcieP2PType"
typedef struct {NvU64 start,size;} MemoryRange;
typedef struct {MemoryRange*pRanges;NvU64 numRanges;} MemoryArea;
typedef struct {NvU32 dynamicP2PQuarantined;NvU64 dynamicP2PBytes,mappableLength;void*pVAS;} Bar1VaInfo;
typedef struct {Bar1VaInfo bar1[1];NvU64 size;bool staticEnabled;struct {NvU32 peerNumberMask[8];}p2pPcie;}KernelBus;
typedef struct {NvU32 forceP2PType;}KernelBif;
typedef struct {struct {NvU64 fbAddrSpaceSizeMb;}Ram;}MemoryManager;
typedef struct OBJGPU {KernelBus*bus;KernelBif*bif;MemoryManager*memory;unsigned instance;struct{NvU32 iovaspaceId;}busInfo;bool virt,mig,cc,sli;unsigned arch,opt,type,impl;NvU64 phys;}OBJGPU;
typedef struct {OBJGPU*pGpu;NvU64 size;unsigned flags;int space;}MEMORY_DESCRIPTOR;
typedef struct {struct gpuDynBar1P2PMapping*pDynBar1List;}subDeviceDesc;
typedef struct {NvHandle handle;}gpuSession;
struct gpuDevice {subDeviceDesc*rmSubDevice;gpuSession*session;};
typedef struct {int dummy;} nvGpuOpsLockSet;
typedef int THREAD_STATE_NODE;
#define GPU_GET_KERNEL_BUS(g) ((g)->bus)
#define GPU_GET_KERNEL_BIF(g) ((g)->bif)
#define GPU_GET_MEMORY_MANAGER(g) ((g)->memory)
#define IS_VIRTUAL(g) ((g)->virt)
#define IS_MIG_ENABLED(g) ((g)->mig)
#define IsSLIEnabled(g) ((g)->sli)
#define gpuIsCCFeatureEnabled(g) ((g)->cc)
#define gpuGetChipArch(g) ((g)->arch)
#define gpuGetChipImpl(g) ((g)->impl)
static int osReadRegistryDword(OBJGPU*g,const char*n,NvU32*v){*v=!strcmp(n,"RMDynamicBar1P2P")?g->opt:g->type;return NV_OK;}
static unsigned gpuGetInstance(OBJGPU*g){return g->instance;}
static NvU64 kbusGetPciBarSize(KernelBus*b,int i){(void)i;return b->size;}
static bool kbusIsStaticBar1Enabled(OBJGPU*g,KernelBus*b){(void)g;return b->staticEnabled;}
static int unmap_fail, fail_step, locked=1, lock_fail, live_node,live_aperture,live_md,live_dma,drain_releases;
static unsigned events[16],n_events;
static NvU64 dma_base, aperture_offset=2*MIB;
static bool rmDeviceGpuLockIsOwner(unsigned i){(void)i;return locked;}
static void*portMemAllocNonPaged(size_t n){if(fail_step==1)return NULL;live_node++;return calloc(1,n);}
static void portMemFree(void*p){assert(p);live_node--;free(p);}
#define portMemSet memset
static NvU64 memdescGetSize(MEMORY_DESCRIPTOR*m){return m->size;}
static int memdescGetAddressSpace(MEMORY_DESCRIPTOR*m){return m->space;}
static bool memdescGetFlag(MEMORY_DESCRIPTOR*m,unsigned f){return (m->flags&f)!=0;}
static NvU64 gpumgrGetGpuPhysFbAddr(OBJGPU*g){return g->phys;}
static bool portSafeAddU64(NvU64 a,NvU64 b,NvU64*out){if(a>UINT64_MAX-b)return false;*out=a+b;return true;}
static MemoryRange mrangeMake(NvU64 a,NvU64 b){return (MemoryRange){a,b};}
static int kbusMapFbAperture_HAL(OBJGPU*g,KernelBus*b,MEMORY_DESCRIPTOR*m,MemoryRange range,MemoryArea*out,int flags,void*dev){
 (void)g;(void)b;(void)m;(void)dev;assert(locked&&flags==33);
 if(fail_step==2)return NV_ERR_INSUFFICIENT_RESOURCES;
 out->pRanges=malloc(sizeof(MemoryRange));*out->pRanges=(MemoryRange){aperture_offset,range.size};out->numRanges=fail_step==3?2:1;live_aperture++;return 0;
}
static int kbusUnmapFbAperture_HAL(OBJGPU*g,KernelBus*b,MEMORY_DESCRIPTOR*m,MemoryArea area,int flags){
 (void)g;(void)b;(void)m;assert(locked&&flags==35);if(unmap_fail)return NV_ERR_INVALID_STATE;events[n_events++]=3;free(area.pRanges);live_aperture--;return 0;
}
static int memdescCreate(MEMORY_DESCRIPTOR**out,OBJGPU*g,NvU64 size,int align,int contig,int space,int cache,int flags){
 (void)align;(void)contig;(void)cache;(void)flags;if(fail_step==4)return NV_ERR_NO_MEMORY;
 *out=calloc(1,sizeof(**out));**out=(MEMORY_DESCRIPTOR){g,size,0,space};live_md++;return 0;
}
static void memdescDescribe(MEMORY_DESCRIPTOR*m,int s,NvU64 p,NvU64 n){(void)m;(void)s;(void)p;(void)n;}
static int memdescMapIommu(MEMORY_DESCRIPTOR*m,unsigned i){(void)m;(void)i;if(fail_step==5)return NV_ERR_INSUFFICIENT_RESOURCES;live_dma++;return 0;}
static void memdescUnmapIommu(MEMORY_DESCRIPTOR*m,unsigned i){(void)m;(void)i;assert(locked);events[n_events++]=1;live_dma--;}
static void memdescDestroy(MEMORY_DESCRIPTOR*m){events[n_events++]=2;live_md--;free(m);}
static void memdescGetPtePhysAddrsForGpu(MEMORY_DESCRIPTOR*m,OBJGPU*g,int at,int off,int ps,int count,NvU64*out){(void)m;(void)g;(void)at;(void)off;(void)ps;assert(count==1);*out=fail_step==6?UINT64_MAX:dma_base;}
static void threadStateInit(THREAD_STATE_NODE*t,int f){(void)t;(void)f;}
static void threadStateFree(THREAD_STATE_NODE*t,int f){(void)t;(void)f;}
static int _nvGpuOpsLocksAcquireAll(int f,unsigned h,void*p,nvGpuOpsLockSet*l){(void)f;(void)h;(void)p;(void)l;if(lock_fail)return NV_ERR_INVALID_LOCK_STATE;locked=1;return 0;}
static void _nvGpuOpsLocksRelease(nvGpuOpsLockSet*l){(void)l;locked=0;drain_releases++;}
'''
bus=(a.source/'src/nvidia/src/kernel/gpu/bus/kern_bus.c').read_text()
functions=extract(bus,'kbusDynamicBar1P2PEligible')+extract(bus,'kbusDynamicBar1P2PPair')
functions+=(rm/'nv_gpu_ops_dynamic_bar1.h').read_text()
functions+=extract((rm/'nv_gpu_ops.c').read_text(),'_nvGpuOpsEncodeDynBar1P2PAddrs')
main=r'''
int main(void){
 KernelBif bif={0};MemoryManager fb={{24576}};
 KernelBus buses[3]={0};OBJGPU g[3]={0};
 for(unsigned i=0;i<3;i++){buses[i].size=256*MIB;buses[i].bar1[0].mappableLength=256*MIB;buses[i].bar1[0].pVAS=&buses[i];g[i]=(OBJGPU){.bus=&buses[i],.bif=&bif,.memory=&fb,.instance=i,.busInfo={i},.arch=GPU_ARCHITECTURE_AMPERE,.opt=1,.type=2,.phys=1ULL<<40};}
 assert(kbusDynamicBar1P2PPair(g,g+1));assert(!kbusDynamicBar1P2PPair(g,g));
 g[0].opt=0;assert(!kbusDynamicBar1P2PPair(g,g+1));g[0].opt=1;
 // GA102/103/104/106/107 and AD102/103/104/106/107 share the family gate.
 // This checks admission only, not physical compatibility or CUDA acceptance.
 const unsigned consumer_impls[]={2,3,4,6,7};
 for(unsigned i=0;i<5;i++){
  g[0].impl=consumer_impls[i];
  g[0].arch=GPU_ARCHITECTURE_AMPERE;assert(kbusDynamicBar1P2PPair(g,g+1));
  g[0].arch=GPU_ARCHITECTURE_ADA;assert(kbusDynamicBar1P2PPair(g,g+1));
  g[0].opt=0;assert(!kbusDynamicBar1P2PPair(g,g+1));g[0].opt=1;
 }
 g[0].arch=0x180;assert(!kbusDynamicBar1P2PPair(g,g+1));
 g[0].arch=0x1a0;assert(!kbusDynamicBar1P2PPair(g,g+1));
 g[0].arch=0x1b0;assert(!kbusDynamicBar1P2PPair(g,g+1));
 g[0].arch=GPU_ARCHITECTURE_AMPERE;g[0].impl=0;
 g[0].arch=GPU_ARCHITECTURE_TURING;g[0].impl=2;assert(kbusDynamicBar1P2PPair(g,g+1));
 g[0].impl=4;assert(!kbusDynamicBar1P2PPair(g,g+1));g[0].arch=GPU_ARCHITECTURE_AMPERE;
 g[0].mig=1;assert(!kbusDynamicBar1P2PPair(g,g+1));g[0].mig=0;
 g[0].virt=1;assert(!kbusDynamicBar1P2PPair(g,g+1));g[0].virt=0;
 g[0].cc=1;assert(!kbusDynamicBar1P2PPair(g,g+1));g[0].cc=0;
 g[0].sli=1;assert(!kbusDynamicBar1P2PPair(g,g+1));g[0].sli=0;
 buses[0].size=32ULL<<30;assert(!kbusDynamicBar1P2PPair(g,g+1));buses[0].size=256*MIB;
 buses[0].staticEnabled=1;assert(!kbusDynamicBar1P2PPair(g,g+1));buses[0].staticEnabled=0;
 buses[0].p2pPcie.peerNumberMask[1]=1;assert(!kbusDynamicBar1P2PPair(g,g+1));buses[0].p2pPcie.peerNumberMask[1]=0;
 bif.forceP2PType=9;assert(!kbusDynamicBar1P2PPair(g,g+1));bif.forceP2PType=0;
 g[0].type=9;assert(!kbusDynamicBar1P2PPair(g,g+1));g[0].type=2;
 NvU64 charge=0,out=99;NvBool created=1;
 assert(_nvGpuOpsDynBar1Charge(256*MIB,0,192*MIB,&charge)==0&&charge==192*MIB);
 assert(_nvGpuOpsDynBar1Charge(256*MIB,0,192*MIB+1,&charge)!=0);
 assert(_nvGpuOpsDynBar1Charge(256*MIB,0,UINT64_MAX,&charge)!=0);
 assert(_nvGpuOpsDynBar1Charge(64*MIB,0,4096,&charge)!=0);
 subDeviceDesc sub={0},other={0};MEMORY_DESCRIPTOR alloc={g+1,64*MIB,0,ADDR_FBMEM};
 for(int stage=1;stage<=6;stage++){
  fail_step=stage;n_events=0;
  assert(_nvGpuOpsDynBar1GetOrCreate(&sub,g,g+1,&alloc,1,&out,&created)!=0);
  assert(!sub.pDynBar1List&&!created&&!buses[1].bar1[0].dynamicP2PBytes);
  assert(!live_node&&!live_aperture&&!live_md&&!live_dma);
 }
 fail_step=0;n_events=0;locked=0;
 assert(_nvGpuOpsDynBar1GetOrCreate(&sub,g,g+1,&alloc,1,&out,&created)==NV_ERR_INVALID_LOCK_STATE);
 assert(!live_node);locked=1;
 assert(_nvGpuOpsDynBar1GetOrCreate(&sub,g,g+1,&alloc,1,&out,&created)==0&&created&&out==0);
 assert(_nvGpuOpsDynBar1GetOrCreate(&sub,g,g+1,&alloc,1,&out,&created)==0&&!created);
 assert(live_node==1&&buses[1].bar1[0].dynamicP2PBytes==64*MIB);
 assert(_nvGpuOpsDynBar1GetOrCreate(&sub,g+2,g+1,&alloc,1,&out,&created)==NV_ERR_INVALID_STATE);
 alloc.size=128*MIB;
 assert(_nvGpuOpsDynBar1GetOrCreate(&other,g+2,g+1,&alloc,1,&out,&created)==0);
 assert(buses[1].bar1[0].dynamicP2PBytes==192*MIB);
 assert(_nvGpuOpsDynBar1GetOrCreate(&other,g+2,g+1,&alloc,2,&out,&created)==NV_ERR_INSUFFICIENT_RESOURCES);
 n_events=0;_nvGpuOpsDynBar1Destroy(&sub,1);
 assert(n_events==3&&events[0]==1&&events[1]==2&&events[2]==3);
 assert(buses[1].bar1[0].dynamicP2PBytes==128*MIB&&other.pDynBar1List);
 _nvGpuOpsDynBar1Destroy(&sub,1);assert(n_events==3);
 gpuSession session={1};struct gpuDevice dev={&other,&session};lock_fail=1;locked=0;
 assert(_nvGpuOpsDynBar1Drain(&dev)==NV_ERR_INVALID_LOCK_STATE);
 assert(other.pDynBar1List&&live_dma==1&&buses[1].bar1[0].dynamicP2PBytes==128*MIB&&drain_releases==0);
 lock_fail=0;n_events=0;assert(_nvGpuOpsDynBar1Drain(&dev)==0);
 assert(!other.pDynBar1List&&!live_node&&!live_aperture&&!live_md&&!live_dma&&!buses[1].bar1[0].dynamicP2PBytes);
 assert(drain_releases==1);locked=1;
 for(unsigned i=0;i<1000;i++){
  n_events=0;alloc.size=MIB;
  assert(_nvGpuOpsDynBar1GetOrCreate(&sub,g,g+1,&alloc,i+1,&out,&created)==0);
  _nvGpuOpsDynBar1Destroy(&sub,i+1);
  assert(!buses[1].bar1[0].dynamicP2PBytes&&!live_dma&&!live_node);
 }
 // Failed unmap retains the allocation, range and budget; DMA is revoked once.
 n_events=0;assert(_nvGpuOpsDynBar1GetOrCreate(&sub,g,g+1,&alloc,7,&out,&created)==0);
 locked=0;assert(_nvGpuOpsDynBar1Destroy(&sub,7)==NV_ERR_INVALID_LOCK_STATE&&live_dma==1);locked=1;
 unmap_fail=1;assert(_nvGpuOpsDynBar1Destroy(&sub,7)!=0);
 assert(buses[1].bar1[0].dynamicP2PQuarantined==1);
 assert(_nvGpuOpsDynBar1GetOrCreate(&other,g+2,g+1,&alloc,99,&out,&created)==NV_ERR_INVALID_STATE);
 assert(sub.pDynBar1List&&live_aperture==1&&live_dma==0&&live_md==0&&buses[1].bar1[0].dynamicP2PBytes);
 assert(_nvGpuOpsDynBar1GetOrCreate(&sub,g,g+1,&alloc,7,&out,&created)==NV_ERR_INVALID_STATE);
 dev.rmSubDevice=&sub;assert(_nvGpuOpsDynBar1Drain(&dev)!=0&&sub.pDynBar1List);
 unmap_fail=0;assert(_nvGpuOpsDynBar1Drain(&dev)==0&&!sub.pDynBar1List&&!live_node&&!live_aperture);locked=1;
 // Failure of allocation AND rollback is also owned, then released on retry.
 fail_step=5;unmap_fail=1;n_events=0;
 assert(_nvGpuOpsDynBar1GetOrCreate(&sub,g,g+1,&alloc,8,&out,&created)!=0&&sub.pDynBar1List);
 assert(live_dma==0&&live_md==0&&buses[1].bar1[0].dynamicP2PBytes);
 unmap_fail=0;fail_step=0;assert(_nvGpuOpsDynBar1Drain(&dev)==0&&!live_node&&!live_aperture);locked=1;
 assert(!buses[1].bar1[0].dynamicP2PQuarantined);
 NvU64 addresses[2]={99,99};
 assert(_nvGpuOpsEncodeDynBar1P2PAddrs(addresses,0,8192,0,8192,4096,2)==0&&addresses[0]==0&&addresses[1]==4096);
 assert(_nvGpuOpsEncodeDynBar1P2PAddrs(addresses,0,8192,4096,4096,4096,1)==0&&addresses[0]==4096);
 assert(_nvGpuOpsEncodeDynBar1P2PAddrs(addresses,0,8192,8192,4096,4096,1)!=0);
 assert(_nvGpuOpsEncodeDynBar1P2PAddrs(addresses,0,8192,0,0,4096,1)!=0);
 assert(_nvGpuOpsEncodeDynBar1P2PAddrs(addresses,1,8192,0,4096,4096,1)!=0);
 assert(_nvGpuOpsEncodeDynBar1P2PAddrs(addresses,UINT64_MAX-4095,8192,0,8192,4096,2)!=0);
 assert(_nvGpuOpsEncodeDynBar1P2PAddrs(addresses,0x30004a0000ULL,32*MIB,0,32*MIB,2*MIB,2)!=0);
 assert(_nvGpuOpsEncodeDynBar1P2PAddrs(addresses,0x30004a0000ULL,32*MIB,0,32*MIB,4096,2)==0);
 puts("PASS actual dynamic manager: eligibility, six transactional failures, zero IOVA, shared target budget, duplicate ownership, cleanup order, lock/unmap failure quarantine/retry, 1000 create/free cycles, encoder bounds/overflow");
}
'''
with tempfile.TemporaryDirectory() as temp:
 c=Path(temp)/'test.c';exe=Path(temp)/'test';c.write_text(pre+functions+main)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-g',str(c),'-o',str(exe)],check=True)
 if not a.compile_only: subprocess.run([exe],check=True)
 else: print('PASS fixture compilation only; runtime assertions not executed')
# Structural integration assertions complement execution of the actual manager.
s=(rm/'nv_gpu_ops.c').read_text();free=extract(s,'nvGpuOpsFreeDupedHandle');destroy=extract(s,'nvGpuOpsDeviceDestroy')
assert free.index('_nvGpuOpsDynBar1Destroy')<free.index('rmGpuGroupLockRelease')<free.index('_disablePeerAccess')<free.index('pRmApi->Free')
assert destroy.index('_nvGpuOpsDynBar1Drain')<destroy.index('nvGpuOpsFindAndDestroyP2pInfo')<destroy.index('pRmApi->Free')
uvm=a.source/'kernel-open/nvidia-uvm';enable=extract((uvm/'uvm_va_space.c').read_text(),'enable_peers')
assert enable.index('uvm_parent_gpus_are_dynamic_bar1_peers')<enable.index('processor_mask_array_set(va_space->can_access')
assert '__set_bit(pair_index, va_space->enabled_peers);\n        return NV_OK;' in enable
for name in ('uvm_mmu_create_peer_identity_mappings','uvm_mmu_destroy_peer_identity_mappings'):
 assert 'uvm_parent_gpus_are_dynamic_bar1_peers' in extract((uvm/'uvm_mmu.c').read_text(),name)
external=(uvm/'uvm_map_external.c').read_text();assert 'nv_kref_put(&ext_gpu_map->mem_handle->ref_count, uvm_release_rm_handle)' in external
assert 'uvm_tracker_wait_deinit(&ext_gpu_map->tracker)' in external
print('PASS integration ordering: managed/HMM masks excluded, identity mappings skipped, UVM refcount/tracker cleanup retained')

with tempfile.TemporaryDirectory() as temp:
 c=Path(temp)/'uvm.c';exe=Path(temp)/'uvm'
 template=Path(__file__).with_name('dynamic_uvm_fixture.c').read_text()
 c.write_text(template.replace('/* ACTUAL_ENABLE_PEERS */', enable))
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(c),'-o',str(exe)],check=True)
 if not a.compile_only: subprocess.run([exe],check=True)
 else: print('PASS fixture compilation only; runtime assertions not executed')
