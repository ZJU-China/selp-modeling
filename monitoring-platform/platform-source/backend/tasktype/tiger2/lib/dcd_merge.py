"""Merge per-replica DCD segments (fresh run + resumed jobs) into one DCD.

NAMD writes a new DCD every time a job is (re)started, and the segments overlap
around the resume point. This module concatenates the raw charmm-style records
of all segments into a single DCD, skipping frames whose absolute simulation
step is already covered by a previous segment, so the merged file holds exactly
one frame per simulated cycle (e.g. 1124 frames instead of 400).

Runs under the system python3 (no numpy/MDAnalysis): frame records are copied
verbatim and only the frame count in the header is rewritten. The non-frame
records (title, natoms) are copied once from the first segment so readers that
parse the standard DCD layout keep working.
"""
import os, math, struct

HEADER_LEN = 84
FIXED_BLOCK_LEN = 48  # charmm unit-cell block (6 doubles)

# Upper bound of frames served to the MD-trajectory viewer. Trajectories
# longer than this are downsampled to a preview DCD (every k-th frame) so the
# browser loads a few MB instead of the full multi-hundred-MB merged file.
PREVIEW_MAX_FRAMES = 120

# Number of trailing frames/cycles kept for the "last N cycles" trajectory in
# the convergence section (one DCD frame == one simulated cycle). Must match
# convergence_check.RECENT_WINDOW so the tail window equals the analysed
# recent window.
TAIL_WINDOW_CYCLES = 100


def read_records(path):
    """Read all (length, body) records of a DCD file in order."""
    records = []
    with open(path, "rb") as fh:
        while True:
            head = fh.read(4)
            if not head:
                break
            n = struct.unpack("<i", head)[0]
            body = fh.read(n)
            tail = fh.read(4)
            if len(body) != n:
                break
            records.append((n, body))
    return records


def _nframes(records):
    # body[0:4] = "CORD", body[4:8] = nframes
    return struct.unpack("<i", records[0][1][4:8])[0]


def _istart(records):
    # body[8:12] = istart (absolute step of frame 0)
    return struct.unpack("<i", records[0][1][8:12])[0]


def _coord_len(records):
    """Length (bytes) of a coordinate record = 4*natoms.

    Coordinate blocks appear 3x per frame and are the most frequent records,
    so natoms is the most common record length / 4.
    """
    counts: "dict[int, int]" = {}
    for n, _body in records[1:]:
        if n > 0 and n % 4 == 0:
            counts[n] = counts.get(n, 0) + 1
    if not counts:
        raise ValueError("no coordinate records found in DCD")
    return max(counts, key=lambda k: counts[k])


def _is_charmm(records, coord_len):
    """True if frames carry a 48-byte fixed (unit-cell) block first."""
    for n, _body in records[1:]:
        if n == FIXED_BLOCK_LEN or n == coord_len:
            return n == FIXED_BLOCK_LEN
    return False


def _log_first_steps(logs_dir):
    """Absolute step of the first ENERGY record of every synced log (sorted)."""
    first_steps = []
    if logs_dir and os.path.isdir(logs_dir):
        for fname in sorted(os.listdir(logs_dir)):
            if not fname.endswith(".log"):
                continue
            first = None
            try:
                with open(os.path.join(logs_dir, fname), errors="replace") as fh:
                    for line in fh:
                        if line.startswith("ENERGY:"):
                            parts = line.split()
                            if len(parts) >= 2:
                                try:
                                    first = int(parts[1])
                                except ValueError:
                                    first = None
                            break
            except OSError:
                continue
            if first is not None:
                first_steps.append(first)
    return sorted(first_steps)


