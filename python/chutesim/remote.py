"""Remote drop execution: run the (design, seed) tasks of an Evaluator on a bigger machine.

The optimizers (MATLAB) and the evaluator/cache stay local; only `_task` calls are shipped. The server
listens on 127.0.0.1 and is reached through an SSH tunnel (ssh -L PORT:127.0.0.1:PORT host), with a
shared authkey. Before any task runs, client and server compare simulator, pipeline and asset hashes and
refuse to work on a mismatch, so remote drops are the same computation as local ones (only the
rendering environment differs; it is recorded in every manifest).

    server:  python -m chutesim.remote serve --port 7777 --workers 120
    client:  CHUTESIM_REMOTE=127.0.0.1:7777 (Evaluator then uses RemotePool instead of a local pool)
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import threading
import time
import traceback
from multiprocessing.connection import Client, Listener
from pathlib import Path

from .config import REPO_ROOT

KEY_FILE = Path.home() / ".config" / "chutesim_remote_key"


def authkey() -> bytes:
    if not KEY_FILE.exists():
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        KEY_FILE.write_bytes(os.urandom(32).hex().encode())
        KEY_FILE.chmod(0o600)
    return KEY_FILE.read_bytes().strip()


def versions(cfg: dict) -> dict:
    from .provenance import pipeline_version, simulator_version
    h = hashlib.sha256()
    adir = REPO_ROOT / cfg["payload"]["assets_dir"]
    for f in sorted(adir.glob("*.stl")):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return {"simulator": simulator_version(), "pipeline": pipeline_version(cfg), "assets": h.hexdigest()[:16]}


# ---------------------------------------------------------------- server
def _run_task(t):
    """_task with a retry: transient renderer failures (e.g. GPU memory momentarily exhausted by many
    offscreen contexts) are retried; the drop itself is deterministic, so a retry gives the same result."""
    from .evaluate import _task
    for attempt in range(4):
        try:
            return _task(t)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


PER_CONN_INFLIGHT = int(os.environ.get("CHUTESIM_REMOTE_PER_CONN", "30"))
SMALL_BATCH = int(os.environ.get("CHUTESIM_REMOTE_SMALL_BATCH", "5"))


def _set_gl(backend: str):
    """Worker initializer: choose the offscreen renderer before mujoco is imported in this process; EGL
    workers are spread over the GPUs (CHUTESIM_N_GPU) by process id."""
    os.environ["MUJOCO_GL"] = backend
    os.environ["PYOPENGL_PLATFORM"] = backend
    os.environ["LP_NUM_THREADS"] = "1"
    if backend == "egl":
        n = int(os.environ.get("CHUTESIM_N_GPU", "1"))
        os.environ["MUJOCO_EGL_DEVICE_ID"] = str(os.getpid() % max(n, 1))


def _serve_conn(conn, pools, work_root: Path):
    try:
        while True:
            try:
                msg = conn.recv()
            except EOFError:
                return
            kind, payload = msg
            if kind == "hello":
                mine = versions(payload["cfg"])
                conn.send(("ok", mine) if mine == payload["versions"] else ("mismatch", mine))
            elif kind == "map":
                tasks = []
                for t in payload:
                    d, seed, cfg, run_root, trial, keep = t
                    tasks.append((d, seed, cfg, str(work_root / Path(run_root).name), trial, keep))
                # small batches (sequential methods: one design x scenarios) are latency-bound -> GPU pool;
                # large batches (population methods, re-scoring) are throughput-bound -> CPU (OSMesa) pool
                ex = pools["gpu"] if (pools.get("gpu") and len(tasks) <= SMALL_BATCH) else pools["cpu"]
                # fair sharing: each connection (= one optimizer run) has at most PER_CONN_INFLIGHT drops
                # queued/running, so one big population batch cannot starve the sequential methods
                sem = threading.BoundedSemaphore(PER_CONN_INFLIGHT)
                futs = []
                for t in tasks:
                    sem.acquire()
                    f = ex.submit(_run_task, t)
                    f.add_done_callback(lambda _f: sem.release())
                    futs.append(f)
                out, err = [], None
                for f in futs:
                    try:
                        out.append(f.result())
                    except Exception:
                        err = traceback.format_exc()
                        out.append(None)
                conn.send(("err", err) if err else ("ok", out))
    finally:
        conn.close()


def serve(port: int, workers: int, work_root: str, gpu_workers: int = 0):
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor
    from .evaluate import _ONE_THREAD, _python_exe
    os.environ.update(_ONE_THREAD)
    ctx = mp.get_context("spawn")
    ctx.set_executable(_python_exe())
    cpu_backend = "osmesa" if gpu_workers else os.environ.get("MUJOCO_GL", "egl")
    pools = {"cpu": ProcessPoolExecutor(max_workers=workers, mp_context=ctx, initializer=_set_gl, initargs=(cpu_backend,))}
    if gpu_workers:
        pools["gpu"] = ProcessPoolExecutor(max_workers=gpu_workers, mp_context=ctx, initializer=_set_gl, initargs=("egl",))
    wr = Path(work_root)
    wr.mkdir(parents=True, exist_ok=True)
    lst = Listener(("127.0.0.1", port), authkey=authkey())
    print(f"chutesim remote: {workers} {cpu_backend} workers + {gpu_workers} egl workers on 127.0.0.1:{port}, "
          f"work root {wr}", flush=True)
    while True:
        try:
            conn = lst.accept()
        except Exception as e:   # bad authkey / dropped handshake: keep serving
            print("accept failed:", e, flush=True)
            continue
        threading.Thread(target=_serve_conn, args=(conn, pools, wr), daemon=True).start()


# ---------------------------------------------------------------- client
class RemotePool:
    """Drop-in for the Evaluator's pool: .map(_task, tasks) runs the tasks on the server.
    Connection problems are retried (the whole batch is resent; drops are deterministic)."""

    def __init__(self, address: str, cfg: dict, retry_s: float = 3600):
        host, port = address.rsplit(":", 1)
        self.addr = (host, int(port))
        self.cfg = cfg
        self.retry_s = retry_s
        self.batch_timeout_s = float(os.environ.get("CHUTESIM_REMOTE_BATCH_TIMEOUT", "2700"))
        self.ver = versions(cfg)

    def _connect(self):
        conn = Client(self.addr, authkey=authkey())
        conn.send(("hello", {"versions": self.ver, "cfg": self.cfg}))
        status, theirs = conn.recv()
        if status != "ok":
            conn.close()
            raise RuntimeError(f"remote code/asset mismatch: local {self.ver} vs remote {theirs}")
        return conn

    def map(self, func, tasks, chunksize=1):
        t0 = time.time()
        delay = 5
        while True:
            try:
                conn = self._connect()
                try:
                    conn.send(("map", list(tasks)))
                    # a batch whose connection was silently lost (e.g. server restart) would block forever
                    if not conn.poll(self.batch_timeout_s):
                        raise ConnectionError(f"no reply within {self.batch_timeout_s:.0f} s")
                    status, out = conn.recv()
                finally:
                    conn.close()
                if status != "ok":
                    raise RuntimeError("remote task failed:\n" + str(out))
                return out
            except (ConnectionError, EOFError, OSError) as e:
                if time.time() - t0 > self.retry_s:
                    raise
                print(f"remote unavailable ({e}); retrying in {delay}s", file=sys.stderr, flush=True)
                time.sleep(delay)
                delay = min(delay * 2, 60)

    def close(self):
        pass

    def join(self):
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="chutesim.remote")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("serve")
    p.add_argument("--port", type=int, default=7777)
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    p.add_argument("--work-root", default=str(REPO_ROOT / "data" / "sim_remote"))
    p.add_argument("--gpu-workers", type=int, default=0, help="if >0: EGL pool for small batches, OSMesa pool for the rest")
    sp.add_parser("versions")
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        serve(a.port, a.workers, a.work_root, a.gpu_workers)
    else:
        from .config import load_config
        print(versions(load_config(None)))


if __name__ == "__main__":
    main()
