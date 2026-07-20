"""PQ — Pulse Quantum Feynman path integrals on the vank float kernel.

The PQ workload of the dual-coin plan (``docs/DUAL_COIN_IPO_PLAN.md`` §5 in
Knitweb/pulse): amplitudes as sums over lattice paths, each path contributing
the phasor ``e^(i·S)`` for its discretized action ``S``. Everything runs on
:mod:`.vfloat`, so the same job produces the same bits on every peer — which is
exactly what lets a path integral settle as proof-of-useful-work under
``VERIFICATION_UNIFORM`` (a verifier simply re-executes and byte-compares),
mirroring ``knitweb.quantum.job`` for circuits.

This module lives in vank, not pulse, deliberately: vank already depends on
pulse, so pulse cannot import the float kernel without a cycle — the PQ engine
sits on top of both (``knitweb_knitfield.registry`` provides the job-class
registry both sides share).

Model — a particle on a 1-D lattice of ``sites`` sites hops between
nearest-neighbour sites (step ∈ {−1, 0, +1}) from ``src`` to ``dst`` in
``steps`` time slices of duration ``dt``. Per slice the action gains

    S += m/2 · (Δx/dt)² · dt  −  V(x) · dt

with ``V = 0`` (free) or ``V = k/2 · (x − center)²`` (harmonic). All job
parameters are integers (micro-units for m, dt, k); positions are lattice
integers. Two execution modes:

  * ``enumerate`` — exact sum over *all* admissible paths, guarded by
    ``path_budget`` (the job is rejected up front if the path count exceeds it);
  * ``sample`` — ``num_paths`` paths drawn by a deterministic SHA-256 stream
    from ``seed``; at every slice the drawn step is filtered to moves that can
    still reach ``dst`` in the remaining slices, so every sampled path is
    admissible by construction.

The proof carries the amplitude only through the declared integer boundary
(``amplitude_micro`` per component) plus the path count — no floats anywhere
near the record, per the fabric rule.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from knitweb.core import canonical
from knitweb_knitfield import VERIFICATION_UNIFORM, register_job_class

from .vfloat import (
    CF,
    amplitude_micro,
    c_add,
    c_exp_i,
    div_round,
    fp_mul,
)

__all__ = [
    "PQ_JOB_CLASS",
    "PathIntegralJob",
    "PathIntegralProof",
    "count_paths",
    "execute",
    "verify",
    "ensure_registered",
]

PQ_JOB_CLASS = "pq-path-integral"
_MICRO_TO_FP = 10 ** 12   # micro-units (10^-6) to vfloat scale (10^-18)

register_job_class(PQ_JOB_CLASS, VERIFICATION_UNIFORM)


def ensure_registered() -> None:
    """Confirm the job class is registered (a no-op after import side effect)."""
    register_job_class(PQ_JOB_CLASS, VERIFICATION_UNIFORM)


@dataclass(frozen=True)
class PathIntegralJob:
    """One deterministic path-integral work unit (integer-only spec)."""

    sites: int
    steps: int
    src: int
    dst: int
    mass_micro: int            # m in micro-units
    dt_micro: int              # slice duration in micro-units
    potential: str = "free"    # "free" | "harmonic"
    k_micro: int = 0           # harmonic strength in micro-units
    center: int = 0            # harmonic center site
    mode: str = "enumerate"    # "enumerate" | "sample"
    path_budget: int = 4096    # enumerate: hard cap on the exact path count
    seed: int = 0              # sample: stream seed
    num_paths: int = 0         # sample: paths to draw

    def __post_init__(self) -> None:
        for name in ("sites", "steps", "src", "dst", "mass_micro", "dt_micro",
                     "k_micro", "center", "path_budget", "seed", "num_paths"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if self.sites <= 0 or self.steps <= 0:
            raise ValueError("sites and steps must be positive")
        if not (0 <= self.src < self.sites and 0 <= self.dst < self.sites):
            raise ValueError("src and dst must be lattice sites")
        if self.mass_micro <= 0 or self.dt_micro <= 0:
            raise ValueError("mass_micro and dt_micro must be positive")
        if self.potential not in ("free", "harmonic"):
            raise ValueError("potential must be 'free' or 'harmonic'")
        if self.potential == "harmonic" and self.k_micro < 0:
            raise ValueError("k_micro must be non-negative")
        if self.mode not in ("enumerate", "sample"):
            raise ValueError("mode must be 'enumerate' or 'sample'")
        if self.mode == "enumerate" and self.path_budget <= 0:
            raise ValueError("path_budget must be positive")
        if self.mode == "sample" and self.num_paths <= 0:
            raise ValueError("sample mode needs num_paths > 0")
        if abs(self.dst - self.src) > self.steps:
            raise ValueError("dst is unreachable within steps")

    def to_record(self) -> dict:
        return {
            "kind": PQ_JOB_CLASS,
            "sites": self.sites, "steps": self.steps,
            "src": self.src, "dst": self.dst,
            "mass_micro": self.mass_micro, "dt_micro": self.dt_micro,
            "potential": self.potential, "k_micro": self.k_micro,
            "center": self.center, "mode": self.mode,
            "path_budget": self.path_budget,
            "seed": self.seed, "num_paths": self.num_paths,
        }

    @property
    def cid(self) -> str:
        return canonical.cid(self.to_record())


@dataclass(frozen=True)
class PathIntegralProof:
    """What a worker emits: the integer amplitude components and their digest."""

    re_micro: int    # amplitude real part, micro-units
    im_micro: int    # amplitude imaginary part, micro-units
    paths: int       # paths summed (exact count, or num_paths in sample mode)
    digest: str      # sha256 over the canonical proof body, bound to the job

    def body(self, job_cid: str) -> dict:
        return {"kind": "pq-proof", "job": job_cid, "re_micro": self.re_micro,
                "im_micro": self.im_micro, "paths": self.paths}


# --------------------------------------------------------------------------- #
# Action + amplitude (all vfloat)
# --------------------------------------------------------------------------- #
def _slice_action(job: PathIntegralJob, x: int, step: int) -> int:
    """Fixed-point action contribution of one time slice starting at ``x``."""
    m = job.mass_micro * _MICRO_TO_FP
    dt = job.dt_micro * _MICRO_TO_FP
    # kinetic: m/2 * (step/dt)^2 * dt  ==  m * step^2 / (2 dt)   (step ∈ {-1,0,1})
    kinetic = div_round(m * (step * step), 2 * job.dt_micro * 10 ** 6)
    action = kinetic
    if job.potential == "harmonic" and job.k_micro:
        d = x - job.center
        # potential term: -(k/2) * d^2 * dt
        action -= fp_mul(div_round(job.k_micro * _MICRO_TO_FP * (d * d), 2), dt)
    return action


def _admissible_steps(job: PathIntegralJob, x: int, slices_left: int) -> list[int]:
    """Steps from ``x`` that stay on the lattice and can still reach ``dst``."""
    out = []
    for step in (-1, 0, 1):
        nxt = x + step
        if 0 <= nxt < job.sites and abs(job.dst - nxt) <= slices_left - 1:
            out.append(step)
    return out


def count_paths(job: PathIntegralJob) -> int:
    """Exact admissible-path count (dynamic programming, cheap)."""
    counts = {job.src: 1}
    for t in range(job.steps):
        nxt: dict[int, int] = {}
        for x, n in counts.items():
            for step in _admissible_steps(job, x, job.steps - t):
                nxt[x + step] = nxt.get(x + step, 0) + n
        counts = nxt
    return counts.get(job.dst, 0)


def _enumerate_amplitude(job: PathIntegralJob) -> tuple[CF, int]:
    total = CF(0, 0)
    paths = 0
    stack: list[tuple[int, int, int]] = [(job.src, 0, 0)]  # (x, t, action_so_far)
    while stack:
        x, t, action = stack.pop()
        if t == job.steps:
            total = c_add(total, c_exp_i(action))
            paths += 1
            continue
        # reversed() keeps DFS order lexicographic in step (-1, 0, 1) — the
        # summation order is part of the job's determinism contract.
        for step in reversed(_admissible_steps(job, x, job.steps - t)):
            stack.append((x + step, t + 1, action + _slice_action(job, x, step)))
    return total, paths


def _sample_amplitude(job: PathIntegralJob) -> tuple[CF, int]:
    total = CF(0, 0)
    seed = job.seed.to_bytes(8, "big", signed=False)
    for i in range(job.num_paths):
        x, action = job.src, 0
        for t in range(job.steps):
            allowed = _admissible_steps(job, x, job.steps - t)
            draw = hashlib.sha256(seed + i.to_bytes(8, "big") + t.to_bytes(4, "big"))
            step = allowed[draw.digest()[0] % len(allowed)]
            action += _slice_action(job, x, step)
            x += step
        total = c_add(total, c_exp_i(action))
    return total, job.num_paths


def execute(job: PathIntegralJob) -> PathIntegralProof:
    """Do the work: sum the path phasors and emit a reproducible proof."""
    ensure_registered()
    if job.mode == "enumerate":
        n = count_paths(job)
        if n == 0:
            raise ValueError("no admissible path from src to dst")
        if n > job.path_budget:
            raise ValueError(f"exact enumeration of {n} paths exceeds path_budget "
                             f"{job.path_budget}; use mode='sample'")
        amplitude, paths = _enumerate_amplitude(job)
    else:
        amplitude, paths = _sample_amplitude(job)
    proof = PathIntegralProof(
        re_micro=amplitude_micro(amplitude.re),
        im_micro=amplitude_micro(amplitude.im),
        paths=paths,
        digest="",
    )
    body = canonical.encode(proof.body(job.cid))
    return PathIntegralProof(
        re_micro=proof.re_micro, im_micro=proof.im_micro, paths=paths,
        digest=hashlib.sha256(body).hexdigest(),
    )


def verify(job: PathIntegralJob, proof: PathIntegralProof) -> bool:
    """Uniform verification: re-execute and confirm the byte-identical proof.

    Deterministic booleans only — a digest that does not match the claimed
    components, or components that re-execution does not reproduce, is fraud
    and must not settle (slashable).
    """
    body = canonical.encode(proof.body(job.cid))
    if hashlib.sha256(body).hexdigest() != proof.digest:
        return False
    try:
        recomputed = execute(job)
    except ValueError:
        return False  # inadmissible or over-budget jobs can never carry a proof
    return recomputed == proof
