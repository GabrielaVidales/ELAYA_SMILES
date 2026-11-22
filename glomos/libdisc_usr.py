"""
libdisc_usr.py — discrimination of (near-)duplicate conformers with USR.

USR = Ultrafast Shape Recognition (Ballester & Richards, Proc. R. Soc. A 2007 /
J. Comput. Chem. 2007, 28, 1711).  For each structure the distribution of
atom distances to four reference points is summarised by three moments
(mean, standard deviation, cube root of the third central moment), giving 12
descriptors expressed in angstrom. Two structures are *duplicates* when

    1/(1 + mean|Δdescriptor|) >= tol_similarity     AND     |ΔE| <= tol_energy

USR depends only on interatomic distances, so it is invariant to rotation,
translation, atom permutation of identical atoms *and* reflection: mirror-image
conformers (e.g. gauche+/gauche-) are merged into one family, which is what one
wants for an energy-ranked conformer list.

Changes with respect to the original version
--------------------------------------------
* numba is **no longer required**. The original ``@njit`` kernels had no
  ``cache=True`` so every GLOMOS run paid 10-40 s of JIT compilation, and numba
  was only installed transitively (via dscribe -> sparse) in the Docker image.
  Molecules are small, so plain vectorised numpy is faster end-to-end.
* The descriptor now uses (mean, SD, cbrt-skewness) — all in Å — instead of
  (variance, third moment) whose units differ (Å² and Å³), which made the
  similarity threshold mean different things for different features.
* ``filter_against_reference_usr`` ignored its ``mono`` argument (always 8
  features while the deduplication used 16). One descriptor is used now.
"""
import time
import numpy as np
from scipy.spatial import cKDTree
from glomos.libutils import sort_by_energy

tolsij = 0.95
tolene = 0.10      # kcal/mol


# --- USR descriptor ------------------------------------------------------------
def _moments(d):
    mu = d.mean()
    c = d - mu
    m2 = np.mean(c ** 2)
    m3 = np.mean(c ** 3)
    return mu, np.sqrt(m2), np.cbrt(m3)


def usr_descriptor(pos):
    """12 USR descriptors (Å) of one structure given as an (N, 3) array."""
    pos = np.asarray(pos, dtype=float)
    ctd = pos.mean(axis=0)
    d_ctd = np.linalg.norm(pos - ctd, axis=1)
    cst = pos[int(np.argmin(d_ctd))]
    fct = pos[int(np.argmax(d_ctd))]
    d_fct = np.linalg.norm(pos - fct, axis=1)
    ftf = pos[int(np.argmax(d_fct))]
    out = []
    for ref in (ctd, cst, fct, ftf):
        out.extend(_moments(np.linalg.norm(pos - ref, axis=1)))
    return np.array(out, dtype=float)


def compute_usr(lista_atoms, mode="usr", dtype=np.float64):
    """(M, 12) matrix of USR descriptors. ``mode`` is kept for API compatibility."""
    X = np.empty((len(lista_atoms), 12), dtype=np.float64)
    for k, at in enumerate(lista_atoms):
        X[k] = usr_descriptor(at.get_positions())
    return X.astype(dtype, copy=False)


def usr_similarity(a, b):
    """USR similarity in (0, 1] between two descriptor vectors."""
    return 1.0 / (1.0 + float(np.mean(np.abs(np.asarray(a) - np.asarray(b)))))


def _dmax(D, sim):
    # similarity >= sim  <=>  sum|Δ| <= D * (1 - sim) / sim
    return D * (1.0 - sim) / sim


# --- Filters ---------------------------------------------------------------------
def filtro_est(lista_atoms, sim=tolsij, dE_max=None, mode="usr", dtype=np.float64):
    """Drop structures that duplicate a lower-energy one. Returns energy-sorted list."""
    lista_sorted = sort_by_energy(lista_atoms, 1)
    if len(lista_sorted) <= 1:
        return lista_sorted
    E = np.array([float(a.info["e"]) for a in lista_sorted], dtype=np.float64)
    X = compute_usr(lista_sorted, mode=mode, dtype=dtype)
    keep = filtro_kdtree(X, E, _dmax(X.shape[1], sim), dE_max)
    return [lista_sorted[i] for i in np.nonzero(keep)[0]]


def filtro_kdtree(X, E, dmax, dE_max):
    """Boolean keep-mask; the lower-energy member of each duplicate pair survives."""
    X = np.asarray(X, dtype=np.float64, order="C")
    E = np.asarray(E, dtype=np.float64)
    N = X.shape[0]
    tree = cKDTree(X)
    keep = np.ones(N, dtype=bool)
    for i in range(N):
        if not keep[i]:
            continue
        for j in tree.query_ball_point(X[i], r=dmax, p=1):
            if j <= i:
                continue
            if dE_max is None or abs(E[j] - E[i]) <= dE_max:
                keep[j] = False
    return keep


def filtro_kdtree_ref_search(X_ref, E_ref, X_search, E_search, dmax, dE_max=None):
    """Keep-mask for ``X_search``: False when a reference structure duplicates it."""
    X_ref = np.asarray(X_ref, dtype=np.float64, order="C")
    X_search = np.asarray(X_search, dtype=np.float64, order="C")
    M = X_search.shape[0]
    keep = np.ones(M, dtype=bool)
    if X_ref.shape[0] == 0:
        return keep
    tree = cKDTree(X_ref)
    for i in range(M):
        for j in tree.query_ball_point(X_search[i], r=dmax, p=1):
            if dE_max is None or abs(E_ref[j] - E_search[i]) <= dE_max:
                keep[i] = False
                break
    return keep


def filtro_est_ref_search(ref_atoms, search_atoms, sim=tolsij, dE_max=None, mode="usr", dtype=np.float64):
    if len(search_atoms) == 0:
        return []
    X_ref = compute_usr(ref_atoms, mode=mode, dtype=dtype)
    X_sea = compute_usr(search_atoms, mode=mode, dtype=dtype)
    E_ref = np.array([float(a.info["e"]) for a in ref_atoms], dtype=np.float64)
    E_sea = np.array([float(a.info["e"]) for a in search_atoms], dtype=np.float64)
    keep = filtro_kdtree_ref_search(X_ref, E_ref, X_sea, E_sea, _dmax(X_sea.shape[1], sim), dE_max)
    return [a for a, k in zip(search_atoms, keep) if k]


# --- Public entry points used by the GA ----------------------------------------------
def deduplicate_by_usr(lista_atoms, tols=tolsij, tole=tolene, mono=False, flag=1):
    """Remove duplicates inside one list (similar shape AND |ΔE| <= tole kcal/mol)."""
    if len(lista_atoms) == 0:
        return []
    start = time.time()
    ni = len(lista_atoms)
    out = filtro_est(lista_atoms, sim=tols, dE_max=tole)
    if flag == 1:
        print('USR comparison at    %5.2f s [%d -> %d]' % (time.time() - start, ni, len(out)))
    return out


def filter_against_reference_usr(moleculein, moleculeref, tols=tolsij, tole=tolene, mono=False, flag=1):
    """Remove from ``moleculein`` anything already represented in ``moleculeref``."""
    if len(moleculein) == 0:
        return []
    start = time.time()
    ni = len(moleculein)
    out = filtro_est_ref_search(moleculeref, moleculein, sim=tols, dE_max=tole)
    if flag == 1:
        print('USR comparison     at %5.2f s [%d -> %d]' % (time.time() - start, ni, len(out)))
    return out
