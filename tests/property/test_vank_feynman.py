"""PQ path-integral proofs: exactness, interference, determinism, verification.

The contract mirrors knitweb.quantum.job: byte-reproducible execution settles
under VERIFICATION_UNIFORM, so the tests pin analytic amplitudes (against the
vfloat kernel directly), path counts, bit-identical sampled runs, and the
fraud paths of verify().
"""

import dataclasses

import pytest

from knitweb_vank.feynman import (
    PQ_JOB_CLASS,
    PathIntegralJob,
    count_paths,
    ensure_registered,
    execute,
    verify,
)
from knitweb_vank.vfloat import amplitude_micro, c_add, c_exp_i, div_round

_MICRO_TO_FP = 10 ** 12


def _free_job(**over) -> PathIntegralJob:
    spec = dict(sites=2, steps=2, src=0, dst=0,
                mass_micro=1_000_000, dt_micro=1_000_000)  # m = dt = 1.0
    spec.update(over)
    return PathIntegralJob(**spec)


@pytest.mark.property
def test_single_path_free_particle_has_unit_amplitude():
    # One site: the only admissible path never moves; free action is 0, so the
    # amplitude is exactly e^(i*0) = 1.
    job = _free_job(sites=1, steps=3)
    proof = execute(job)
    assert (proof.re_micro, proof.im_micro, proof.paths) == (1_000_000, 0, 1)


@pytest.mark.property
def test_two_path_interference_matches_the_kernel():
    # sites=2, steps=2, src=dst=0: exactly the two-slit sum
    #   stay-stay   (action 0)  and  hop-return (action m/dt = 1.0)
    job = _free_job()
    assert count_paths(job) == 2
    hop_action = 2 * div_round(1_000_000 * _MICRO_TO_FP, 2 * 1_000_000 * 10 ** 6)
    expected = c_add(c_exp_i(0), c_exp_i(hop_action))
    proof = execute(job)
    assert proof.paths == 2
    assert proof.re_micro == amplitude_micro(expected.re)
    assert proof.im_micro == amplitude_micro(expected.im)


@pytest.mark.property
def test_count_paths_agrees_with_enumeration():
    job = _free_job(sites=4, steps=6, src=0, dst=2)
    assert count_paths(job) == execute(job).paths > 0


@pytest.mark.property
def test_harmonic_potential_shifts_the_phase():
    free = execute(_free_job(sites=1, steps=2))
    pinned = execute(_free_job(sites=1, steps=2, potential="harmonic",
                               k_micro=500_000, center=1))
    assert (free.re_micro, free.im_micro) != (pinned.re_micro, pinned.im_micro)


@pytest.mark.property
def test_sampled_mode_is_bit_identical_and_verifiable():
    job = _free_job(sites=5, steps=12, dst=2, mode="sample", seed=42, num_paths=64)
    p1, p2 = execute(job), execute(job)
    assert p1 == p2 and p1.paths == 64
    assert verify(job, p1)
    # A different seed is a different job — its proof must not verify here.
    other = execute(dataclasses.replace(job, seed=43))
    assert not verify(job, other)


@pytest.mark.property
def test_verify_rejects_tampering():
    job = _free_job()
    proof = execute(job)
    assert verify(job, proof)
    forged = dataclasses.replace(proof, re_micro=proof.re_micro + 1)
    assert not verify(job, forged)  # digest no longer covers the components
    rehashed = execute(_free_job(steps=4))
    assert not verify(job, rehashed)  # honest proof, wrong job


@pytest.mark.property
def test_enumeration_budget_guard():
    wide = _free_job(sites=9, steps=16, dst=0, path_budget=100)
    with pytest.raises(ValueError):
        execute(wide)
    assert count_paths(wide) > 100  # the guard fired for the right reason


@pytest.mark.property
def test_job_validation_and_registration():
    ensure_registered()  # idempotent; also exercises the import-time seam
    with pytest.raises(ValueError):
        _free_job(dst=5)               # off-lattice
    with pytest.raises(ValueError):
        _free_job(sites=3, steps=1, dst=2)  # unreachable
    with pytest.raises(TypeError):
        _free_job(seed=True)           # bool violates integer-only
    with pytest.raises(ValueError):
        _free_job(mode="sample")       # sample mode needs num_paths
    assert PQ_JOB_CLASS == "pq-path-integral"
