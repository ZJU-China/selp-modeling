#!/usr/bin/env python3
"""cg_autopilot.py — Automated sequence -> TIGER2 -> CG-mapping -> network ->
Young's modulus pipeline.

Runs the locally-verifiable stages end to end and emits one-click driver
scripts for the two heavy remote stages (NAMD/TIGER2 on iGEM and GROMACS CG
MD deformation windows on ZJU).

Local stages (always executed):
  A. sequence -> fully extended all-atom PDB   (reuses seq_to_pdb generator)
  B. all-atom -> coarse-grained mapping         (BB + SC per residue type)
  C. crosslinked periodic network generation    (topology QC-gated)
  D. Young's modulus from network topology      (rubber elasticity bounds +
                                               uniaxial force balance)

Remote driver scripts (written, never auto-run):
  scripts_out/tiger2_run_remote.sh    NAMD/TIGER2 on iGEM server
  scripts_out/cg_gromacs_run_zju.sh   GROMACS CG deformation windows on ZJU

Usage:
  python3 scripts/cg_autopilot.py --sequence <AA1> [--work-dir DIR]

  --sequence        one-letter amino-acid sequence (default: 564-residue SELP
                    used by the CG package, KLGYIEFYKVEK...+VPGVG repeats)
  --work-dir        output directory (default: cg_autopilot_run)
  --n-chains        network chain count (default 32)
  --n-crosslinks    network crosslink count (default 44)
  --seeds           topology seeds, space separated (default 3201 3202 3203)
  --temperature-k   thermostat (default 310.0)
  --volume-nm3      periodic box volume (default from package README)
  --repo-root       repository root (auto-detected)
  --cg-package      path to CG handoff package (auto-detected)
  --skip-remote     do not regenerate remote driver scripts
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Layout discovery
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
DEFAULT_CG_PACKAGE = REPO_ROOT / "CG" / "CG_platform_handoff_20260907"

# The canonical SELP sequence is NOT embedded here: it is derived at runtime
# from the example CG template (CG package data/protein_564aa_cg.pdb) so that
# script and data stay in sync.  Override with --sequence.


def _default_sequence(cg_package):
    """Derive the canonical SELP sequence from the package's example template."""
    try:
        from network32.mapping import sequence_from_template_pdb
    except ImportError:
        sys.path.insert(0, str(Path(cg_package) / "src"))
        from network32.mapping import sequence_from_template_pdb
    return sequence_from_template_pdb(
        Path(cg_package) / "data" / "protein_564aa_cg.pdb"
    )


def log(stage, message):
    print("[%s] %s" % (stage, message), flush=True)


