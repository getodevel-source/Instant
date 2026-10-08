"""Medidor del bake-off: corre cada runner N veces y mide, por corrida:
arranque (hasta primer frame), fps medio y peor p95 (del propio runner), CPU
(% de un core, arbol de procesos) y working set (MB, arbol completo: incluye
los subprocesos de Chromium en la ruta web).

Solo Windows (usa Toolhelp32 + psapi via ctypes). Sin dependencias extra.

Uso: python measure.py [--runner qml|web|both] [--runs 3] [--seconds-cap 30]
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import statistics as st
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


# Firmas explicitas: sin esto los HANDLE de 64 bits viajan como c_int.
kernel32.OpenProcess.restype = ctypes.c_void_p
kernel32.OpenProcess.argtypes = (wt.DWORD, wt.BOOL, wt.DWORD)
kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
kernel32.CreateToolhelp32Snapshot.argtypes = (wt.DWORD, wt.DWORD)


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)), ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_char * 260)]


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


kernel32.Process32First.argtypes = (ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32))
kernel32.Process32First.restype = wt.BOOL
kernel32.Process32Next.argtypes = (ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32))
kernel32.Process32Next.restype = wt.BOOL
kernel32.GetProcessTimes.argtypes = (ctypes.c_void_p, ctypes.POINTER(wt.FILETIME),
                                     ctypes.POINTER(wt.FILETIME), ctypes.POINTER(wt.FILETIME),
                                     ctypes.POINTER(wt.FILETIME))
kernel32.GetProcessTimes.restype = wt.BOOL
kernel32.K32GetProcessMemoryInfo.argtypes = (ctypes.c_void_p, ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
                                             wt.DWORD)
kernel32.K32GetProcessMemoryInfo.restype = wt.BOOL


def process_table():
    """[(pid, ppid)] de todo el sistema."""
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return []
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    rows = []
    try:
        ok = kernel32.Process32First(snapshot, ctypes.byref(entry))
        while ok:
            rows.append((entry.th32ProcessID, entry.th32ParentProcessID))
            ok = kernel32.Process32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return rows


def tree_pids(root_pid):
    rows = process_table()
    children = {}
    for pid, ppid in rows:
        children.setdefault(ppid, []).append(pid)
    result = []
    stack = [root_pid]
    while stack:
        pid = stack.pop()
        result.append(pid)
        stack.extend(children.get(pid, []))
    return result


def process_cpu_ns(pid):
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        creation, exit_, kernel, user = (wt.FILETIME() for _ in range(4))
        if not kernel32.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_),
                                        ctypes.byref(kernel), ctypes.byref(user)):
            return None
        k = (kernel.dwHighDateTime << 32) | kernel.dwLowDateTime
        u = (user.dwHighDateTime << 32) | user.dwLowDateTime
        return (k + u) * 100  # 100 ns -> ns
    finally:
        kernel32.CloseHandle(handle)


def process_ws_bytes(pid):
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        if not kernel32.K32GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None
        return counters.WorkingSetSize
    finally:
        kernel32.CloseHandle(handle)


def snapshot_tree(root_pid):
    cpu = 0
    ws = 0
    for pid in tree_pids(root_pid):
        c = process_cpu_ns(pid)
        w = process_ws_bytes(pid)
        if c:
            cpu += c
        if w:
            ws += w
    return cpu, ws


def run_once(runner, seconds_cap, variant="v2"):
    script = os.path.join(HERE, "run_qml.py" if runner == "qml" else "run_web.py")
    label = runner
    cmd = [sys.executable, script, "--shots", "", "--out", os.path.join(HERE, "out"),
           "--label", f"{label}_measure", "--variant", variant]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, cwd=HERE)
    samples = []
    events = []
    t0 = time.monotonic()
    next_sample = 0.5
    while proc.poll() is None:
        time.sleep(0.1)
        now = time.monotonic() - t0
        if now >= next_sample:
            cpu, ws = snapshot_tree(proc.pid)
            samples.append((now, cpu, ws))
            next_sample += 0.5
        if now > seconds_cap:
            proc.kill()
            break
    out, _ = proc.communicate(timeout=10)
    for line in (out or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except ValueError:
                pass

    # CPU% y WS en regimen (desde t=2s): el arranque distorsiona el promedio.
    steady = [s for s in samples if s[0] >= 2.0 and samples and s[1]]
    cpu_pct = None
    if len(steady) > 1:
        dcpu = steady[-1][1] - steady[0][1]
        dwall = steady[-1][0] - steady[0][0]
        cpu_pct = round(dcpu / (dwall * 1e9) * 100.0, 1)
    ws_avg = round(st.mean([s[2] for s in steady]) / (1024 * 1024), 1) if steady else None
    ws_peak = round(max((s[2] for s in samples), default=0) / (1024 * 1024), 1)

    first = next((e["ms"] for e in events if e["event"] == "first_frame"), None)
    fps = [e["fps"] for e in events if e["event"] == "fps"]
    p95 = [e["p95_ms"] for e in events if e["event"] == "fps"]
    summary = next((e for e in events if e["event"] == "summary"), {})
    return {
        "runner": runner,
        "startup_ms": first,
        "fps_avg": round(st.mean(fps), 1) if fps else None,
        "fps_p95_worst_ms": max(p95) if p95 else None,
        "frames": summary.get("frames"),
        "duration_s": summary.get("duration_s"),
        "cpu_pct_one_core": cpu_pct,
        "ws_avg_mb": ws_avg,
        "ws_peak_mb": ws_peak,
        "samples": len(samples),
    }


def median_of(runs, key):
    values = [r[key] for r in runs if r.get(key) is not None]
    return round(st.median(values), 1) if values else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", choices=["qml", "web", "both"], default="both")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--variant", choices=["v2", "v3", "v4"], default="v2")
    parser.add_argument("--seconds-cap", type=int, default=30)
    args = parser.parse_args()

    runners = ["qml", "web"] if args.runner == "both" else [args.runner]
    report = {}
    for runner in runners:
        runs = []
        for i in range(args.runs):
            result = run_once(runner, args.seconds_cap, args.variant)
            runs.append(result)
            print(json.dumps({"event": "run", "i": i + 1, **result}), flush=True)
        report[runner] = {
            "runs": runs,
            "median": {k: median_of(runs, k) for k in
                       ("startup_ms", "fps_avg", "fps_p95_worst_ms", "cpu_pct_one_core",
                        "ws_avg_mb", "ws_peak_mb", "frames")},
        }
    out_path = os.path.join(HERE, "out", f"measure_{args.variant}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(json.dumps({"event": "report", "file": out_path,
                      "median": {k: v["median"] for k, v in report.items()}}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
