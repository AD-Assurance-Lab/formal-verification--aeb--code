"""Wait for the GPU, and prove it, rather than silently falling back to the CPU.

Ported from `formal-verification--steering--code/pipeline/gpu.py` on 2026-09-04, after
that repo's desktop migration turned up a second way the usual idiom lies. Every tool
here was written as

    dev = "cuda" if torch.cuda.is_available() else "cpu"

which reads like a portability convenience and is actually a silent-failure switch. It is
wrong in BOTH directions:

  * FALSE when the device is fine. `is_available()` returns False while CARLA is still
    initialising on the same card, and it returns False QUIETLY -- the run continues on
    the CPU, produces numbers, and nothing says so. Caught in the steering study when a
    policy drive printed "CUDA unknown error ... setting the available devices to be zero"
    and then drove the whole lap anyway. Restarting CARLA before EVERY run turned this
    from one startup race per cell into one per run.

  * TRUE when the device is useless. On the lab's RTX 5090 (sm_120) with a torch built
    for sm_50..sm_90, `is_available()` returns True and `get_device_name()` answers
    correctly, and then every kernel dies with "no kernel image is available for
    execution on the device". A version check cannot catch this. Running a kernel can.

    dev = require_cuda()                    # waits, then insists
    dev = require_cuda(allow_cpu=True)      # for tools that genuinely do not need it
    dev = require_cuda(tries=1, wait_s=0)   # nothing racing CARLA; fail fast
"""
import time

import torch


def require_cuda(tries=12, wait_s=10.0, allow_cpu=False, verbose=True):
    """Return "cuda" once the device is actually usable, or raise.

    Allocates AND OPERATES ON a tensor rather than trusting is_available(): the flag can
    be True while the context still fails, and an allocation alone can succeed on a card
    whose kernels the installed torch does not carry.
    """
    last = None
    for i in range(tries):
        try:
            if torch.cuda.is_available():
                torch.zeros(8, device="cuda") + 1.0     # prove it, do not assume it
                return "cuda"
            last = "torch.cuda.is_available() is False"
        except Exception as exc:                        # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
        if verbose:
            print(f"  GPU not ready ({last}); CARLA is probably still starting "
                  f"-- retry {i+1}/{tries} in {wait_s:.0f} s", flush=True)
        if wait_s:
            time.sleep(wait_s)
    if allow_cpu:
        print("  WARNING: falling back to CPU deliberately (allow_cpu=True)", flush=True)
        return "cpu"
    raise RuntimeError(
        f"GPU never became available after {tries} tries ({last}).\n"
        "  Refusing to fall back to the CPU silently: a measurement that quietly runs "
        "on a different device is a measurement of something else.\n"
        "  If the card is present but every kernel fails, the torch build does not match "
        "its compute capability -- check torch.cuda.get_arch_list() against "
        "torch.cuda.get_device_capability(), and rebuild with scripts/bootstrap_env.sh.")
