# Manual GPU benchmarks (source-only)

These programs are kept in Git and source archives, not in either deb package.
They are not part of `make check` and never run during installation. CUDA toolkit
and an explicitly idle GPU host are required. Check both `nvidia-smi` and device
file users before testing; do not interrupt another workload. None of these
programs configures ACS, BAR sizes, modules, services, or GPU clocks.

## Suite tests

From the repository root:

```sh
mkdir -p build/hardware
nvcc -O2 -arch=sm_75 tests/hardware/dynamic_bar1.cu -lcuda -o build/hardware/dynamic_bar1
nvcc -O2 -arch=sm_75 tests/hardware/latency_breakdown.cu -lcuda -o build/hardware/latency_breakdown
nvcc -O2 tests/hardware/peer_matrix.cu -o build/hardware/peer_matrix
```

`sm_75` plus embedded PTX worked on the tested Turing/Ampere host. Adjust the
CUDA architecture target for other GPUs. Use actual PCI BDFs, not CUDA ordinal
assumptions:

```sh
build/hardware/peer_matrix
build/hardware/dynamic_bar1 0000:1a:00.0 0000:1b:00.0 bench 32 0
mkdir -p build/hardware/latency
build/hardware/latency_breakdown \
  0000:1a:00.0 0000:1b:00.0 0000:16:00.0 0000:17:00.0 24 \
  > build/hardware/latency/samples.csv
python3 tests/hardware/analyze_latency.py build/hardware/latency
```

The BDFs above are examples from the measurement host. Four distinct devices
are required; the first two form `pair0`, the remaining two `pair1`. Both
pairs must support P2P. The test does not enable whole-device peer access:
it uses explicit VMM peer mappings. Results preserve per-direction samples.
`RATE` is each measurement kernel's aggregate effective clock in MHz; `S`
records raw cycle differences. `CLOCK` is warmup clock calibration, not the
conversion used for final samples. `DEVICE` records BDF-to-CUDA mappings.
The analyzer rejects incomplete runs, drops rounds 0 and 1, and reports pooled
percentiles and the range of per-round medians. Each kernel already drops its
first 128 operations. These are descriptive distributions, not confidence
intervals from independent samples.

The load test uses dependent `ld.global.cv.u32` loads and consumes the result
before its end timestamp. Store-issue timing is **not remote completion**.
Empty-system-fence and store-plus-fence timings include instrumentation and
cannot be subtracted from RTT to derive physical wire latency. No cross-GPU
clock synchronization is assumed. Both ping-pong participants have bounded
waits, and cleanup does not call `cudaDeviceReset`.

For clock telemetry, run the following in a separate terminal while measuring
and stop it when the test finishes:

```sh
nvidia-smi --query-gpu=timestamp,pci.bus_id,pstate,clocks.sm,clocks.mem,temperature.gpu,power.draw,utilization.gpu --format=csv -lms 100 > build/hardware/clocks.csv
```

To reproduce the documented **PCIe-only RTX** measurements, the driver was
loaded temporarily with `NVreg_NvLinkDisable=1 NVreg_RMDynamicBar1P2P=1`, after
confirming the host was idle and stopping its persistence service. A100 retained
full BAR1; RTX retained its 256 MiB BAR1. Do not mistake NVLink transfers for
PCIe transfers: record `nvidia-smi topo -m` and module parameters. Restore default
module parameters and original service state after testing. The programs do not
perform driver unload/reload automatically.

## NVIDIA CUDA Samples

Use the unmodified v12.8 release and its Common headers; do not copy upstream
source or binaries into this repository or a deb. For example, after extracting
the official tag archive into `/path/to/cuda-samples-12.8`:

```sh
nvcc -O2 -arch=sm_75 -I/path/to/cuda-samples-12.8/Common \
  /path/to/cuda-samples-12.8/Samples/5_Domain_Specific/p2pBandwidthLatencyTest/p2pBandwidthLatencyTest.cu \
  -o build/hardware/p2pBandwidthLatencyTest
CUDA_VISIBLE_DEVICES=GPU-uuid-a,GPU-uuid-b \
  build/hardware/p2pBandwidthLatencyTest --numElems=8388608
CUDA_VISIBLE_DEVICES=GPU-uuid-a,GPU-uuid-b \
  build/hardware/p2pBandwidthLatencyTest --numElems=8388608 --p2p_read
```

Replace UUID placeholders with `nvidia-smi -L` values. Confirm output identifies
the intended pair and reports access in both directions. `--p2p_read` adds read
matrices but still prints the write and bidirectional tests. Do not double-count
those when aggregating modes. Exclude diagonal and P2P-disabled cells when
reporting direct inter-GPU P2P. Record the sample's Boost warning and run-to-run
ranges. It does not measure the same latency as GPU ping-pong.

The measured results, environment, counts, and limitations are in the root
README. The small-bandwidth and stress program also supports explicit budget,
normal-exit, and active-exit scenarios; inspect its usage and run_stress.py before
using them. Those scenarios are not automatically run by these commands.

For the documented ten-round experiment, save output as
`A100-write-00.log` … `A100-write-09.log`, and likewise for `A100-read`,
`2080Ti-write`, and `2080Ti-read`. Run
`python3 tests/hardware/summarize_cuda_samples.py LOG_DIRECTORY`. It discards
rounds 00/01, requires eight retained observations per matrix cell, excludes
duplicate write matrices from read-mode runs, and writes `summary.json`.
Matrix cell labels refer to the printed row/column; read and write mode reverse
the data-transfer direction for a given initiating device.
