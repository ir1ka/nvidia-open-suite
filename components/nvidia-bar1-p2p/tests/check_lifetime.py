#!/usr/bin/python3
"""Compile actual IOVAS linked-list/drain code against lifetime mocks."""
from pathlib import Path
import argparse,re,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);a=p.parse_args()
s=(a.source/'src/nvidia/src/kernel/mem_mgr/io_vaspace.c').read_text()
def extract(name):
 m=re.search(r'(?:static )?void\n'+re.escape(name)+r'\s*\(',s)
 if not m:raise ValueError(name)
 brace=s.index('{',m.end());end=brace+1;depth=1
 while depth:depth+=(s[end]=='{')-(s[end]=='}');end+=1
 return s[m.start():end]+'\n'
pre=r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
typedef uint32_t NvU32;typedef uint64_t NvU64;
#define RMCFG_FEATURE_PLATFORM_UNIX 1
#define RMCFG_FEATURE_MODS_FEATURES 0
#define NVCPU_IS_ARM 0
#define NV_ASSERT assert
#define NV_PRINTF(...) ((void)0)
#define LEVEL_ERROR 1
typedef struct OBJGPU{unsigned eligible;struct{unsigned iovaspaceId;}busInfo;}OBJGPU;
#define GPU_GET_KERNEL_BUS(g) ((void*)(g))
static int kbusFullBar1P2PEligible(OBJGPU*g,void*b){(void)b;return g && g->eligible==1;}
static int kbusDynamicBar1P2PEligible(OBJGPU*g){return g && g->eligible==2;}
struct IOVAMAPPING;
typedef struct {struct IOVAMAPPING*maps;NvU64 Size;int pages_alive;}MEMORY_DESCRIPTOR,*PMEMORY_DESCRIPTOR;
typedef struct IOVAMAPPING{unsigned iovaspaceId,refcount;PMEMORY_DESCRIPTOR pPhysMemDesc;union{struct IOVAMAPPING*pParent,*pChildren;}link;struct IOVAMAPPING*pNext,*pFullBar1VasPrev,*pFullBar1VasNext;}IOVAMAPPING,*PIOVAMAPPING;
typedef struct{NvU64 mappingCount;PIOVAMAPPING pFullBar1RootMappings;}OBJIOVASPACE;
static OBJIOVASPACE vas[2];static unsigned unmapped[2];static int dma_identity_alive[2]={1,1};
static OBJIOVASPACE*iovaspaceFromId(unsigned id){return id<2?&vas[id]:NULL;}
static void memdescRemoveIommuMap(PMEMORY_DESCRIPTOR md,PIOVAMAPPING map){
 PIOVAMAPPING*p=&md->maps;while(*p&&*p!=map)p=&(*p)->pNext;assert(*p==map);*p=map->pNext;
}
#define portMemFree free
static void osIovaUnmap(PIOVAMAPPING m){assert(dma_identity_alive[m->iovaspaceId]);assert(m->pPhysMemDesc->pages_alive);unmapped[m->iovaspaceId]++;}
static void iovaspaceReleaseMapping(OBJIOVASPACE*v,PIOVAMAPPING m){(void)v;assert(m->refcount>1);m->refcount--;}
static void iovaspaceDestroyMapping(OBJIOVASPACE*v,PIOVAMAPPING m);
'''
main=r'''
static void iovaspaceDestroyMapping(OBJIOVASPACE*v,PIOVAMAPPING m){_iovaspaceDestroyRootMapping(v,m);}
static PIOVAMAPPING add(OBJGPU*g,PMEMORY_DESCRIPTOR md){
 PIOVAMAPPING m=calloc(1,sizeof(*m));m->refcount=1;m->iovaspaceId=g->busInfo.iovaspaceId;m->pPhysMemDesc=md;m->pNext=md->maps;md->maps=m;
 vas[m->iovaspaceId].mappingCount++;_iovaspaceTrackFullBar1Root(&vas[m->iovaspaceId],m,g);return m;
}
int main(void){
 OBJGPU gpu[2]={{.eligible=1,.busInfo={0}},{.eligible=1,.busInfo={1}}};
 MEMORY_DESCRIPTOR shared={.Size=0x200000,.pages_alive=1},extra={.Size=0x200000,.pages_alive=1},child={.Size=0x1000,.pages_alive=1};
 MEMORY_DESCRIPTOR native={.Size=4096,.pages_alive=1};
 gpu[0].eligible=0;PIOVAMAPPING nativeMap=add(&gpu[0],&native);gpu[0].eligible=1;
 PIOVAMAPPING a=add(&gpu[0],&shared),other=add(&gpu[1],&shared),middle=add(&gpu[0],&extra),head=add(&gpu[0],&extra);
 iovaspaceDestroyMapping(&vas[0],middle);assert(head->pFullBar1VasNext==a&&a->pFullBar1VasPrev==head);
 PIOVAMAPPING c=calloc(1,sizeof(*c));c->iovaspaceId=0;c->refcount=1;c->pPhysMemDesc=&child;c->link.pParent=a;child.maps=c;a->link.pChildren=c;a->refcount++;vas[0].mappingCount++;
 iovaspaceDrainFullBar1Mappings(&gpu[0]);
 assert(!vas[0].pFullBar1RootMappings&&vas[0].mappingCount==1&&unmapped[0]==3);
 assert(native.maps==nativeMap);iovaspaceDestroyMapping(&vas[0],nativeMap);assert(vas[0].mappingCount==0&&unmapped[0]==4);
 assert(shared.maps==other&&extra.maps==NULL&&child.maps==NULL&&shared.pages_alive);
 assert(vas[1].mappingCount==1&&vas[1].pFullBar1RootMappings==other&&unmapped[1]==0);
 dma_identity_alive[0]=0;iovaspaceDrainFullBar1Mappings(&gpu[0]);assert(unmapped[0]==4);
 iovaspaceDrainFullBar1Mappings(&gpu[1]);assert(vas[1].mappingCount==0&&shared.maps==NULL&&unmapped[1]==1);
 puts("PASS scoped drain, root/children detached, other GPU and untracked native maps preserved, DMA unmap before identity loss, idempotence");
 gpu[0].eligible=0;dma_identity_alive[0]=1;
 PIOVAMAPPING skipped=add(&gpu[0],&shared);assert(!vas[0].pFullBar1RootMappings);
 iovaspaceDrainFullBar1Mappings(&gpu[0]);assert(shared.maps==skipped&&vas[0].mappingCount==1);
 iovaspaceDestroyMapping(&vas[0],skipped);
 puts("PASS ineligible maps remain outside the extension tracker");
 gpu[0].eligible=2;PIOVAMAPPING dynamic=add(&gpu[0],&shared);
 assert(vas[0].pFullBar1RootMappings==dynamic);
 iovaspaceDrainFullBar1Mappings(&gpu[0]);assert(!vas[0].mappingCount&&!shared.maps);
 puts("PASS dynamic small-BAR eligible mappings participate in teardown drain");
 return 0;
}
'''
functions=''.join(extract(n)for n in ('_iovaspaceTrackFullBar1Root','_iovaspaceUntrackFullBar1Root','_iovaspaceDestroySubmapping','_iovaspaceDestroyRootMapping','iovaspaceDrainFullBar1Mappings'))
with tempfile.TemporaryDirectory()as t:
 c=Path(t)/'lifetime.c';b=Path(t)/'lifetime';c.write_text(pre+functions+main)
 subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror',str(c),'-o',str(b)],check=True)
 subprocess.run([str(b)],check=True)
