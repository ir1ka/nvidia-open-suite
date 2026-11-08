#!/usr/bin/env python3
"""Opt-in hardware stress only; no driver, BAR, ACS or persistent configuration writes.
Each pair runs two processes against the same target BAR1 budgets. Selected
children are SIGKILLed while the sibling continues. Only our child PIDs are killed.
"""
import argparse
import json
import random
import re
import signal
import subprocess
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--pair', action='append', required=True, help='label,BDF_A,BDF_B')
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--seed', type=int, default=20261108)
parser.add_argument('--rounds', type=int, default=6)
parser.add_argument('--steps', type=int, default=600)
parser.add_argument('--check-kernel-log', action='store_true', help='Read dmesg through sudo -n and stop on new kernel/GPU errors')
parser.add_argument('--kill', action='store_true', help='SIGKILL one child per pair on odd rounds')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
pairs = [pair.split(',') for pair in args.pair]
if any(len(pair) != 3 or not re.fullmatch(r'[a-zA-Z0-9_-]+', pair[0]) for pair in pairs):
    parser.error('pair must contain a safe label and two BDFs')
rng = random.Random(args.seed)
results = []
children = []
last_kernel_time = 0.0

def check_kernel(initial=False):
    global last_kernel_time
    if not args.check_kernel_log:
        return
    log = subprocess.check_output(['sudo', '-n', 'dmesg'], text=True, timeout=10)
    errors = []
    for line in log.splitlines():
        match = re.match(r'\[\s*([0-9.]+)\]', line)
        if not match:
            continue
        timestamp = float(match[1])
        if not initial and timestamp > last_kernel_time and re.search(r'\bXid\b|left-over mappings|Assertion failed|quarantined|\bBUG:|\bOops:', line):
            errors.append(line)
    timestamps = [float(value) for value in re.findall(r'^\[\s*([0-9.]+)\]', log, re.M)]
    if timestamps:
        last_kernel_time = max(timestamps)
    (args.output / 'kernel-latest.log').write_text(log)
    if errors:
        (args.output / 'kernel-errors.log').write_text('\n'.join(errors) + '\n')
        raise RuntimeError('new kernel errors; see kernel-errors.log')

check_kernel(initial=True)

def save():
    (args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')

try:
    for round_number in range(args.rounds):
        children = []
        deadline = time.monotonic() + 240
        next_kernel_check = time.monotonic() + 5
        for label, a, b in pairs:
            for worker in range(2):
                seed = rng.randrange(1, 2**32)
                name = f'{label}-round{round_number}-worker{worker}-seed{seed}'
                path = args.output / (name + '.log')
                kill_at = rng.choice([50, 100, 150]) if args.kill and round_number % 2 and worker == round_number % 2 else None
                with path.open('w') as log:
                    proc = subprocess.Popen([str(args.binary.resolve()), a, b, 'stress', '64', '512', str(seed), str(args.steps)], stdout=log, stderr=subprocess.STDOUT)
                children.append({'process': proc, 'name': name, 'path': path, 'kill_at': kill_at, 'killed': False, 'seed': seed})
        while any(child['process'].poll() is None for child in children):
            if time.monotonic() > deadline:
                raise TimeoutError('stress round timed out')
            for child in children:
                proc = child['process']
                log = child['path'].read_text()
                if proc.poll() not in (None, 0, -signal.SIGKILL):
                    raise RuntimeError(f"failed child {child['name']}: {proc.returncode}")
                if child['kill_at'] is not None and not child['killed'] and proc.poll() is None:
                    progress = [int(step) for step in re.findall(r'STRESS_PROGRESS .*?step=(\d+)', log)]
                    if progress and max(progress) >= child['kill_at']:
                        proc.kill()
                        child['killed'] = True
            if time.monotonic() >= next_kernel_check:
                check_kernel()
                next_kernel_check = time.monotonic() + 5
            time.sleep(.05)
        for child in children:
            proc = child['process']
            log = child['path'].read_text()
            if child['killed']:
                if proc.returncode != -signal.SIGKILL:
                    raise RuntimeError('unexpected killed child status')
            elif proc.returncode != 0 or 'PASS STRESS' not in log:
                raise RuntimeError('child did not pass: ' + child['name'])
            results.append({key: child[key] for key in ('name', 'seed', 'kill_at', 'killed')} | {'returncode': proc.returncode, 'last_status': next((line for line in reversed(log.splitlines()) if 'STRESS' in line), '')})
        save()
        print(f'PASS round={round_number} processes={len(children)} killed={sum(child["killed"] for child in children)}', flush=True)
        # Refill and release budgets after all clients (including killed ones) exit.
        for label, a, b in pairs:
            with (args.output / f'{label}-round{round_number}-recovery.log').open('w') as log:
                subprocess.run([str(args.binary.resolve()), a, b, 'exhaust', '32', '512'], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
        check_kernel()
        print(f'PASS round={round_number} post-exit budget recovery and data', flush=True)
finally:
    for child in children:
        proc = child['process']
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)
    save()