def _base_steps(segments, logs_dir, nsavc):
    """Per-segment absolute step of frame 0.

    Segment 0 is the original run: its DCD istart already is the step of its
    first frame (one cycle in). Later segments start where their log's first
    ENERGY record says; when the log is missing, chain from the previous
    segment's last kept step.
    """
    first_steps = _log_first_steps(logs_dir)
    base_steps = []
    last_kept = float("-inf")
    for j, seg in enumerate(segments):
        recs = read_records(seg)
        istart = _istart(recs)
        nf = _nframes(recs)
        if j == 0:
            base = istart
        elif j < len(first_steps):
            base = first_steps[j]
        else:
            base = last_kept + nsavc
        base_steps.append(base)
        last_kept = base + (nf - 1) * nsavc
    return base_steps


def merge_segments(segments, logs_dir, out_path, steps_per_cycle=15000):
    """Merge `segments` (paths, ordered by job) into `out_path`.

    Returns {"frames": int, "segments": [{"path","frames","baseStep","kept"}]}.
    """
    if not segments:
        raise ValueError("no DCD segments to merge")

    nsavc = int(steps_per_cycle)
    if nsavc <= 0:
        nsavc = 15000

    base_steps = _base_steps(segments, logs_dir, nsavc)

    # header + prelude records come from the first segment
    first_recs = read_records(segments[0])
    header_body = bytearray(first_recs[0][1])
    coord_len_0 = _coord_len(first_recs)
    prelude = []
    for n, body in first_recs[1:]:
        if n != FIXED_BLOCK_LEN and n != coord_len_0:
            prelude.append((n, body))

    out_nframes = 0
    kept = []
    last_kept_step = float("-inf")
    per_seg = []

    for j, seg in enumerate(segments):
        recs = read_records(seg)
        nf = _nframes(recs)
        coord_len = _coord_len(recs)
        if coord_len != coord_len_0:
            raise ValueError(
                f"segment {j} natoms mismatch ({coord_len // 4} vs {coord_len_0 // 4})"
            )
        charmm = _is_charmm(recs, coord_len)
        frame_size = 4 if charmm else 3

        frame_recs = []
        coords = 0
        seg_kept = 0
        base = base_steps[j]
        step = base
        for n, body in recs[1:]:
            if n != FIXED_BLOCK_LEN and n != coord_len:
                continue
            frame_recs.append((n, body))
            if n == coord_len:
                coords += 1
                if coords == frame_size:
                    if step > last_kept_step:
                        kept.append(frame_recs)
                        last_kept_step = step
                        out_nframes += 1
                        seg_kept += 1
                    frame_recs = []
                    coords = 0
                    step += nsavc
        per_seg.append({
            "path": os.path.basename(seg),
            "frames": nf,
            "baseStep": base,
            "kept": seg_kept,
        })

    struct.pack_into("<i", header_body, 4, out_nframes)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(struct.pack("<i", HEADER_LEN))
        fh.write(header_body)
        fh.write(struct.pack("<i", HEADER_LEN))
        for n, body in prelude:
            fh.write(struct.pack("<i", n))
            fh.write(body)
            fh.write(struct.pack("<i", n))
        for frame in kept:
            for n, body in frame:
                fh.write(struct.pack("<i", n))
                fh.write(body)
                fh.write(struct.pack("<i", n))

    return {"frames": out_nframes, "segments": per_seg}


def _split_frames(records, coord_len, frame_size):
    """Group the frame records of a DCD into per-frame record lists."""
    frames = []
    frame_recs = []
    coords = 0
    for n, body in records[1:]:
        if n != FIXED_BLOCK_LEN and n != coord_len:
            continue
        frame_recs.append((n, body))
        if n == coord_len:
            coords += 1
            if coords == frame_size:
                frames.append(frame_recs)
                frame_recs = []
                coords = 0
    return frames


