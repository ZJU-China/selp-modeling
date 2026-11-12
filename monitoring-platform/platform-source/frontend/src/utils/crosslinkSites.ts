// Crosslink-site selection for sequence → coarse-grained hydrogel tasks.
//
// The CG network generator cross-links specific amino-acid residues (e.g. Tyr)
// to form network junctions.  This module turns a 1-letter amino-acid sequence
// into a list of candidate crosslink sites at the requested residue types,
// optionally thinned to a well-spaced subset (mirrors the template's core-Tyr
// pattern of ~10 junctions per chain spaced near-uniformly).

export interface CrosslinkSite {
  /** 1-based residue position in the sequence. */
  position: number
  /** 1-letter code at the site (e.g. "Y"). */
  residue: string
  /** 3-letter name (e.g. "TYR"). */
  residueName: string
}

export interface CrosslinkSelectionOptions {
  /** Target 1-letter residue codes (uppercase), e.g. ["Y"] for Tyr. */
  targets: string[]
  /** Maximum number of sites to keep; if unset, keep ``maxCount`` if given else all. */
  maxCount?: number
  /** Minimum separation (in residues) between kept sites; 0 disables thinning. */
  minSpacing?: number
  /** Distribute kept sites evenly along the chain rather than greedy first-fit. */
  spread?: boolean
  /** With ``spread``: skip residues within this distance of either chain terminus. */
  excludeTermini?: number
}

export interface CrosslinkSelection {
  sites: CrosslinkSite[]
  /** 1-based positions kept, comma-joined (for form/CSV). */
  csv: string
  /** Human-readable summary (used in the form's result area). */
  summary: string
}

const AA1_TO_AA3: Record<string, string> = {
  A: "ALA", R: "ARG", N: "ASN", D: "ASP", C: "CYS",
  Q: "GLN", E: "GLU", G: "GLY", H: "HIS", I: "ILE",
  L: "LEU", K: "LYS", M: "MET", F: "PHE", P: "PRO",
  S: "SER", T: "THR", W: "TRP", Y: "TYR", V: "VAL",
  U: "SEC", O: "PYL",
}

const VALID_TARGETS = new Set(Object.keys(AA1_TO_AA3))

/**
 * Return every sequence position whose residue is among ``targets``.
 * Positions are 1-based; unknown characters are skipped.
 */
export function findResiduePositions(sequence: string, targets: string[]): CrosslinkSite[] {
  const wanted = new Set(targets.map(t => t.toUpperCase()).filter(t => VALID_TARGETS.has(t)))
  const result: CrosslinkSite[] = []
  for (let i = 0; i < sequence.length; i++) {
    const res = sequence[i].toUpperCase()
    if (!wanted.has(res)) continue
    result.push({ position: i + 1, residue: res, residueName: AA1_TO_AA3[res] })
  }
  return result
}

/**
 * Thin a candidate list to a well-spaced subset.
 *
 * With ``spread`` enabled the sites are distributed evenly along the chain:
 * target positions are laid out uniformly over the non-excluded segment and
 * each target snaps to the nearest candidate residue.  This reproduces the
 * template's core-Tyr scheme (one junction every ~51 residues).  Otherwise a
 * greedy scan keeps a site whenever it is at least ``minSpacing`` residues
 * away from the previous kept one.  When a ``maxCount`` is set it bounds the
 * result in either mode.
 */
function thinSites(
  candidates: CrosslinkSite[],
  sequence: string,
  options: CrosslinkSelectionOptions,
): CrosslinkSite[] {
  const { maxCount, minSpacing = 0, spread = false, excludeTermini = 0 } = options
  if (spread) {
    const count = maxCount != null ? Math.max(1, Math.min(maxCount, candidates.length)) : candidates.length
    const lo = Math.max(1, 1 + excludeTermini)
    const hi = Math.max(lo, sequence.length - excludeTermini)
    const chosen: CrosslinkSite[] = []
    const used = new Set<number>()
    for (let k = 0; k < count; k++) {
      const target = lo + ((hi - lo + 1) * (k + 1)) / (count + 1)
      let best: CrosslinkSite | null = null
      let bestDist = Infinity
      for (const cand of candidates) {
        if (used.has(cand.position)) continue
        const dist = Math.abs(cand.position - target)
        if (chosen.length === 0 && dist < bestDist) {
          best = cand; bestDist = dist
        } else if (chosen.length > 0 && dist < bestDist) {
          best = cand; bestDist = dist
        }
      }
      if (best) {
        used.add(best.position)
        chosen.push(best)
      }
    }
    if (minSpacing > 1) {
      return greedyThin(chosen.sort((a, b) => a.position - b.position), minSpacing, maxCount)
    }
    return chosen.sort((a, b) => a.position - b.position)
  }
  return greedyThin(candidates, minSpacing, maxCount)
}

function greedyThin(
  candidates: CrosslinkSite[],
  minSpacing: number,
  maxCount?: number,
): CrosslinkSite[] {
  const kept: CrosslinkSite[] = []
  const spacing = Math.max(0, minSpacing)
  for (const cand of candidates) {
    const last = kept[kept.length - 1]
    if (last && cand.position - last.position < spacing) continue
    kept.push(cand)
    if (maxCount != null && kept.length >= maxCount) break
  }
  return kept
}

/**
 * Select crosslink sites from a sequence at the requested residues.
 *
 * Example
 * -------
 * selectCrosslinkSites("KLGYIEFYKVEK...", { targets: ["Y"], maxCount: 10, spread: true })
 * returns ~10 Tyr positions spread roughly evenly along the chain.
 */
export function selectCrosslinkSites(sequence: string, options: CrosslinkSelectionOptions): CrosslinkSelection {
  const candidates = findResiduePositions(sequence, options.targets)
  const sites = thinSites(candidates, sequence, options)
  const csv = sites.map(s => s.position).join(",")
  const unique = new Set(sites.map(s => s.residueName)).size
  const summary = sites.length === 0
    ? "No candidate residues found"
    : `${sites.length} site(s) at ${[...new Set(sites.map(s => s.residueName))].join("/")}`
      + ` (${unique} residue type${unique === 1 ? "" : "s"}), 1-based: ${csv}`
  return { sites, csv, summary }
}