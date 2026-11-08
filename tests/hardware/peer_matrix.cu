// Read CUDA capability matrix; cross-architecture enable attempts allocate no buffers.
#include <cuda_runtime.h>
#include <cstdio>
#include <vector>
int main() {
    int count=0;
    cudaError_t status=cudaGetDeviceCount(&count);
    if(status!=cudaSuccess){fprintf(stderr,"%s\n",cudaGetErrorString(status));return 1;}
    std::vector<cudaDeviceProp> prop(count);
    std::vector<std::vector<char>> bdf(count,std::vector<char>(32));
    for(int i=0;i<count;i++) {
        if(cudaGetDeviceProperties(&prop[i],i)!=cudaSuccess ||
           cudaDeviceGetPCIBusId(bdf[i].data(),32,i)!=cudaSuccess)return 2;
        printf("GPU %d %s %s CC=%d.%d\n",i,bdf[i].data(),prop[i].name,prop[i].major,prop[i].minor);
    }
    for(int i=0;i<count;i++) for(int j=0;j<count;j++) if(i!=j) {
        int access=0,atomics=0;
        if(cudaDeviceCanAccessPeer(&access,i,j)!=cudaSuccess)return 3;
        if(cudaDeviceGetP2PAttribute(&atomics,cudaDevP2PAttrNativeAtomicSupported,i,j)!=cudaSuccess)return 4;
        printf("PAIR %s -> %s access=%d atomics=%d",bdf[i].data(),bdf[j].data(),access,atomics);
        if(prop[i].major!=prop[j].major) {
            if(cudaSetDevice(i)!=cudaSuccess)return 5;
            status=cudaDeviceEnablePeerAccess(j,0);
            printf(" enable=%d %s",int(status),cudaGetErrorName(status));
            if(status==cudaSuccess && cudaDeviceDisablePeerAccess(j)!=cudaSuccess)return 6;
            cudaGetLastError();
        }
        printf("\n");
    }
    return 0;
}