def subsample_dcd(src, out_path, max_frames=PREVIEW_MAX_FRAMES):
    """Write a downsampled copy of a DCD holding at most `max_frames` frames.

    Keeps the first frame plus every k-th frame (k = ceil(nframes/max_frames))
    so the preview spans the whole run while staying small enough to stream to
    a browser. Pure stdlib record-level copy; the header/prelude come verbatim
    from the source and only the frame count is rewritten.

    Returns {"frames": int, "downsampled": bool, "sourceFrames": int}.
    """
    recs = read_records(src)
    nf = _nframes(recs)
    if nf <= 0:
        raise ValueError("DCD contains no frames")

    if nf <= max_frames:
        # Already small enough: byte-for-byte copy, no downsampling.
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(src, "rb") as src_fh, open(out_path, "wb") as out_fh:
            out_fh.write(src_fh.read())
        return {"frames": nf, "downsampled": False, "sourceFrames": nf}

    coord_len = _coord_len(recs)
    charmm = _is_charmm(recs, coord_len)
    frame_size = 4 if charmm else 3
    frames = _split_frames(recs, coord_len, frame_size)

    step = max(1, math.ceil(nf / max_frames))
    kept = frames[::step]
    out_nframes = len(kept)

    header_body = bytearray(recs[0][1])
    struct.pack_into("<i", header_body, 4, out_nframes)
    prelude = [
        (n, body) for n, body in recs[1:]
        if n != FIXED_BLOCK_LEN and n != coord_len
    ]

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(struct.pack("<i", HEADER_LEN))
        fh.write(header_body)
        fh.write(struct.pack("<i", HEADER_LEN))
        for n, body in prelude:
            fh.write(struct.pack("<i", n))
            fh.write(body)
            fh.write(struct.pack("<i", n))
        for frame in kept:
            for n, body in frame:
                fh.write(struct.pack("<i", n))
                fh.write(body)
                fh.write(struct.pack("<i", n))

    return {"frames": out_nframes, "downsampled": True, "sourceFrames": nf}


def tail_dcd(src, out_path, n_frames=TAIL_WINDOW_CYCLES):
    """Write the last `n_frames` frames of a merged DCD (one frame = one cycle).

    Kept frame records are copied verbatim and only the header is rewritten
    (frame count and istart, so the tail file's start step is the first frame
    it actually contains). If the source holds fewer frames than the window,
    the whole file is copied byte-for-byte.

    Returns {"frames": int, "truncated": bool, "sourceFrames": int}.
    """
    recs = read_records(src)
    nf = _nframes(recs)
    if nf <= 0:
        raise ValueError("DCD contains no frames")

    if nf <= n_frames:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(src, "rb") as src_fh, open(out_path, "wb") as out_fh:
            out_fh.write(src_fh.read())
        return {"frames": nf, "truncated": False, "sourceFrames": nf}

    coord_len = _coord_len(recs)
    charmm = _is_charmm(recs, coord_len)
    frame_size = 4 if charmm else 3
    frames = _split_frames(recs, coord_len, frame_size)
    kept = frames[-n_frames:]
    out_nframes = len(kept)

    header_body = bytearray(recs[0][1])
    struct.pack_into("<i", header_body, 4, out_nframes)
    # body[8:12] = ISTART, body[12:16] = NSAVC (steps between frames): shift
    # istart forward so it points at the first frame of the tail window.
    istart = struct.unpack("<i", header_body[8:12])[0]
    nsavc = struct.unpack("<i", header_body[12:16])[0]
    struct.pack_into("<i", header_body, 8, istart + (nf - out_nframes) * nsavc)
    prelude = [
        (n, body) for n, body in recs[1:]
        if n != FIXED_BLOCK_LEN and n != coord_len
    ]

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(struct.pack("<i", HEADER_LEN))
        fh.write(header_body)
        fh.write(struct.pack("<i", HEADER_LEN))
        for n, body in prelude:
            fh.write(struct.pack("<i", n))
            fh.write(body)
            fh.write(struct.pack("<i", n))
        for frame in kept:
            for n, body in frame:
                fh.write(struct.pack("<i", n))
                fh.write(body)
                fh.write(struct.pack("<i", n))

    return {"frames": out_nframes, "truncated": True, "sourceFrames": nf}
