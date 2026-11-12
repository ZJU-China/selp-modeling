"""Small output helpers shared by the analysis modules."""
import json


def write_dat(path, header, rows):
    """Tab-separated data file: a `# <header>` comment line then one row per
    line. `header` includes the column names and units, e.g.
    "replica step rg(A)". `rows` is an iterable of tuples of numbers/strings.
    """
    with open(path, "w") as f:
        f.write("# " + header + "\n")
        for row in rows:
            f.write("\t".join("" if v is None else str(v) for v in row) + "\n")


def write_tsv(path, rows):
    """Generic tab-separated file (first row may be a header)."""
    with open(path, "w") as f:
        for row in rows:
            f.write("\t".join("" if v is None else str(v) for v in row) + "\n")


def write_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, ensure_ascii=False)


def count_rows(path):
    """Number of data rows (non-blank, non-comment)."""
    try:
        with open(path) as f:
            return sum(1 for line in f if line.strip() and not line.startswith("#"))
    except OSError:
        return 0