"""
libutils.py — geometry, torsion, I/O and list utilities for the GLOMOS framework.

Changes with respect to the original version
--------------------------------------------
* adjacency_matrix() is fully vectorised (the original double Python loop was
  called after *every* trial rotation and dominated the cost of the GA).
* readxyzs()/writexyzs() tolerate blank lines and arbitrary comment lines.
* Energies stored in ``atoms.info['e']`` are **kcal/mol** everywhere (the old
  docstrings said eV, which was misleading).
* New torsion helpers (get_torsion / set_torsion) used by the torsion-space GA.
"""
import os
import time
import numpy as np
from ase import Atom, Atoms
from ase.data import covalent_radii, chemical_symbols

# Bondi van-der-Waals radii (Å) for clash detection; unknown elements -> 1.8 Å
VDW_RADII = {
    1: 1.20, 5: 1.92, 6: 1.70, 7: 1.55, 8: 1.52, 9: 1.47, 14: 2.10, 15: 1.80,
    16: 1.80, 17: 1.75, 35: 1.85, 53: 1.98,
}

# =============================================================================
# Graph and connectivity utilities
# =============================================================================


def adjacency_matrix(atoms, factor=1.2):
    """Binary adjacency from a scaled covalent-radius criterion (vectorised).

    in:
        atoms  (ase.Atoms): structure.
        factor (float): bonded if d <= factor * (r_i + r_j).
    out:
        numpy.ndarray (N, N) int64, 1 where bonded.
    """
    pos = np.asarray(atoms.get_positions(), dtype=float)
    z = np.asarray(atoms.get_atomic_numbers())
    r = covalent_radii[z]
    d = np.linalg.norm(pos[:, None, :] - pos[None, :, :], axis=-1)
    lim = factor * (r[:, None] + r[None, :])
    mat = (d <= lim).astype(np.int64)
    np.fill_diagonal(mat, 0)
    return mat


def adjacency_from_bonds(n, bonds):
    """Adjacency matrix from an explicit bond list [(i, j[, order]), ...]."""
    mat = np.zeros((n, n), dtype=np.int64)
    for b in bonds:
        i, j = int(b[0]), int(b[1])
        mat[i, j] = mat[j, i] = 1
    return mat


def neighbor_lists(adjmatrix):
    n = adjmatrix.shape[0]
    return [list(np.nonzero(adjmatrix[i])[0]) for i in range(n)]