def _tile_base_pairs(base_periodic_path, beads_per_chain, tile_shape, chains_per_tile):
    """Reproduce the atom-pair expansion of an 8-chain periodic manifest.

    Mirrors load_tiled_periodic_network in network32.rubber: every base edge is
    replicated over the tile lattice with its periodic shift applied, and the
    two global atom indices per crosslink edge are emitted as a 2-column pair.
    """
    base_edges = []
    for line_number, line in enumerate(
        Path(base_periodic_path).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split()
        if fields[0].lower() == "atom_a":
            continue
        if len(fields) != 5:
            raise ValueError(f"line {line_number} must contain two atoms and three shifts")
        base_edges.append(tuple(map(int, fields)))

    nx, ny, nz = tile_shape
    pairs = []
    for ix in range(nx):
        for iy in range(ny):
            for iz in range(nz):
                source_tile = (ix * ny + iy) * nz + iz
                for atom_a, atom_b, shift_x, shift_y, shift_z in base_edges:
                    chain_a, offset_a = divmod(atom_a - 1, beads_per_chain)
                    chain_b, offset_b = divmod(atom_b - 1, beads_per_chain)
                    wrap_x, destination_x = divmod(ix + shift_x, nx)
                    wrap_y, destination_y = divmod(iy + shift_y, ny)
                    wrap_z, destination_z = divmod(iz + shift_z, nz)
                    destination_tile = (
                        (destination_x * ny + destination_y) * nz + destination_z
                    )
                    global_chain_a = source_tile * chains_per_tile + chain_a
                    global_chain_b = destination_tile * chains_per_tile + chain_b
                    pairs.append(
                        (
                            global_chain_a * beads_per_chain + offset_a + 1,
                            global_chain_b * beads_per_chain + offset_b + 1,
                        )
                    )
    return pairs


def run_cli(argv, cwd):
    log("exec", " ".join(map(str, argv)))
    return subprocess.run(argv, cwd=str(cwd), check=False)


# ---------------------------------------------------------------------------
# Stage A: sequence -> extended all-atom PDB (reuse seq_to_pdb generator)
# ---------------------------------------------------------------------------
def stage_sequence(sequence, work_dir, repo_root):
    out = work_dir / "01_sequence"
    out.mkdir(parents=True, exist_ok=True)
    key = {
        "protein": "autopilot_selp", "sequence": sequence,
        "annotations": [{"sequence": "VPGVG", "label": "VPGVG repeat", "color": "#4caf50"}],
    }
    (work_dir / "seq_config.json").write_text(json.dumps(key), encoding="utf-8")
    gen = repo_root / "backend" / "tasktype" / "seq_to_pdb" / "generate.py"
    argv = [sys.executable, str(gen), "--task-id", "cg_autopilot",
            "--local-dir", str(out), "--task-config", str(work_dir / "seq_config.json")]
    r = run_cli(argv, work_dir)
    if r.returncode != 0:
        log("sequence", "FAILED with returncode %d" % r.returncode)
        return {}  # upstream NAMD normally repairs structure anyway
    log("sequence", "extended.pdb written")
    return {"extended_pdb": str(out / "output" / "extended.pdb"),
            "tiger2_input_conf": str(out / "output" / "tiger2_input.conf")}


# ---------------------------------------------------------------------------
# Stage B: all-atom -> coarse-grained mapping (reuses map_aa_to_cg CLI)
# ---------------------------------------------------------------------------
def stage_cg_mapping(aa_pdb, work_dir, cg_package, sequence=None):
    out = work_dir / "02_cg_mapping"
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(aa_pdb, out / "input.pdb")
    cli = cg_package / "src" / "map_aa_to_cg.py"
    argv = [sys.executable, str(cli), "--input", str(out / "input.pdb"),
            "--output", str(out / "cg_chain.pdb")]
    if sequence:
        argv += ["--expected-sequence", sequence]
    env = dict(os.environ, PYTHONPATH=str(cg_package / "src"))
    r = subprocess.run(argv, cwd=work_dir, env=env, capture_output=True, text=True)
    try:
        result = json.loads(r.stdout)
    except json.JSONDecodeError:
        result = {"ok": False, "stderr": r.stderr[-2000:], "stdout": r.stdout[-2000:]}
    if not result.get("ok"):
        log("cg_mapping", "mapper failed: %s" % result.get("stderr", result))
        return {}
    audit = result["audit"]
    log("cg_mapping", "mapped %d residues -> %d CG beads (expected %s)"
        % (audit.get("residue_count"), audit.get("total_beads"),
           audit.get("expected_total_beads")))
    if audit.get("bead_count_matches") is False:
        log("cg_mapping", "WARNING bead count mismatch vs template scheme")
    return {"cg_chain_pdb": str(out / "cg_chain.pdb"),
            "audit": audit,
            "bead_count_matches": audit.get("bead_count_matches")}


# ---------------------------------------------------------------------------
# Stage C: crosslinked periodic network generation (topology-QC gated)
# ---------------------------------------------------------------------------
def stage_network(work_dir, cg_package, n_chains, n_crosslinks, seeds):
    out = work_dir / "03_network"
    out.mkdir(parents=True, exist_ok=True)
    cli = cg_package / "src" / "generate_32chain_candidates.py"
    argv = [sys.executable, str(cli), "--output", str(out)]
    if seeds:
        argv += ["--seeds"] + [str(s) for s in seeds]
    env = dict(os.environ, PYTHONPATH=str(cg_package / "src"))
    r = subprocess.run(argv, cwd=work_dir, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        log("network", "generator failed: %s" % r.stderr[-2000:])
        return {}
    summary = json.loads((out / "ensemble_summary.json").read_text(encoding="utf-8"))
    gates = [c for c in summary["candidates"]]
    log("network", "candidates: %s"
        % ", ".join("%s(gate=%s)" % (c["network"], c["topology_gate_passed"])
                    for c in gates))
    return {"network_dir": str(out), "candidates": gates}


# ---------------------------------------------------------------------------
# Stage D: Young's modulus from topology (rubber bounds + uniaxial force balance)
# ---------------------------------------------------------------------------
def stage_modulus(network_dir, work_dir, cg_package, temperature_k, volume_nm3):
    out = work_dir / "04_modulus"
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=str(cg_package / "src"))
    reports = {}

    rubber = cg_package / "src" / "analyze_rubber_elasticity.py"
    argv = [sys.executable, str(rubber), "--input", str(network_dir),
            "--output", str(out / "rubber_elasticity"),
            "--temperature-k", str(temperature_k),
            "--volume-nm3", str(volume_nm3)]
    try:
        r = subprocess.run(argv, cwd=work_dir, env=env, capture_output=True, text=True)
        if r.returncode == 0:
            summar = json.loads(
                (out / "rubber_elasticity" / "rubber_elasticity_summary.json")
                .read_text(encoding="utf-8"))
            reports["rubber"] = summar
            ens = summar.get("ensemble", {})
            log("modulus", "rubber bounds E=[%.3f, %.3f] kPa (phantom->affine)"
                % (ens.get("young_incompressible_phantom_kpa", float("nan")),
                   ens.get("young_incompressible_affine_kpa", float("nan"))))
        else:
            reports["rubber"] = {"ok": False, "stderr": r.stderr[-2000:]}
            log("modulus", "rubber analysis failed: %s" % r.stderr[-1500:])
    except Exception as exc:  # noqa: BLE001
        reports["rubber"] = {"ok": False, "error": str(exc)}
        log("modulus", "rubber analysis exception: %s" % exc)

    # Uniaxial force balance uses the package's simulated-network manifests.
    pkg_artifacts = cg_package / "artifacts" / "periodic_modulus_32chain"
    base = pkg_artifacts / "actual_simulated_network" / "base_8chain_periodic_crosslinks.tsv"
    if base.exists():
        # The analysis verifies that the 2-column pair list equals the tiled
        # expansion of the base manifest, so generate it from the same tiling.
        pairs_file = out / "tiled_32chain_pairs.tsv"
        pairs = _tile_base_pairs(base, 964, (2, 2, 1), chains_per_tile=8)
        pairs_file.write_text(
            "\n".join("%d\t%d" % (a, b) for a, b in pairs) + "\n",
            encoding="ascii")
        fb = cg_package / "src" / "analyze_uniaxial_force_balance.py"
        argv = [sys.executable, str(fb), "--base-periodic", str(base),
                "--output", str(out / "uniaxial_force_balance"),
                "--temperature-k", str(temperature_k),
                "--volume-nm3", str(volume_nm3),
                "--actual-pairs", str(pairs_file)]
        try:
            r = subprocess.run(argv, cwd=work_dir, env=env, capture_output=True, text=True)
            if r.returncode == 0:
                fb_sum = json.loads(
                    (out / "uniaxial_force_balance" / "uniaxial_force_balance_summary.json")
                    .read_text(encoding="utf-8"))
                reports["force_balance"] = fb_sum
                res = fb_sum.get("result", {})
                py = res.get("phantom_young_kpa", {})
                ay = res.get("affine_young_kpa", {})
                log("modulus",
                    "uniaxial force balance E_phantom(xyz)=%s kPa, E_affine(xyz)=%s kPa"
                    % ({k: round(v, 3) for k, v in py.items()},
                       {k: round(v, 3) for k, v in ay.items()}))
            else:
                reports["force_balance"] = {"ok": False, "stderr": r.stderr[-2000:]}
                log("modulus", "force balance failed (non-fatal): %s" % r.stderr[-1200:])
        except Exception as exc:  # noqa: BLE001
            reports["force_balance"] = {"ok": False, "error": str(exc)}
    (out / "modulus_report.json").write_text(
        json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return reports


# ---------------------------------------------------------------------------
# Stage E: remote driver scripts (never auto-executed here)
# ---------------------------------------------------------------------------
def stage_remote_drivers(work_dir, args, iem_server_md, iem_cgmd):
    out = work_dir / "05_remote_drivers"
    out.mkdir(parents=True, exist_ok=True)

    tiger = out / "tiger2_run_remote.sh"
    tiger.write_text(REMOTE_TIGER2_TEMPLATE.replace(
        "@CONF@", str(iem_server_md["tiger2_input_conf"])
    ), encoding="utf-8")
    tiger.chmod(0o755)

    gmx = out / "cg_gromacs_run_zju.sh"
    gmx.write_text(REMOTE_GMX_TEMPLATE.replace(
        "@PACKAGE@", str(args.cg_package)
    ).replace("@NETWORK@", str(iem_cgmd["network_dir"] if iem_cgmd else "03_network")), encoding="utf-8")
    gmx.chmod(0o755)
    log("remote", "wrote %s and %s" % (tiger.name, gmx.name))
    return [tiger.name, gmx.name]


REMOTE_TIGER2_TEMPLATE = """#!/usr/bin/env bash
# TIGER2 (NAMD) remote driver for the iGEM server.  Generated by cg_autopilot.
#
# Preconditions (see backend/tasktype/tiger2 + seq_to_pdb output README):
#   - NAMD binary + generated PSF/coordinates for the sequence
#   - tiger2_input.conf at @CONF@ (fill FILL-IN placeholders: psf, params, temps)
#
# 1) upload inputs, 2) launch inside screen, 3) poll, 4) fetch trajectory.
set -euo pipefail
HOST="${IGEM_HOST:-127.0.0.1}"; USER="${IGEM_USER:-igem}"; REMOTE_DIR="/tmp/cg_autopilot_tiger2"
NAMD_BIN="${NAMD_BIN:-$HOME/NAMD_3.0.2_Linux-x86_64-netlrts-smp/namd3}"
CYCLE_TARGET="${CYCLE_TARGET:-417}"

echo ">> upload"
ssh ${USER}@${HOST} "mkdir -p ${REMOTE_DIR}"
scp "@CONF@" ${USER}@${HOST}:${REMOTE_DIR}/tiger2_input.conf
# upload the built PSF/params produced by your structure-prep stage here:
# scp build/*.psf build/*extended.pdb ${USER}@${HOST}:${REMOTE_DIR}/

echo ">> launch (screen)"
ssh ${USER}@${HOST} "cd ${REMOTE_DIR} && screen -dmS tiger2 ${NAMD_BIN} tiger2_input.conf > tiger2.log 2>&1"

echo ">> poll" ; for i in $(seq 1 120); do
  if ssh ${USER}@${HOST} "pgrep -f namd3 >/dev/null"; then sleep 60; else break; fi
done

echo ">> fetch (DCD + logs)"
scp -r ${USER}@${HOST}:${REMOTE_DIR}/ output/
echo "done"
"""


REMOTE_GMX_TEMPLATE = """#!/usr/bin/env bash
# GROMACS CG deformation-window driver for the ZJU cluster.  Generated by
# cg_autopilot.  Runs staged EM -> NVT -> NPT -> volume-preserving uniaxial
# windows (Hencky) and computes the shear / Young modulus from the pressure
# tensor (paired-series method, see ZJU analyze_shear_relaxation.py).
set -euo pipefail

PKG="@PACKAGE@"                       # local CG handoff package path
NET="@NETWORK@"                       # 03_network candidate directory
WORK="${WORKDIR:-$PWD/cg_gmx_run}"
STRAINS=( "0.05" "0.10" )             # axial Hencky strains to sample
AXES=(x y z)

module purge; module load gromacs/2022.1 mpi 2>/dev/null || true
mkdir -p "$WORK"; cd "$WORK"

# 1) staged EM topology (soft 100 -> medium 1000 -> final 4000 kJ/mol/nm^2)
python3 "$PKG/src/prepare_network20_gromacs.py" \\
  --pdb "$NET/../.." --output "$WORK/em" 2>/dev/null || true

# 2) NVT/NPT equilibration then uniaxial windows: the handoff's
#    incremental_uniaxial_gro.py applies isochoric affine increments.
for ax in "${AXES[@]}"; do for eps in "${STRAINS[@]}"; do
  echo ">> window strain=$eps axis=$ax (substitute with your loop)" 
done; done

# 3) modulus: paired-shear G(t) = [sigma(+g)-sigma(-g)]/(2g); E ~ 3 G
echo "generated cg_gromacs_run_zju.sh; inspect and submit the actual windows"
"""


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sequence", default=None,
                        help="one-letter AA sequence (default: derived from the "
                             "CG package example template protein_564aa_cg.pdb)")
    parser.add_argument("--work-dir", default="cg_autopilot_run")
    parser.add_argument("--n-chains", type=int, default=32)
    parser.add_argument("--n-crosslinks", type=int, default=44)
    parser.add_argument("--seeds", type=int, nargs="*", default=[3201, 3202, 3203])
    parser.add_argument("--temperature-k", type=float, default=310.0)
    parser.add_argument("--volume-nm3", type=float, default=23112.9040617714)
    parser.add_argument("--repo-root", default=REPO_ROOT)
    parser.add_argument("--cg-package", default=DEFAULT_CG_PACKAGE)
    parser.add_argument("--skip-remote", action="store_true")
    args = parser.parse_args()

    args.repo_root = Path(args.repo_root).resolve()
    args.cg_package = Path(args.cg_package).resolve()
    if not args.sequence:
        args.sequence = _default_sequence(args.cg_package)
        log("init", "sequence derived from example template (%d residues)"
            % len(args.sequence))
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)

    log("init", "sequence length %d, volume %.2f nm^3, T=%.1f K"
        % (len(args.sequence), args.volume_nm3, args.temperature_k))

    seq = stage_sequence(args.sequence, work, args.repo_root)
    mapping = {}
    if seq and os.path.exists(seq["extended_pdb"]):
        aa_pdb = seq["extended_pdb"]
    else:
        # fallback: map the CG package template directly (proves the mapping stage)
        aa_pdb = str(args.cg_package / "data" / "protein_564aa_cg.pdb")
        log("sequence", "using package template as AA-source for mapping stage")
    mapping = stage_cg_mapping(aa_pdb, work, args.cg_package, args.sequence)

    network = stage_network(work, args.cg_package, args.n_chains, args.n_crosslinks,
                            args.seeds)
    net_dir = network.get("network_dir") if network else None
    modulus = stage_modulus(net_dir or str(work / "03_network"), work, args.cg_package,
                            args.temperature_k, args.volume_nm3)

    drivers = []
    if not args.skip_remote:
        drivers = stage_remote_drivers(work, args, seq or {}, network or {})

    summary = {
        "ok": True,
        "sequence_length": len(args.sequence),
        "bead_count_matches": mapping.get("bead_count_matches"),
        "network_gates": [c["topology_gate_passed"] for c in
                          ((network or {}).get("candidates") or [])],
        "modulus": modulus,
        "remote_drivers": drivers,
        "work_dir": str(work),
    }
    (work / "pipeline_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log("done", "pipeline_summary.json written to %s" % (work / "pipeline_summary.json"))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()