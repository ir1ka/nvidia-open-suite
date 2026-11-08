#!/usr/bin/python3
"""Execute actual CMP unlock and native resize; assert PF is outside NVIDIA."""
import argparse,re,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=Path);a=p.parse_args();root=a.source/'kernel-open/nvidia';text=(root/'nv-pci.c').read_text()
def extract(name):
 m=re.search(r'static (?:void|int)\s+'+name+r'\s*\(',text);assert m,name
 pos=text.index('{',m.end())+1;end=pos;depth=1
 while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
 return text[m.start():end]+'\n'
pre=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <linux/pci_regs.h>
#define NV_PCI_REBAR_GET_POSSIBLE_SIZES_PRESENT 1
#ifndef TEST_OLD_RESIZE
#define NV_PCI_RESIZE_RESOURCE_HAS_EXCLUDE_BARS_ARG 1
#endif
#define NV_IS_EXPORT_SYMBOL_PRESENT_pci_find_host_bridge 1
#define __iomem
#define NV_GPU_BAR1 1
#define NV_GPU_BAR3 3
#define IORESOURCE_MEM 0x200
#define IORESOURCE_UNSET 0x20000000
static char trace_buffer[2048];
#define nv_printf(level,...) ((void)snprintf(trace_buffer,sizeof(trace_buffer),__VA_ARGS__))
#define NV_PCI_DOMAIN_NUMBER(d) 0
#define NV_PCI_BUS_NUMBER(d) 0
#define NV_PCI_SLOT_NUMBER(d) 0
#define PCI_FUNC(d) 0
typedef uint32_t u32;typedef uint16_t u16;typedef uint64_t resource_size_t;
struct pci_dev;struct pci_host_bridge{bool preserve_config;};
struct pci_bus{struct pci_dev*owner;struct pci_host_bridge host;};
struct pci_dev{unsigned device,devfn;uint64_t start[6],len[6],flags[6],limit;unsigned long sizes;struct pci_bus*bus;u16 command;bool fail_assign;};
static unsigned NVreg_EnableResizableBar,maps,reads,writes,unmaps,assigns,resizes,checks;
static u32 backing[1024];
static uint64_t pci_resource_start(struct pci_dev*d,int b){return d->start[b];}
static uint64_t pci_resource_len(struct pci_dev*d,int b){return d->len[b];}
static uint64_t pci_resource_flags(struct pci_dev*d,int b){return d->flags[b];}
static void*ioremap(uint64_t a,uint64_t b){maps++;return backing;}
static u32 readl(void*p){reads++;return *(u32*)p;}
static void writel(u32 v,void*p){writes++;*(u32*)p=v;}
static void iounmap(void*p){unmaps++;}
static int fls(unsigned long x){return x?64-__builtin_clzl(x):0;}
static void clear_bit(int n,unsigned long*p){*p&=~(1UL<<n);}
static unsigned long pci_rebar_get_possible_sizes(struct pci_dev*d,int b){return d->sizes;}
static int pci_rebar_bytes_to_size(uint64_t n){return __builtin_ctzll(n)-20;}
static struct pci_host_bridge*pci_find_host_bridge(struct pci_bus*b){return &b->host;}
static int pci_read_config_word(struct pci_dev*d,int o,u16*v){*v=d->command;return 0;}
static int pci_write_config_word(struct pci_dev*d,int o,u16 v){d->command=v;return 0;}
static void pci_release_resource(struct pci_dev*d,int b){d->flags[b]|=IORESOURCE_UNSET;}
static int pci_resize_resource(struct pci_dev*d,int b,int code
#ifdef NV_PCI_RESIZE_RESOURCE_HAS_EXCLUDE_BARS_ARG
,int exclude
#endif
){resizes++;uint64_t n=1ULL<<(code+20);if(n>d->limit)return -ENOSPC;d->len[b]=n;return 0;}
static void pci_assign_unassigned_bus_resources(struct pci_bus*b){assigns++;if(!b->owner->fail_assign){b->owner->flags[1]&=~IORESOURCE_UNSET;b->owner->flags[3]&=~IORESOURCE_UNSET;}}
#define T(x) do{checks++;if(!(x)){fprintf(stderr,"FAIL %u: %s\n",checks,#x);return 1;}}while(0)
static void reset(struct pci_dev*d,struct pci_bus*b){memset(d,0,sizeof(*d));memset(b,0,sizeof(*b));b->owner=d;d->bus=b;d->device=0x20c2;d->start[0]=0x10000000;d->len[0]=0x1000000;d->flags[0]=IORESOURCE_MEM;d->len[1]=1ULL<<28;d->len[3]=1ULL<<25;d->limit=1ULL<<36;d->sizes=(1UL<<8)|(1UL<<9)|(1UL<<10)|(1UL<<16);d->command=PCI_COMMAND_MEMORY;NVreg_EnableResizableBar=maps=reads=writes=unmaps=assigns=resizes=0;}
'''
main=r'''
int main(void){struct pci_dev d;struct pci_bus b;
 reset(&d,&b);d.device=0x20f1;nv_cmp_unlock_bar1_resize(&d);T(maps==0&&writes==0);T(nv_resize_pcie_bars(&d)==0);T(resizes==0);
 reset(&d,&b);d.len[0]=0x1000;nv_cmp_unlock_bar1_resize(&d);T(writes==0&&maps==0);
 reset(&d,&b);d.flags[0]|=IORESOURCE_UNSET;nv_cmp_unlock_bar1_resize(&d);T(writes==0&&maps==0);
 reset(&d,&b);d.start[0]=0;nv_cmp_unlock_bar1_resize(&d);T(writes==0&&maps==0);
 reset(&d,&b);nv_cmp_unlock_bar1_resize(&d);T(maps==1&&writes==2&&reads==6&&unmaps==1);T(backing[0x724/4]==0x30);T(backing[0xdcc/4]==0x8000000a);T(NVreg_EnableResizableBar==0);
 T(nv_resize_pcie_bars(&d)==0);T(d.len[1]==(1ULL<<36));T(assigns==1&&resizes==1);T(d.command==PCI_COMMAND_MEMORY);
 reset(&d,&b);d.device=0x2082;nv_cmp_unlock_bar1_resize(&d);T(writes==2);T(NVreg_EnableResizableBar==0);
 reset(&d,&b);d.limit=1ULL<<30;T(nv_resize_pcie_bars(&d)==0);T(d.len[1]==(1ULL<<30));T(resizes==2);T(assigns==1);T(d.command==PCI_COMMAND_MEMORY);
 reset(&d,&b);d.fail_assign=true;T(nv_resize_pcie_bars(&d)==-ENODEV);T(assigns==2);T(d.flags[1]&IORESOURCE_UNSET);T(d.command==PCI_COMMAND_MEMORY);
 reset(&d,&b);d.device=0x1e04;NVreg_EnableResizableBar=1;d.sizes=0;T(nv_resize_pcie_bars(&d)==0);T(assigns==0&&resizes==0);
 reset(&d,&b);b.host.preserve_config=true;T(nv_resize_pcie_bars(&d)==0);T(assigns==0&&resizes==0);
 reset(&d,&b);d.len[1]=1ULL<<36;T(nv_resize_pcie_bars(&d)==0);T(resizes==0&&assigns==0);
 printf("PASS %u actual CMP/native resize assertions: MMIO guards, no global ReBAR mutation, per-device resize, smaller-size fallback, assignment failure, small-BAR/no-ReBAR and firmware preservation\n",checks);return 0;}
'''
with tempfile.TemporaryDirectory()as tmp:
 c=Path(tmp)/'cmp.c';c.write_text(pre+extract('nv_cmp_unlock_bar1_resize')+extract('nv_resize_pcie_bars')+main)
 for old in [False,True]:
  exe=Path(tmp)/('old'if old else'new');subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter',*(['-DTEST_OLD_RESIZE']if old else[]),str(c),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
assert 'nv_pf_bar_'not in text
assert 'nv_pf_bar_'not in(root/'nv.c').read_text()
assert 'nv-pf-bar'not in(root/'nvidia-sources.Kbuild').read_text()
assert not(root/'pf').exists()and not(a.source/'pf-bar').exists()
probe=text[text.index('    num_probed_nv_devices++;'):]
assert probe.index('pci_enable_device(pci_dev)')<probe.index('nv_cmp_unlock_bar1_resize(pci_dev);')<probe.index('nv_resize_pcie_bars(pci_dev)')<probe.index('pci_set_master(pci_dev)')
assert 'NVreg_EnableResizableBar = 1;'not in text
print('PASS: NVIDIA has no PF recovery object, hook or PF source; CMP resize remains per-device inside native PCI probe')
