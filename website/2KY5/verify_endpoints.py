from pathlib import Path
import numpy as np
k = 7.291987686899543
conversion = 1e27/6.02214076e23
def solve_original(B, A, V, links):
    u, s, v = np.linalg.svd(B, full_matrices=False)
    sel = s > s[0] * 1e-10
    pinv = v[sel].T / s[sel] @ u[:, sel].T
    R = A - B @ (pinv @ A)
    C = R.T @ R / V
    free = [0, 1, 3, 4, 5]
    q = np.zeros(6)
    q[2] = 1
    q[free] = -np.linalg.pinv(C[np.ix_(free, free)], rcond=1e-10) @ C[free, 2]
    E = float(C[2, 2] - C[2, free] @ np.linalg.pinv(C[np.ix_(free, free)], rcond=1e-10) @ C[free, 2])
    energy = float(q @ C @ q)
    residual = float(np.max(abs(B.T @ R)))
    free_stress = float(np.max(abs((C @ q)[free])))
    mismatch = abs(energy - E)
    assert residual < 1e-07 and np.linalg.eigvalsh(C).min() > -1e-10 and (free_stress < 1e-08) and (mismatch < 1e-10) and (E > 0)
    rr = R @ q
    total = float(rr @ rr)
    affine = float((A.T @ A / V)[2, 2])
    return dict(E_reduced=E, E_kPa_frozen=E * k * conversion, C_reduced=C.tolist(), chain_equilibrium_residual=residual, free_stress_residual=free_stress, stress_energy_mismatch=mismatch, chemical_energy_fraction=float(rr[:links] @ rr[:links] / total), affine_CZZ=affine, chain_relaxed_CZZ=float(C[2, 2]), free_lateral_fraction=float(E / C[2, 2]), chain_relaxation_fraction=float(C[2, 2] / affine), spring_rows=len(B), B_rank=int(sel.sum()))

root = Path(__file__).resolve().parent
for branch in "ABC":
    with np.load(root/f"2KY5_{branch}_operators.npz", allow_pickle=False) as z:
        result = solve_original(z["B"], z["A"], float(np.prod(z["box"])), 34)
    value = result["E_kPa_frozen"]
    print(branch, f"{value:.6f}")
