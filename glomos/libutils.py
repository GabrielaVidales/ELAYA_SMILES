"""
libutils.py — Geometry, rotation, I/O, and list utilities for the glomos framework.
"""
import os
import time
import numpy as np
from ase import Atom, Atoms
from ase.data import covalent_radii, chemical_symbols

# =============================================================================
# Graph and connectivity utilities
# =============================================================================

def adjacency_matrix(atoms, factor=1.2):
    """Build a binary adjacency matrix based on scaled covalent-radius distance criterion.

    in:
        atoms (ase.Atoms): input structure.
        factor (float): distance scale factor relative to sum of covalent radii (default 1.2).
    out:
        numpy.ndarray: square integer matrix of shape (N, N); 1 if atoms are bonded, 0 otherwise.
    """
    n = len(atoms)
    mat = np.zeros((n, n), dtype=np.int64)

    for i in range(n):
        ri = covalent_radii[atoms[i].number]
        pi = atoms[i].position
        for j in range(i + 1, n):
            rj = covalent_radii[atoms[j].number]
            pj = atoms[j].position
            d = np.linalg.norm(pj - pi) / (ri + rj)
            if d <= factor:
                mat[i, j] = mat[j, i] = 1
    return mat



# =============================================================================
# Rotations
# =============================================================================


def rotate_matrix(molecule, matrix):
    """Apply a rotation matrix to all atomic positions of a molecule in-place.

    in:
        molecule (ase.Atoms): structure to rotate.
        matrix (numpy.ndarray): 3x3 rotation matrix.
    out:
        ase.Atoms: the same object with rotated positions.
    """
    molecule.set_positions(np.dot(molecule.get_positions(), matrix.T))
    return molecule


def rodrigues_rotation_matrix(kvector, qdeg):
    """Compute a rotation matrix for an arbitrary-axis rotation using Rodrigues' formula.

    in:
        kvector (array-like): rotation axis vector (need not be normalized).
        qdeg (float): rotation angle in degrees.
    out:
        numpy.ndarray: 3x3 rotation matrix.
    """
    qrad = np.deg2rad(qdeg)
    k = np.array(kvector, dtype=float)
    k /= np.linalg.norm(k)

    K = np.array([
        [0, -k[2], k[1]],
        [k[2], 0, -k[0]],
        [-k[1], k[0], 0]
    ])

    return np.eye(3) + np.sin(qrad) * K + (1 - np.cos(qrad)) * np.dot(K, K)


def rotate_vector_angle_deg(molecule, kvector, qdeg):
    """Rotate a molecule around an arbitrary axis by a given angle using Rodrigues' formula.

    in:
        molecule (ase.Atoms): structure to rotate.
        kvector (array-like): rotation axis vector.
        qdeg (float): rotation angle in degrees.
    out:
        ase.Atoms: the rotated structure.
    """
    return rotate_matrix(molecule, rodrigues_rotation_matrix(kvector, qdeg))


# =============================================================================
# IO utilities (XYZ)
# =============================================================================

def readxyzs(filename):
    """Read a concatenated multi-structure XYZ file into a list of Atoms objects.

    in:
        filename (str): path to the XYZ file containing one or more structures.
    out:
        list of ase.Atoms: structures with info['e'] (energy) and info['i'] (label) set from
            the comment line.
    """
    if not os.path.isfile(filename):
        raise FileNotFoundError(filename)
    molecules = []
    with open(filename) as fh:
        while True:
            line = fh.readline()
            if not line:
                break
            natoms = int(line.strip())
            comment = fh.readline().split()
            name = comment[1] if len(comment) >= 2 else "unknown"
            energy = float(comment[0]) if comment else 0.0
            mol = Atoms()
            mol.info["e"] = energy
            mol.info["i"] = name
            for _ in range(natoms):
                sym_raw, x, y, z = fh.readline().split()
                x, y, z = map(float, (x, y, z))
                try:
                    symbol = chemical_symbols[int(sym_raw)]
                except (ValueError, IndexError):
                    symbol = sym_raw.capitalize()
                mol.append(Atom(symbol, (x, y, z)))
            molecules.append(mol)
    return molecules

def writexyzs(atoms_list, filename):
    """Write a list of Atoms objects to a concatenated multi-structure XYZ file.

    in:
        atoms_list (list of ase.Atoms or ase.Atoms): structures to write; each must have
            info['e'] and info['i'].
        filename (str): output file path.
    out:
        None.
    """
    if not isinstance(atoms_list, list):
        atoms_list = [atoms_list]
    with open(filename, "w") as fh:
        for atoms in atoms_list:
            print(len(atoms), file=fh)
            print(f"{atoms.info['e']:12.8f} {atoms.info['i']}", file=fh)
            for atom in atoms:
                x, y, z = atom.position
                print(f"{atom.symbol:<2s} {x:16.9f} {y:16.9f} {z:16.9f}", file=fh)

# =============================================================================
# List and filtering utilities
# =============================================================================

def rename(atoms_list, basename, ndigits):
    """Rename structures in a list with a zero-padded sequential label.

    in:
        atoms_list (list of ase.Atoms): structures to rename in-place.
        basename (str): prefix for the new name.
        ndigits (int): zero-padding width for the sequential index.
    out:
        list of ase.Atoms: the same list with updated info['i'] labels.
    """
    for i, atoms in enumerate(atoms_list):
        atoms.info["i"] = f"{basename}_{str(i+1).zfill(ndigits)}"
    return atoms_list

def sort_by_energy(atoms_list, opt=0):
    """Sort structures by energy and return sorted copies.

    in:
        atoms_list (list Atoms): Structures, each with info['e'] (energy in eV).
        opt        (int)       : 0 → energies in the copies are shifted so the
                                     minimum is 0 (relative energies).
                                 1 → energies in the copies are kept as absolute
                                     values (no shift applied).
    out:
        Sorted list of deep copies.  Original objects are not modified.
        Returns [] if atoms_list is empty.
    """
    if not atoms_list:
        return []
    energies = [(i, a.info["e"]) for i, a in enumerate(atoms_list)]
    energies.sort(key=lambda x: x[1])
    ref = energies[0][1] if opt == 0 else 0.0
    out = []
    for idx, e in energies:
        a = atoms_list[idx].copy()
        a.info["e"] = e - ref
        out.append(a)
    return out

def cutter_energy(atoms_list, enemax):
    """Return structures whose energy is within enemax eV of the global minimum.
    
    in:
        atoms_list (list Atoms): Structures with info['e'] (absolute energy, eV).
        enemax     (float)     : Maximum energy window above the minimum (eV).
    out:
        Filtered list (subset of the original objects, not copies).
        Returns [] if atoms_list is empty.
    """
    if len(atoms_list)==0: return []
    start = time.time()
    ni=len(atoms_list)
    sorted_list = sort_by_energy(atoms_list, 1)
    emin = sorted_list[0].info["e"]
    moleculeout=[a for a in atoms_list if (a.info["e"] - emin) < enemax]
    nf=len(moleculeout)
    end = time.time()
    print('Cutter by energy at  %5.2f s [%d -> %d]' %(end - start, ni, nf))
    return moleculeout

