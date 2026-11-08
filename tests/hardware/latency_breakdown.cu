// Opt-in hardware diagnostic; reuses explicit VMM mappings and cleanup helpers.
#define main existing_dynamic_main
#include "dynamic_bar1.cu"
#undef main
#include <cerrno>
constexpr int N=2048, DROP=128;
__global__ void warm(unsigned long long *r){
 unsigned long long t=timer(),c=clock64();volatile float x=threadIdx.x+1;
 while(timer()-t<200000000ULL){for(int j=0;j<64;j++)x=x*1.000001f+0.000001f;}
 if(!blockIdx.x&&!threadIdx.x){r[0]=timer()-t;r[1]=clock64()-c;}
}
__global__ void chain(uint32_t*p){for(unsigned i=threadIdx.x+blockIdx.x*blockDim.x;i<65536;i+=blockDim.x*gridDim.x)p[i*16]=((i+8191)&65535)*16;}
__global__ void micro(uint32_t*p,int mode,unsigned long long*out){
 unsigned long long t0=timer(),c0=clock64();
 unsigned idx=0;for(int i=0;i<N;i++){
  unsigned long long a=clock64();
  if(mode==1)asm volatile("ld.global.cv.u32 %0, [%1];":"=r"(idx):"l"(p+idx):"memory");
  if(mode==1 && idx==0xffffffffu){out[N]=idx;return;} // Consume the load before reading the end timestamp.
  if(mode==2||mode==3){((volatile uint32_t*)p)[1048576+i]=i+1;}
  if(mode==3||mode==4)__threadfence_system();
  unsigned long long b=clock64();out[i]=b-a;
 }out[N]=idx;out[N+1]=clock64()-c0;out[N+2]=timer()-t0;
}
__global__ void rounds(volatile uint32_t*local,volatile uint32_t*peer,bool initiator,unsigned long long*out){
 unsigned long long deadline=timer()+3000000000ULL;
 if(!initiator){peer[1]=1;__threadfence_system();}
 else while(!local[1]){if(timer()>deadline){out[N]=1;return;}}
 unsigned long long t0=timer(),c0=clock64();
 for(unsigned i=1;i<=N;i++){
  unsigned long long a=clock64();
  if(initiator){peer[0]=i;__threadfence_system();while(local[0]!=i){if(timer()>deadline){out[N]=2;return;}}}
  else{while(local[0]!=i){if(timer()>deadline){out[N]=3;return;}}peer[0]=i;__threadfence_system();}
  out[i-1]=clock64()-a;
 }out[N]=0;out[N+1]=clock64()-c0;out[N+2]=timer()-t0;
}
static void emit(int round,const char*pair,int gpu,const char*metric,unsigned long long*d,bool ping=false){
 std::vector<unsigned long long>h(N+3);RT(cudaMemcpy(h.data(),d,h.size()*8,cudaMemcpyDeviceToHost));
 if(ping&&h[N]){fprintf(stderr,"ping timeout %llu\n",h[N]);exit(9);}
 printf("RATE,%d,%s,%d,%s,%.6f\n",round,pair,gpu,metric,h[N+1]*1000./h[N+2]);
 for(int i=DROP;i<N;i++)printf("S,%d,%s,%d,%s,%d,%llu\n",round,pair,gpu,metric,i,h[i]);
}
int main(int argc,char**argv){
 setbuf(stdout,nullptr);
 if(argc!=6){fprintf(stderr,"usage: %s PAIR0_BDF_A PAIR0_BDF_B PAIR1_BDF_A PAIR1_BDF_B ROUNDS\n",argv[0]);return 1;}
 char*end=nullptr;errno=0;long parsed=strtol(argv[5],&end,10);
 if(errno||!*argv[5]||*end||parsed<3||parsed>1000){fprintf(stderr,"ROUNDS must be 3..1000\n");return 1;}
 int count=int(parsed);DR(cuInit(0));int g[4];
 for(int k=0;k<4;k++){g[k]=by_bdf(argv[k+1]);for(int j=0;j<k;j++)if(g[k]==g[j]){fprintf(stderr,"Four distinct devices required\n");return 1;}
  printf("DEVICE,%d,%s,%d\n",k,argv[k+1],g[k]);}
 Buffer b[4],flags[4];unsigned long long*out[4];cudaStream_t s[4];
 for(int k=0;k<4;k++){RT(cudaSetDevice(g[k]));int can=0;RT(cudaDeviceCanAccessPeer(&can,g[k],g[k^1]));if(!can)return 6;
  b[k]=alloc(g[k],8<<20);DR(share(b[k],g[k^1]));flags[k]=alloc(g[k],65536);DR(share(flags[k],g[k^1]));
  chain<<<128,128>>>((uint32_t*)b[k].ptr);RT(cudaMalloc(&out[k],(N+3)*8));RT(cudaStreamCreate(&s[k]));RT(cudaDeviceSynchronize());}
 for(int r=0;r<count;r++)for(int order=0;order<2;order++){
  int base=2*((order+r)%2);const char*label=base?"pair1":"pair0";
  for(int k=base;k<base+2;k++){RT(cudaSetDevice(g[k]));warm<<<128,128,0,s[k]>>>(out[k]);}
  for(int k=base;k<base+2;k++){RT(cudaSetDevice(g[k]));RT(cudaStreamSynchronize(s[k]));unsigned long long h[2];RT(cudaMemcpy(h,out[k],16,cudaMemcpyDeviceToHost));printf("CLOCK,%d,%s,%d,%.3f\n",r,label,g[k],h[1]*1000./h[0]);}
  printf("PHASE,%d,%s,%lld\n",r,label,(long long)std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::system_clock::now().time_since_epoch()).count());
  for(int k=base;k<base+2;k++){
   RT(cudaSetDevice(g[k]));const char*names[]={"timer","read_cv","write_issue","write_fence","empty_fence"};
   for(int m=0;m<5;m++)for(int remote=0;remote<2;remote++){
    micro<<<1,1,0,s[k]>>>((uint32_t*)b[remote?(k^1):k].ptr,m,out[k]);RT(cudaStreamSynchronize(s[k]));
    char name[64];snprintf(name,sizeof name,"%s_%s",remote?"remote":"local",names[m]);emit(r,label,g[k],name,out[k]);
    if(m==1){unsigned long long idx;RT(cudaMemcpy(&idx,out[k]+N,8,cudaMemcpyDeviceToHost));if(idx!=((N*8191u)&65535)*16)return 10;}
    if(m==2||m==3){uint32_t v;RT(cudaMemcpy(&v,(uint32_t*)b[remote?(k^1):k].ptr+1048576+N-1,4,cudaMemcpyDeviceToHost));if(v!=N)return 11;}
   }
  }
  for(int initiator=base;initiator<base+2;initiator++){
   for(int k=base;k<base+2;k++){RT(cudaSetDevice(g[k]));RT(cudaMemset((void*)flags[k].ptr,0,65536));RT(cudaMemset(out[k],0,(N+3)*8));RT(cudaDeviceSynchronize());}
   for(int t=0;t<2;t++){int k=t?initiator:(initiator^1);RT(cudaSetDevice(g[k]));rounds<<<1,1,0,s[k]>>>((volatile uint32_t*)flags[k].ptr,(volatile uint32_t*)flags[k^1].ptr,k==initiator,out[k]);}
   for(int k=base;k<base+2;k++){RT(cudaSetDevice(g[k]));RT(cudaStreamSynchronize(s[k]));unsigned long long status;RT(cudaMemcpy(&status,out[k]+N,8,cudaMemcpyDeviceToHost));if(status){fprintf(stderr,"ping timeout %llu\n",status);return 9;}if(k==initiator)emit(r,label,g[k],"ping_rtt",out[k],true);}
  }
 }
 for(int k=0;k<4;k++){release(b[k]);release(flags[k]);RT(cudaSetDevice(g[k]));RT(cudaFree(out[k]));RT(cudaStreamDestroy(s[k]));}puts("PASS cleanup without reset");
}
