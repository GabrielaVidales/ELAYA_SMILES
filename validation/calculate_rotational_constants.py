#!/usr/bin/env python3
"""Rotational constants (A, B, C) from one or more XYZ structures.

    python validation/calculate_rotational_constants.py structure.xyz [more.xyz ...]
    python validation/calculate_rotational_constants.py conformers.xyz      # multi-XYZ is fine

Pure numpy (no RDKit needed). Most-abundant isotope masses, rigid rotor:
    B[MHz] = h / (8 pi^2 I)  with I the principal moments of inertia.
Output units: MHz, GHz and cm^-1, plus Ray's asymmetry parameter kappa.
Rigid-rotor constants of an equilibrium geometry differ from experimental B0 values by ~1-3 %
(vibrational averaging), see tests/test_chem_numpy.py for the reference checks (water, CO2, CH4).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import elaya_chem as ec  # noqa: E402


def split_xyz(text):
    lines = text.splitlines()
    i, out = 0, []
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        n = int(lines[i].split()[0])
        out.append("\n".join(lines[i:i + 2 + n]))
        i += 2 + n
    return out


def main(paths):
    if not paths:
        print(__doc__)
        return 1
    print("%-28s %-4s %12s %12s %12s  %s" % ("structure", "#", "A (GHz)", "B (GHz)", "C (GHz)", "top"))
    for p in paths:
        with open(p) as fh:
            blocks = split_xyz(fh.read())
        for k, blk in enumerate(blocks, 1):
            syms, pos = ec.parse_xyz(blk)
            c = ec.rotational_constants(syms, pos)
            f = lambda v: "%12.4f" % v if v is not None else "%12s" % "-"
            print("%-28s %-4d %s %s %s  %s" % (os.path.basename(p)[:28], k, f(c["A_GHz"]), f(c["B_GHz"]),
                                               f(c["C_GHz"]), c.get("top", "")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
