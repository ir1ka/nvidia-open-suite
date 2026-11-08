// Explicit VMM peer mappings: no cudaDeviceReset and no whole-device peer enable.
#include <cuda.h>
#include <cuda_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <vector>
#include <random>
#include <chrono>
#include <unistd.h>
#define RT(x) do {cudaError_t e=(x);if(e!=cudaSuccess){fprintf(stderr,"RT %s:%d %s: %s\n",__FILE__,__LINE__,#x,cudaGetErrorString(e));exit(2);}}while(0)
#define DR(x) do {CUresult e=(x);if(e!=CUDA_SUCCESS){const char*n=nullptr,*s=nullptr;cuGetErrorName(e,&n);cuGetErrorString(e,&s);fprintf(stderr,"DR %s:%d %s: %s %s\n",__FILE__,__LINE__,#x,n?n:"?",s?s:"?");exit(3);}}while(0)
struct Buffer {CUdeviceptr ptr=0;CUmemGenericAllocationHandle handle=0;size_t size=0;int owner=0;};
static Buffer alloc(int owner,size_t bytes){
 RT(cudaSetDevice(owner));Buffer b;b.owner=owner;
 CUmemAllocationProp prop={};prop.type=CU_MEM_ALLOCATION_TYPE_PINNED;prop.location.type=CU_MEM_LOCATION_TYPE_DEVICE;prop.location.id=owner;
 size_t gran;DR(cuMemGetAllocationGranularity(&gran,&prop,CU_MEM_ALLOC_GRANULARITY_MINIMUM));b.size=(bytes+gran-1)/gran*gran;
 DR(cuMemCreate(&b.handle,b.size,&prop,0));DR(cuMemAddressReserve(&b.ptr,b.size,0,0,0));DR(cuMemMap(b.ptr,b.size,0,b.handle,0));
 CUmemAccessDesc access={};access.location=prop.location;access.flags=CU_MEM_ACCESS_FLAGS_PROT_READWRITE;DR(cuMemSetAccess(b.ptr,b.size,&access,1));return b;
}
static CUresult share(Buffer &b,int peer){RT(cudaSetDevice(b.owner));CUmemAccessDesc access={};access.location.type=CU_MEM_LOCATION_TYPE_DEVICE;access.location.id=peer;access.flags=CU_MEM_ACCESS_FLAGS_PROT_READWRITE;return cuMemSetAccess(b.ptr,b.size,&access,1);}
static void release(Buffer&b){RT(cudaSetDevice(b.owner));DR(cuMemUnmap(b.ptr,b.size));DR(cuMemAddressFree(b.ptr,b.size));DR(cuMemRelease(b.handle));b.ptr=0;}
__global__ void fill(uint32_t*p,size_t n,uint32_t seed){for(size_t i=blockIdx.x*blockDim.x+threadIdx.x;i<n;i+=gridDim.x*blockDim.x)p[i]=uint32_t(i)*2654435761u^seed;}
__global__ void read_peer(uint32_t*out,const uint32_t*in,size_t n){for(size_t i=blockIdx.x*blockDim.x+threadIdx.x;i<n;i+=gridDim.x*blockDim.x)out[i]=in[i];}
__device__ unsigned long long timer(){unsigned long long t;asm volatile("mov.u64 %0, %%globaltimer;":"=l"(t));return t;}
__global__ void ping(volatile uint32_t*local,volatile uint32_t*peer,unsigned n,bool initiator,unsigned long long*result){
 if(threadIdx.x||blockIdx.x)return;const unsigned long long timeout=2000000000ULL;unsigned long long t0=timer();
 if(!initiator){peer[1]=1;__threadfence_system();}
 else {while(local[1]!=1){if(timer()-t0>timeout){result[1]=1;return;}}}
 unsigned long long start=timer();
 for(unsigned k=1;k<=n;k++){
  if(initiator){peer[0]=k;__threadfence_system();while(local[0]!=k){if(timer()-t0>timeout){result[1]=2;return;}}}
  else {while(local[0]!=k){if(timer()-t0>timeout){result[1]=3;return;}}peer[0]=k;__threadfence_system();}
 }
 result[0]=timer()-start;result[1]=0;
}
static int by_bdf(const char*bdf){int n;RT(cudaGetDeviceCount(&n));for(int i=0;i<n;i++){char b[32];RT(cudaDeviceGetPCIBusId(b,sizeof b,i));if(!strcasecmp(b,bdf))return i;}fprintf(stderr,"No device %s\n",bdf);exit(4);}
static void verify(int gpu,uint32_t*out,size_t words,uint32_t seed){RT(cudaSetDevice(gpu));std::vector<uint32_t>host(words);RT(cudaMemcpy(host.data(),out,words*4,cudaMemcpyDeviceToHost));for(size_t i=0;i<words;i++)if(host[i]!=(uint32_t(i)*2654435761u^seed)){fprintf(stderr,"MISMATCH gpu=%d word=%zu got=%08x\n",gpu,i,host[i]);exit(5);}}
static double elapsed(cudaEvent_t start,cudaEvent_t end){RT(cudaEventSynchronize(end));float ms;RT(cudaEventElapsedTime(&ms,start,end));return ms;}
int main(int argc,char**argv){
 setbuf(stdout,nullptr);if(argc<4){fprintf(stderr,"usage: %s BDF_A BDF_B bench|exhaust|exit|hold|active|managed|legacy|stress [MiB=32] [pressureMiB=512]\n",argv[0]);return 1;}
 DR(cuInit(0));int gpu[2]={by_bdf(argv[1]),by_bdf(argv[2])};size_t bytes=(argc>4?strtoull(argv[4],nullptr,0):32)*(1ULL<<20);size_t pressure=(argc>5?strtoull(argv[5],nullptr,0):512)*(1ULL<<20);const char*mode=argv[3];
 if(!strcmp(mode,"legacy"))pressure=0;
 void*localPressure[2]={};uint32_t*out[2]={};cudaStream_t stream[2];cudaEvent_t start[2],end[2];
 for(int i=0;i<2;i++){
  RT(cudaSetDevice(gpu[i]));cudaDeviceProp prop;RT(cudaGetDeviceProperties(&prop,gpu[i]));int can=0;RT(cudaDeviceCanAccessPeer(&can,gpu[i],gpu[1-i]));printf("GPU %d %s peer=%d memory=%zu\n",gpu[i],prop.name,can,prop.totalGlobalMem);
  if(!can){fprintf(stderr,"Peer capability absent\n");return 6;}
  if(pressure){RT(cudaMalloc(&localPressure[i],pressure));RT(cudaMemset(localPressure[i],0x5a,pressure));}
  RT(cudaMalloc(&out[i],bytes));RT(cudaStreamCreateWithFlags(&stream[i],cudaStreamNonBlocking));RT(cudaEventCreate(&start[i]));RT(cudaEventCreate(&end[i]));
 }
 if(!strcmp(mode,"stress")){
  const unsigned seed=argc>6?strtoul(argv[6],nullptr,0):1;
  const unsigned steps=argc>7?strtoul(argv[7],nullptr,0):500;
  std::mt19937 rng(seed);
  struct Slot {Buffer b;uint32_t pattern;int owner_index;};
  std::vector<Slot> slots;unsigned maps=0,oom=0,checks=0,writes=0,frees=0;
  printf("STRESS_START seed=%u steps=%u pid=%d\n",seed,steps,getpid());
  for(unsigned step=0;step<steps;step++){
   const unsigned op=rng()%100;
   if(slots.empty()||op<45){
    int i=rng()%2;size_t n=(2ULL<<(rng()%6))<<20;if(n>bytes)n=bytes;
    Slot slot{alloc(gpu[i],n),uint32_t(rng()),i};CUresult shareStatus=share(slot.b,gpu[1-i]);
    if(shareStatus==CUDA_ERROR_OUT_OF_MEMORY){release(slot.b);oom++;}
    else {DR(shareStatus);RT(cudaSetDevice(gpu[i]));fill<<<256,256>>>((uint32_t*)slot.b.ptr,n/4,slot.pattern);RT(cudaDeviceSynchronize());slots.push_back(slot);maps++;}
   }
   else if(op<65){unsigned j=rng()%slots.size();release(slots[j].b);slots.erase(slots.begin()+j);frees++;}
   else {
    Slot &slot=slots[rng()%slots.size()];int i=slot.owner_index;size_t n=slot.b.size;
    if(op>=85){
     slot.pattern=rng();RT(cudaSetDevice(gpu[1-i]));fill<<<256,256>>>((uint32_t*)slot.b.ptr,n/4,slot.pattern);RT(cudaDeviceSynchronize());
     RT(cudaSetDevice(gpu[i]));read_peer<<<256,256>>>(out[i],(uint32_t*)slot.b.ptr,n/4);RT(cudaDeviceSynchronize());verify(gpu[i],out[i],n/4,slot.pattern);writes++;
    }else{
     RT(cudaSetDevice(gpu[1-i]));
     if(op&1)read_peer<<<256,256>>>(out[1-i],(uint32_t*)slot.b.ptr,n/4);
     else RT(cudaMemcpyAsync(out[1-i],(void*)slot.b.ptr,n,cudaMemcpyDefault,stream[1-i]));
     RT(cudaDeviceSynchronize());verify(gpu[1-i],out[1-i],n/4,slot.pattern);
    }
    checks++;
   }
   if(step%50==0)printf("STRESS_PROGRESS seed=%u step=%u live=%zu maps=%u oom=%u checks=%u writes=%u frees=%u\n",seed,step,slots.size(),maps,oom,checks,writes,frees);
  }
  for(auto &slot:slots)release(slot.b);
  printf("PASS STRESS seed=%u steps=%u maps=%u oom=%u checks=%u writes=%u frees=%u\n",seed,steps,maps,oom,checks,writes,frees);
  return 0;
 }
 if(!strcmp(mode,"legacy")){
  uint32_t*src[2];
  for(int i=0;i<2;i++){RT(cudaSetDevice(gpu[i]));RT(cudaMalloc(&src[i],bytes));fill<<<256,256>>>(src[i],bytes/4,800+i);RT(cudaDeviceSynchronize());}
  for(int i=0;i<2;i++){RT(cudaSetDevice(gpu[i]));RT(cudaDeviceEnablePeerAccess(gpu[1-i],0));read_peer<<<256,256>>>(out[i],src[1-i],bytes/4);RT(cudaDeviceSynchronize());verify(gpu[i],out[i],bytes/4,801-i);}
  puts("PASS legacy cudaMalloc/cudaDeviceEnablePeerAccess both directions; exit without reset");return 0;
 }
 if(!strcmp(mode,"exhaust")){
  std::vector<Buffer> buffers;bool failed=false;
  for(unsigned i=0;i<64;i++){
   Buffer b=alloc(gpu[0],bytes);CUresult e=share(b,gpu[1]);
   if(e!=CUDA_SUCCESS){const char*n=nullptr;cuGetErrorName(e,&n);printf("EXPECTED_EXHAUST mapped=%zu bytes=%zu error=%d name=%s\n",buffers.size(),buffers.size()*bytes,int(e),n?n:"?");release(b);failed=true;break;}
   buffers.push_back(b);
  }
  if(!failed){fprintf(stderr,"No exhaustion within test cap\n");return 7;}
  for(auto&b:buffers)release(b);
  Buffer b=alloc(gpu[0],bytes);DR(share(b,gpu[1]));RT(cudaSetDevice(gpu[0]));fill<<<128,256>>>((uint32_t*)b.ptr,bytes/4,77);RT(cudaDeviceSynchronize());RT(cudaSetDevice(gpu[1]));read_peer<<<128,256>>>(out[1],(uint32_t*)b.ptr,bytes/4);RT(cudaDeviceSynchronize());verify(gpu[1],out[1],bytes/4,77);release(b);printf("PASS budget recovered after exhaustion\n");return 0;
 }
 Buffer b[2];for(int i=0;i<2;i++){b[i]=alloc(gpu[i],bytes);DR(share(b[i],gpu[1-i]));RT(cudaSetDevice(gpu[i]));fill<<<256,256>>>((uint32_t*)b[i].ptr,bytes/4,123+i);RT(cudaDeviceSynchronize());}
 for(int i=0;i<2;i++){RT(cudaSetDevice(gpu[i]));read_peer<<<256,256>>>(out[i],(uint32_t*)b[1-i].ptr,bytes/4);RT(cudaDeviceSynchronize());verify(gpu[i],out[i],bytes/4,124-i);}
 printf("PASS direct SM peer read, all %zu bytes verified both directions, local pressure=%zu bytes per GPU\n",bytes,pressure);
 if(!strcmp(mode,"managed")){
  uint32_t*um=nullptr;RT(cudaSetDevice(gpu[0]));RT(cudaMallocManaged(&um,bytes));
  for(int i=0;i<2;i++){RT(cudaSetDevice(gpu[i]));fill<<<256,256>>>(um,bytes/4,999+i);RT(cudaDeviceSynchronize());RT(cudaSetDevice(gpu[1-i]));read_peer<<<256,256>>>(out[1-i],um,bytes/4);RT(cudaDeviceSynchronize());verify(gpu[1-i],out[1-i],bytes/4,999+i);}
  RT(cudaFree(um));puts("PASS managed allocation migration/fallback data correctness (not direct P2P claim)");return 0;
 }
 if(!strcmp(mode,"exit")){printf("EXIT_WITH_LIVE_WINDOWS no explicit free/reset\n");return 0;}
 if(!strcmp(mode,"hold")){printf("READY_KILL pid=%d\n",getpid());for(;;)pause();}
 if(!strcmp(mode,"active")){printf("READY_KILL_ACTIVE pid=%d\n",getpid());for(;;){for(int i=0;i<2;i++){RT(cudaSetDevice(gpu[i]));read_peer<<<256,256,0,stream[i]>>>(out[i],(uint32_t*)b[1-i].ptr,bytes/4);RT(cudaStreamSynchronize(stream[i]));}}}
 const int repeats=64;
 for(int engine=0;engine<2;engine++){
  for(int i=0;i<2;i++){
   RT(cudaSetDevice(gpu[i]));RT(cudaEventRecord(start[i],stream[i]));for(int j=0;j<repeats;j++){if(!engine)read_peer<<<256,256,0,stream[i]>>>(out[i],(uint32_t*)b[1-i].ptr,bytes/4);else RT(cudaMemcpyAsync(out[i],(void*)b[1-i].ptr,bytes,cudaMemcpyDefault,stream[i]));}RT(cudaEventRecord(end[i],stream[i]));double ms=elapsed(start[i],end[i]);printf("BW %s %d->%d %.3f GB/s (%zu bytes x %d, %.3f ms)\n",engine?"CE":"SM-read",gpu[1-i],gpu[i],bytes*repeats/ms/1e6,bytes,repeats,ms);verify(gpu[i],out[i],bytes/4,124-i);
  }
  auto before=std::chrono::steady_clock::now();
  for(int j=0;j<repeats;j++)for(int i=0;i<2;i++){RT(cudaSetDevice(gpu[i]));if(!engine)read_peer<<<256,256,0,stream[i]>>>(out[i],(uint32_t*)b[1-i].ptr,bytes/4);else RT(cudaMemcpyAsync(out[i],(void*)b[1-i].ptr,bytes,cudaMemcpyDefault,stream[i]));}
  for(int i=0;i<2;i++){RT(cudaSetDevice(gpu[i]));RT(cudaStreamSynchronize(stream[i]));}
  // Include host submission, exclude validation from concurrent transfer timing.
  double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-before).count();printf("BIDIR %s aggregate %.3f GB/s\n",engine?"CE":"SM-read",2.*bytes*repeats/ms/1e6);
  for(int i=0;i<2;i++)verify(gpu[i],out[i],bytes/4,124-i);
 }
 // Bounded single-thread ping-pong using loads/stores, not remote atomics.
 Buffer flags[2];unsigned long long*result[2];
 for(int i=0;i<2;i++){flags[i]=alloc(gpu[i],65536);DR(share(flags[i],gpu[1-i]));RT(cudaSetDevice(gpu[i]));RT(cudaMemset((void*)flags[i].ptr,0,65536));RT(cudaMalloc(&result[i],16));RT(cudaMemset(result[i],0,16));RT(cudaDeviceSynchronize());}
 for(int i=1;i>=0;i--){RT(cudaSetDevice(gpu[i]));ping<<<1,1,0,stream[i]>>>((volatile uint32_t*)flags[i].ptr,(volatile uint32_t*)flags[1-i].ptr,1000,i==0,result[i]);}
 for(int i=0;i<2;i++){RT(cudaSetDevice(gpu[i]));RT(cudaStreamSynchronize(stream[i]));unsigned long long h[2];RT(cudaMemcpy(h,result[i],16,cudaMemcpyDeviceToHost));printf("LATENCY gpu=%d total_ns=%llu status=%llu RTT_us=%.3f half_RTT_us=%.3f\n",gpu[i],h[0],h[1],h[0]/1000./1000.,h[0]/1000./2000.);if(h[1])return 8;}
 for(int i=0;i<2;i++){release(flags[i]);release(b[i]);RT(cudaSetDevice(gpu[i]));RT(cudaFree(result[i]));RT(cudaFree(out[i]));if(localPressure[i])RT(cudaFree(localPressure[i]));RT(cudaStreamDestroy(stream[i]));RT(cudaEventDestroy(start[i]));RT(cudaEventDestroy(end[i]));}
 puts("PASS normal cleanup without cudaDeviceReset");return 0;
}
