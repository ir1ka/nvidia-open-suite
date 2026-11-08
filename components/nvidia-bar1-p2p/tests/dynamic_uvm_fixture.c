/* Host fixture for the actual enable_peers implementation, not a GPU test. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef int NV_STATUS;
typedef unsigned NvU32;
#define NV_OK 0
#define NV_ERR_INVALID_DEVICE 1
#define UVM_GPU_PEER_COPY_MODE_UNSUPPORTED 0
#define UVM_GPU_LINK_NVLINK_1 2
#define UVM_ASSERT assert
#define UVM_ASSERT_MSG(x,...) assert(x)
#define LIST_HEAD(x) int x=0
#define uvm_assert_rwsem_locked_write(x) ((void)(x))
typedef struct {unsigned bits;} mask;
typedef struct {int peer_copy_mode;bool dynamic;}parent;
typedef struct {parent*parent;unsigned id;}uvm_gpu_t;
typedef int uvm_va_range_t;
typedef struct {int lock;mask registered_gpus;unsigned long enabled_peers[1];
 mask can_access[4],accessible_from[4],can_copy_from[4],has_native_atomics[4],has_fast_link[4];}uvm_va_space_t;
static unsigned managed_calls;
static bool uvm_processor_mask_test(mask*m,unsigned id){return !!(m->bits&(1u<<id));}
static unsigned uvm_gpu_pair_index(unsigned a,unsigned b){return a+b;}
static bool test_bit(unsigned b,unsigned long*p){return (*p&(1UL<<b))!=0;}
static void __set_bit(unsigned b,unsigned long*p){*p|=1UL<<b;}
static bool uvm_parent_gpus_are_dynamic_bar1_peers(parent*a,parent*b){return a->dynamic&&b->dynamic;}
static void processor_mask_array_set(mask*m,unsigned a,unsigned b){m[a].bits|=1u<<b;}
static bool uvm_gpus_are_smc_peers(uvm_gpu_t*a,uvm_gpu_t*b){(void)a;(void)b;return false;}
static int uvm_parent_gpu_peer_link_type(parent*a,parent*b){(void)a;(void)b;return 1;}
static void enable_egm_peers(uvm_va_space_t*v,uvm_gpu_t*a,uvm_gpu_t*b){(void)v;(void)a;(void)b;managed_calls++;}
static bool va_space_check_processors_masks(uvm_va_space_t*v){(void)v;return true;}
#define uvm_for_each_va_range(r,v) for((r)=NULL;(r)!=NULL;)
static int uvm_va_range_enable_peer(uvm_va_range_t*r,uvm_gpu_t*a,uvm_gpu_t*b){(void)r;(void)a;(void)b;managed_calls++;return 0;}
static void disable_peers(uvm_va_space_t*v,uvm_gpu_t*a,uvm_gpu_t*b,int*l){(void)v;(void)a;(void)b;(void)l;}
static bool list_empty(int*l){return *l==0;}
/* ACTUAL_ENABLE_PEERS */
int main(void){
 parent parents[2]={{1,true},{1,true}};uvm_gpu_t a={parents,1},b={parents+1,2};
 uvm_va_space_t v={.registered_gpus={6}};
 assert(enable_peers(&v,&a,&b)==NV_OK);
 assert(test_bit(3,v.enabled_peers)); /* External allocations see the pair. */
 assert(!v.can_access[1].bits&&!v.can_access[2].bits);
 assert(!v.accessible_from[1].bits&&!v.accessible_from[2].bits);
 assert(!v.can_copy_from[1].bits&&!v.can_copy_from[2].bits);
 assert(!v.has_native_atomics[1].bits&&!v.has_native_atomics[2].bits&&!managed_calls);
 /* Same source function retains native/full peer policy. */
 v=(uvm_va_space_t){.registered_gpus={6}};parents[0].dynamic=false;parents[1].dynamic=false;
 assert(enable_peers(&v,&a,&b)==NV_OK&&managed_calls==2);
 assert(v.can_access[1].bits==4&&v.can_access[2].bits==2);
 assert(v.accessible_from[1].bits==4&&v.accessible_from[2].bits==2);
 assert(v.can_copy_from[1].bits==4&&v.can_copy_from[2].bits==2);
 v=(uvm_va_space_t){.registered_gpus={2}};
 assert(enable_peers(&v,&a,&b)==NV_ERR_INVALID_DEVICE&&!v.enabled_peers[0]);
 puts("PASS actual UVM enable_peers: dynamic external pair enabled, managed/HMM/CE/atomic masks excluded, native/full masks retained, unregistered GPU rejected");
}