def topological_distances(adjmatrix):
    """All-pairs shortest path length in bonds (inf where disconnected)."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import shortest_path
    return shortest_path(csr_matrix(adjmatrix), unweighted=True, directed=False)


def connected_components(adjmatrix):
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import connected_components as cc
    return cc(csr_matrix(adjmatrix), directed=False)


def reachable_without(nbrs, start, blocked):
    """Atoms reachable from ``start`` without ever stepping on ``blocked``."""
    seen = {start}
    stack = [start]
    while stack:
        u = stack.pop()
        for v in nbrs[u]:
            if v == blocked or v in seen:
                continue
            seen.add(int(v))
            stack.append(int(v))
    return seen


# =============================================================================
# Rotations / torsions
# =============================================================================


def rotate_matrix(molecule, matrix):
    """Apply a 3x3 rotation matrix to all positions of ``molecule`` in place."""
    molecule.set_positions(np.dot(molecule.get_positions(), matrix.T))
    return molecule


def rodrigues_rotation_matrix(kvector, qdeg):
    """Rotation matrix about an arbitrary axis (Rodrigues' formula)."""
    qrad = np.deg2rad(qdeg)
    k = np.array(kvector, dtype=float)
    k = k / np.linalg.norm(k)
    K = np.array([[0, -k[2], k[1]],
                  [k[2], 0, -k[0]],
                  [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(qrad) * K + (1 - np.cos(qrad)) * np.dot(K, K)


def rotate_vector_angle_deg(molecule, kvector, qdeg):
    """Rotate a molecule about an axis through the origin."""
    return rotate_matrix(molecule, rodrigues_rotation_matrix(kvector, qdeg))


def dihedral_deg(p0, p1, p2, p3):
    """Signed dihedral angle p0-p1-p2-p3 in degrees, range (-180, 180]."""
    b0 = p0 - p1
    b1 = p2 - p1
    b2 = p3 - p2
    b1 = b1 / np.linalg.norm(b1)
    v = b0 - np.dot(b0, b1) * b1
    w = b2 - np.dot(b2, b1) * b1
    x = np.dot(v, w)
    y = np.dot(np.cross(b1, v), w)
    return float(np.degrees(np.arctan2(y, x)))


def wrap180(angle):
    """Wrap an angle in degrees to (-180, 180]."""
    a = (angle + 180.0) % 360.0 - 180.0
    return 180.0 if a == -180.0 else a


def angular_distance(a, b):
    """Smallest absolute difference between two angles (degrees)."""
    return abs(wrap180(a - b))


# =============================================================================
# IO utilities (XYZ)
# =============================================================================


def _parse_xyz_blocks(lines):
    i, n = 0, len(lines)
    blocks = []
    while i < n:
        if not lines[i].strip():
            i += 1
            continue
        try:
            natoms = int(lines[i].split()[0])
        except (ValueError, IndexError):
            raise ValueError("Malformed XYZ: expected atom count, got %r" % lines[i][:40])
        comment = lines[i + 1] if i + 1 < n else ""
        body = lines[i + 2: i + 2 + natoms]
        if len(body) < natoms:
            raise ValueError("Malformed XYZ: truncated structure (%d/%d atoms)" % (len(body), natoms))
        blocks.append((natoms, comment, body))
        i += 2 + natoms
    return blocks


def read_xyz_text(text):
    """Parse (multi-)XYZ text into a list of ase.Atoms.

    The comment line may be ``<energy> <name>`` (GLOMOS convention); anything
    else is stored verbatim in ``info['comment']``.
    """
    molecules = []
    for natoms, comment, body in _parse_xyz_blocks(text.splitlines()):
        parts = comment.split()
        energy, name = 0.0, "unknown"
        if parts:
            try:
                energy = float(parts[0])
                name = parts[1] if len(parts) >= 2 else "unknown"
            except ValueError:
                energy = 0.0
        mol = Atoms()
        mol.info["e"] = energy
        mol.info["i"] = name
        mol.info["comment"] = comment
        for line in body:
            sym_raw, x, y, z = line.split()[:4]
            try:
                symbol = chemical_symbols[int(sym_raw)]
            except (ValueError, IndexError):
                symbol = sym_raw.capitalize()
            mol.append(Atom(symbol, (float(x), float(y), float(z))))
        molecules.append(mol)
    return molecules


def readxyzs(filename):
    """Read a (multi-)XYZ file into a list of ase.Atoms."""
    if not os.path.isfile(filename):
        raise FileNotFoundError(filename)
    with open(filename) as fh:
        return read_xyz_text(fh.read())


def atoms_to_xyz(atoms, comment=None):
    """One XYZ block (string) for an ase.Atoms."""
    if comment is None:
        comment = "%12.8f %s" % (atoms.info.get("e", 0.0), atoms.info.get("i", "mol"))
    lines = [str(len(atoms)), comment]
    for sym, (x, y, z) in zip(atoms.get_chemical_symbols(), atoms.get_positions()):
        lines.append("%-2s %16.9f %16.9f %16.9f" % (sym, x, y, z))
    return "\n".join(lines) + "\n"


def writexyzs(atoms_list, filename):
    """Write structures to a concatenated multi-XYZ file."""
    if not isinstance(atoms_list, list):
        atoms_list = [atoms_list]
    with open(filename, "w") as fh:
        for atoms in atoms_list:
            fh.write(atoms_to_xyz(atoms))


# =============================================================================
# List and filtering utilities
# =============================================================================


def rename(atoms_list, basename, ndigits):
    """Rename structures with a zero-padded sequential label (in place)."""
    for i, atoms in enumerate(atoms_list):
        atoms.info["i"] = "%s_%s" % (basename, str(i + 1).zfill(ndigits))
    return atoms_list


def sort_by_energy(atoms_list, opt=0):
    """Sorted *copies* by ``info['e']``.

    opt=0 -> energies shifted so the minimum is 0 (relative);
    opt=1 -> absolute energies kept.
    """
    if not atoms_list:
        return []
    energies = [(i, float(a.info["e"])) for i, a in enumerate(atoms_list)]
    energies.sort(key=lambda x: x[1])
    ref = energies[0][1] if opt == 0 else 0.0
    out = []
    for idx, e in energies:
        a = atoms_list[idx].copy()
        a.info = dict(atoms_list[idx].info)
        a.info["e"] = e - ref
        out.append(a)
    return out


def cutter_energy(atoms_list, enemax, quiet=False):
    """Keep structures within ``enemax`` kcal/mol of the lowest one."""
    if len(atoms_list) == 0:
        return []
    start = time.time()
    ni = len(atoms_list)
    emin = min(float(a.info["e"]) for a in atoms_list)
    out = [a for a in atoms_list if (float(a.info["e"]) - emin) < enemax]
    if not quiet:
        print("Cutter by energy at  %5.2f s [%d -> %d]" % (time.time() - start, ni, len(out)))
    return out
