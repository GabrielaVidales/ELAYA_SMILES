import time
import math
import numpy as np
from scipy.spatial import cKDTree
from numba import njit, prange
from ase.data import atomic_masses
from glomos.libutils import sort_by_energy
tolsij=0.95
tolene=0.10
#--- USR ----------------------------------------------------------------------
def compute_usr(lista_atoms, mode="mono", dtype=np.float32):
    """Compute the USR descriptor vectors for a list of Atoms objects.

    in:
        lista_atoms (list of ase.Atoms): structures to describe.
        mode (str): 'mono' for 8 geometry-only features or 'multi' for 16 features
            (geometry + mass-weighted).
        dtype (numpy.dtype): output data type (default numpy.float32).
    out:
        numpy.ndarray: matrix of shape (M, 8) or (M, 16) with one descriptor row per
            structure.
    """
    pos_cat, masses, offsets = pack_atoms_list(lista_atoms)
    M = offsets.shape[0] - 1

    if mode == "mono":
        X = np.empty((M, 8), dtype=np.float64)
        usr_batch12(pos_cat, offsets, X)
    else:
        X = np.empty((M, 16), dtype=np.float64)
        usr_batch24(pos_cat, masses, offsets, X)

    return X.astype(dtype, copy=False)


def pack_atoms_list(lista_atoms):
    """Pack a list of Atoms objects into contiguous arrays for batch Numba processing.

    in:
        lista_atoms (list of ase.Atoms): structures to pack.
    out:
        tuple: (pos_cat, masses, offsets) where pos_cat is an (N_total, 3) float64 array
            of all positions, masses is a (N_total,) array of atomic masses, and offsets
            is an (M+1,) int64 array of structure start indices.
    """
    M = len(lista_atoms)
    counts  = np.fromiter((len(a) for a in lista_atoms), dtype=np.int64, count=M)
    offsets = np.zeros(M + 1, dtype=np.int64)
    np.cumsum(counts, out=offsets[1:])
    totalN = int(offsets[-1])

    pos_cat = np.empty((totalN, 3), dtype=np.float64)
    masses  = np.empty(totalN, dtype=np.float64)

    p = 0
    for at in lista_atoms:
        n = len(at)
        pos_cat[p:p+n, :] = at.get_positions()
        Z = at.get_atomic_numbers()
        masses[p:p+n] = atomic_masses[Z]
        p += n

    return pos_cat, masses, offsets


@njit(fastmath=True)
def four_points(pos):
    """Find the four USR reference points: centroid, closest-to-centroid, farthest-from-centroid, and farthest-from-farthest.

    in:
        pos (numpy.ndarray): (N, 3) array of atomic positions (Numba-accelerated).
    out:
        tuple of 12 floats: coordinates of the four reference points (ctd, cst, fct, ftf)
            as x, y, z triples.
    """
    n = pos.shape[0]

    ctd0 = 0.0; ctd1 = 0.0; ctd2 = 0.0
    for i in range(n):
        ctd0 += pos[i, 0]
        ctd1 += pos[i, 1]
        ctd2 += pos[i, 2]
    invn = 1.0 / n
    ctd0 = ctd0 * invn; ctd1 = ctd1 * invn; ctd2 = ctd2 * invn

    i_cst = 0; i_fct = 0
    dmin = math.inf
    dmax = -math.inf
    for i in range(n):
        dx = pos[i, 0] - ctd0
        dy = pos[i, 1] - ctd1
        dz = pos[i, 2] - ctd2
        di = math.sqrt(dx*dx + dy*dy + dz*dz)
        if di < dmin:
            dmin = di; i_cst = i
        if di > dmax:
            dmax = di; i_fct = i

    cst0, cst1, cst2 = pos[i_cst, 0], pos[i_cst, 1], pos[i_cst, 2]
    fct0, fct1, fct2 = pos[i_fct, 0], pos[i_fct, 1], pos[i_fct, 2]

    i_ftf = 0
    dmax2 = -math.inf
    for i in range(n):
        dx = pos[i, 0] - fct0
        dy = pos[i, 1] - fct1
        dz = pos[i, 2] - fct2
        di = math.sqrt(dx*dx + dy*dy + dz*dz)
        if di > dmax2:
            dmax2 = di; i_ftf = i

    ftf0, ftf1, ftf2 = pos[i_ftf, 0], pos[i_ftf, 1], pos[i_ftf, 2]
    return (ctd0, ctd1, ctd2,
            cst0, cst1, cst2,
            fct0, fct1, fct2,
            ftf0, ftf1, ftf2)


@njit(fastmath=True)
def moments_point(pos, p0, p1, p2):
    """Compute the variance and third moment of atomic distances from a reference point.

    in:
        pos (numpy.ndarray): (N, 3) array of atomic positions.
        p0, p1, p2 (float): coordinates of the reference point.
    out:
        tuple of 2 floats: (variance, third_moment) of the distance distribution
            around the reference point.
    """
    n = pos.shape[0]

    s1 = 0.0
    for i in range(n):
        dx = pos[i,0]-p0; dy = pos[i,1]-p1; dz = pos[i,2]-p2
        d  = math.sqrt(dx*dx + dy*dy + dz*dz)
        s1 += d
    mu = s1 / n

    m2 = 0.0; m3 = 0.0
    for i in range(n):
        dx = pos[i,0]-p0; dy = pos[i,1]-p1; dz = pos[i,2]-p2
        d  = math.sqrt(dx*dx + dy*dy + dz*dz)
        r  = d - mu
        r2 = r*r
        m2 += r2
        m3 += r2*r

    return m2/n, m3/n


@njit(fastmath=True)
def moments_point_weighted(pos, p0, p1, p2, w):
    """Compute mass-weighted variance and third moment of atomic distances from a reference point.

    in:
        pos (numpy.ndarray): (N, 3) array of atomic positions.
        p0, p1, p2 (float): coordinates of the reference point.
        w (numpy.ndarray): (N,) array of normalized atomic mass weights.
    out:
        tuple of 2 floats: (weighted_variance, weighted_third_moment) of the distance
            distribution.
    """
    n = pos.shape[0]

    s1 = 0.0
    for i in range(n):
        dx = pos[i,0]-p0; dy = pos[i,1]-p1; dz = pos[i,2]-p2
        d  = math.sqrt(dx*dx + dy*dy + dz*dz) * w[i]
        s1 += d
    mu = s1 / n

    m2 = 0.0; m3 = 0.0
    for i in range(n):
        dx = pos[i,0]-p0; dy = pos[i,1]-p1; dz = pos[i,2]-p2
        d  = math.sqrt(dx*dx + dy*dy + dz*dz) * w[i]
        r  = d - mu
        r2 = r*r
        m2 += r2
        m3 += r2*r

    return m2/n, m3/n


@njit(fastmath=True)
def usr_mono(pos):
    """Compute the 8-feature USR descriptor for a single cluster (geometry only).

    in:
        pos (numpy.ndarray): (N, 3) array of atomic positions (Numba-accelerated).
    out:
        numpy.ndarray: 1D array of 8 floats (2 moments per each of the 4 reference points).
    """
    ctd0,ctd1,ctd2, cst0,cst1,cst2, fct0,fct1,fct2, ftf0,ftf1,ftf2 = four_points(pos)

    r1 = moments_point(pos, ctd0,ctd1,ctd2)
    r2 = moments_point(pos, cst0,cst1,cst2)
    r3 = moments_point(pos, fct0,fct1,fct2)
    r4 = moments_point(pos, ftf0,ftf1,ftf2)

    out = np.empty(8, dtype=np.float64)
    out[0:2] = r1; out[2:4] = r2; out[4:6] = r3; out[6:8] = r4
    return out


@njit(fastmath=True)
def usr_multi(pos, w):
    """Compute the 16-feature USR descriptor combining geometry and mass-weighted moments.

    in:
        pos (numpy.ndarray): (N, 3) array of atomic positions.
        w (numpy.ndarray): (N,) array of normalized atomic mass weights.
    out:
        numpy.ndarray: 1D array of 16 floats (8 unweighted + 8 mass-weighted moments).
    """
    ctd0,ctd1,ctd2, cst0,cst1,cst2, fct0,fct1,fct2, ftf0,ftf1,ftf2 = four_points(pos)

    r1 = moments_point(pos, ctd0,ctd1,ctd2)
    r2 = moments_point(pos, cst0,cst1,cst2)
    r3 = moments_point(pos, fct0,fct1,fct2)
    r4 = moments_point(pos, ftf0,ftf1,ftf2)

    rw1 = moments_point_weighted(pos, ctd0,ctd1,ctd2, w)
    rw2 = moments_point_weighted(pos, cst0,cst1,cst2, w)
    rw3 = moments_point_weighted(pos, fct0,fct1,fct2, w)
    rw4 = moments_point_weighted(pos, ftf0,ftf1,ftf2, w)

    out = np.empty(16, dtype=np.float64)
    out[0:2]   = r1;  out[2:4]   = r2;  out[4:6]   = r3;  out[6:8]   = r4
    out[8:10]  = rw1; out[10:12] = rw2; out[12:14] = rw3; out[14:16] = rw4
    return out


@njit(parallel=True, fastmath=True)
def usr_batch12(pos_cat, offsets, out8):
    """Compute 8-feature USR descriptors for a batch of structures in parallel (Numba).

    in:
        pos_cat (numpy.ndarray): concatenated positions array of shape (N_total, 3).
        offsets (numpy.ndarray): structure boundary indices of shape (M+1,).
        out8 (numpy.ndarray): output array of shape (M, 8) filled in-place.
    out:
        None. Results are written into out8.
    """
    M = offsets.shape[0] - 1
    for m in prange(M):
        a = offsets[m]; b = offsets[m+1]
        pos = pos_cat[a:b, :]
        out8[m, :] = usr_mono(pos)


@njit(parallel=True, fastmath=True)
def usr_batch24(pos_cat, masses, offsets, out16):
    """Compute 16-feature USR descriptors for a batch of structures in parallel (Numba).

    in:
        pos_cat (numpy.ndarray): concatenated positions array of shape (N_total, 3).
        masses (numpy.ndarray): concatenated atomic masses of shape (N_total,).
        offsets (numpy.ndarray): structure boundary indices of shape (M+1,).
        out16 (numpy.ndarray): output array of shape (M, 16) filled in-place.
    out:
        None. Results are written into out16.
    """
    M = offsets.shape[0] - 1
    for m in prange(M):
        a = offsets[m]; b = offsets[m+1]
        pos = pos_cat[a:b, :]
        w_raw = masses[a:b]

        s = 0.0
        for i in range(w_raw.size):
            s += w_raw[i]
        invavg = w_raw.size / s

        w = np.empty(w_raw.size, dtype=np.float64)
        for i in range(w_raw.size):
            w[i] = w_raw[i] * invavg

        out16[m, :] = usr_multi(pos, w)

#--- Filtros ------------------------------------------------------------------
def filtro_est(lista_atoms, sim=tolsij, dE_max=None, mode="mono", dtype=np.float32):
    """Filter a list of structures by USR similarity and optional energy proximity, keeping unique ones.

    in:
        lista_atoms (list of ase.Atoms): structures to filter; each must have info['e'].
        sim (float): minimum USR similarity threshold in [0, 1] (default 0.95).
        dE_max (float or None): maximum allowed energy difference in eV; None disables the
            energy filter.
        mode (str): 'mono' (8-feature) or 'multi' (16-feature) USR descriptor.
        dtype (numpy.dtype): descriptor data type (default numpy.float32).
    out:
        list of ase.Atoms: filtered list with duplicate structures removed, sorted by energy.
    """
    #t1 = time.perf_counter()

    lista_sorted = sort_by_energy(lista_atoms, 1)
    E = np.array([float(a.info["e"]) for a in lista_sorted], dtype=np.float64)

    X = compute_usr(lista_sorted, mode=mode, dtype=dtype)
    N, D = X.shape

    dmax = D * (1.0 - sim) / sim

    keep1 = prefiltro(X, E, dmax, dE_max)
    X1 = X[keep1]
    E1 = E[keep1]
    lista1 = [lista_sorted[i] for i in np.nonzero(keep1)[0]]

    keep2 = filtro_kdtree(X1, E1, dmax, dE_max)
    lista_out = [lista1[i] for i in np.nonzero(keep2)[0]]

    #t2 = time.perf_counter()
    #print(f"Filtro_USR: {t2 - t1:.3f} s | in={len(lista_atoms)} out={len(lista_out)}")

    return lista_out

#PARSING
def deduplicate_by_usr(lista_atoms, tols=tolsij, tole=tolene, mono=False, flag=1):
    """Remove duplicate structures from a list using USR similarity and energy criteria.

    in:
        lista_atoms (list of ase.Atoms): input structures.
        tols (float): USR similarity threshold (default 0.95).
        tole (float): energy tolerance in eV (default 0.10).
        mono (bool): if True, use 8-feature mono descriptor; otherwise use 16-feature multi.
        flag (int): if 1, print timing and count information.
    out:
        list of ase.Atoms: deduplicated structures sorted by energy.
    """
    if len(lista_atoms)==0: return []
    start = time.time()
    ni=len(lista_atoms)
    mode="mono" if mono==True else "multi"
    atoms1=filtro_est(lista_atoms, sim=tols, dE_max=tole, mode=mode, dtype=np.float32)
    nf=len(atoms1)
    end = time.time()
    if flag == 1: print('USR comparison at    %5.2f s [%d -> %d]' %(end - start, ni, nf))
    return atoms1

def filtro_est_ref_search(ref_atoms, search_atoms, sim=tolsij, dE_max=None, mode="mono", dtype=np.float32):
    """Remove from search_atoms any structure that is too similar to a structure in ref_atoms.

    in:
        ref_atoms (list of ase.Atoms): reference pool.
        search_atoms (list of ase.Atoms): structures to filter.
        sim (float): USR similarity threshold.
        dE_max (float or None): maximum energy difference allowed.
        mode (str): 'mono' or 'multi' USR descriptor mode.
        dtype (numpy.dtype): descriptor data type.
    out:
        list of ase.Atoms: structures from search_atoms not duplicated in ref_atoms.
    """
    X_ref = compute_usr(ref_atoms,   mode=mode, dtype=dtype)
    X_sea = compute_usr(search_atoms, mode=mode, dtype=dtype)

    D = X_ref.shape[1]
    dmax = D * (1.0 - sim) / sim

    if dE_max is None:
        keep = filtro_kdtree_ref_search(X_ref, None, X_sea, None, dmax, None)
    else:
        E_ref = np.array([float(a.info["e"]) for a in ref_atoms], dtype=np.float64)
        E_sea = np.array([float(a.info["e"]) for a in search_atoms], dtype=np.float64)
        keep = filtro_kdtree_ref_search(X_ref, E_ref, X_sea, E_sea, dmax, dE_max)

    search_out = [a for a, k in zip(search_atoms, keep) if k]
    return search_out

#PARSING
def filter_against_reference_usr(moleculein, moleculeref, tols=tolsij, tole=tolene, mono=False, flag=1):
    """Remove from moleculein any structure already represented in moleculeref.

    in:
        moleculein (list of ase.Atoms): candidate structures to filter.
        moleculeref (list of ase.Atoms): reference pool.
        tols (float): USR similarity threshold (default 0.95).
        tole (float): energy tolerance in eV (default 0.10).
        mono (bool): if True, use mono descriptor.
        flag (int): if 1, print timing information.
    out:
        list of ase.Atoms: structures from moleculein not found in moleculeref.
    """
    if len(moleculein)==0: return []
    start = time.time()
    ni=len(moleculein)
    mode="mono" if mono==True else "multi"
    moleculeout=filtro_est_ref_search(moleculeref, moleculein, sim=tols, dE_max=tole, mode="mono", dtype=np.float32)
    nf=len(moleculeout)
    end = time.time()
    if flag == 1: print('USR comparison     at %5.2f s [%d -> %d]' %(end - start, ni, nf))
    return moleculeout

def prefiltro(X, E, dmax, dE_max):
    """Fast pre-screening step that eliminates obvious duplicates before the KD-tree filter.

    in:
        X (numpy.ndarray): descriptor matrix of shape (N, D).
        E (numpy.ndarray): energy array of shape (N,).
        dmax (float): maximum L1 descriptor distance to consider as duplicate.
        dE_max (float or None): maximum energy difference; None disables the energy check.
    out:
        numpy.ndarray: boolean mask of shape (N,); True means 'keep'.
    """
    X = np.asarray(X, dtype=np.float32, order="C")
    E = np.asarray(E, dtype=np.float64)

    if dE_max is None:
        return prefiltro_core(X, dmax)
    else:
        return prefiltro_energy_core(X, E, dmax, float(dE_max))

def filtro_kdtree(X, E, dmax, dE_max):
    """Eliminate duplicate structures using a KD-tree on the descriptor space.

    in:
        X (numpy.ndarray): descriptor matrix of shape (N, D).
        E (numpy.ndarray): energy array of shape (N,).
        dmax (float): maximum L1 descriptor radius for similarity.
        dE_max (float or None): maximum energy difference allowed.
    out:
        numpy.ndarray: boolean mask of shape (N,); True means 'keep'.
    """
    X = np.asarray(X, dtype=np.float32, order="C")
    E = np.asarray(E, dtype=np.float64)
    N = X.shape[0]

    tree = cKDTree(X)
    keep = np.ones(N, dtype=bool)

    if dE_max is None:
        for i in range(N):
            if not keep[i]:
                continue
            neigh = tree.query_ball_point(X[i], r=dmax, p=1)
            for j in neigh:
                if j > i:
                    keep[j] = False
    else:
        dEmax = float(dE_max)
        for i in range(N):
            if not keep[i]:
                continue
            Ei = E[i]
            neigh = tree.query_ball_point(X[i], r=dmax, p=1)
            for j in neigh:
                if j <= i:
                    continue
                dE = E[j] - Ei
                if dE < 0.0:
                    dE = -dE
                if dE <= dEmax:
                    keep[j] = False
    return keep

def filtro_kdtree_ref_search(X_ref, E_ref, X_search, E_search, dmax, dE_max=None):
    """Mark search structures as duplicates if they are too close to any reference structure in descriptor space.

    in:
        X_ref (numpy.ndarray): descriptor matrix of the reference pool.
        E_ref (numpy.ndarray or None): energies of the reference pool.
        X_search (numpy.ndarray): descriptor matrix of structures to test.
        E_search (numpy.ndarray or None): energies of structures to test.
        dmax (float): maximum L1 descriptor radius for similarity.
        dE_max (float or None): maximum allowed energy difference.
    out:
        numpy.ndarray: boolean mask of shape (M,) for search structures; True means 'keep'.
    """
    X_ref    = np.asarray(X_ref,    dtype=np.float32, order="C")
    X_search = np.asarray(X_search, dtype=np.float32, order="C")

    if dE_max is not None:
        E_ref    = np.asarray(E_ref,    dtype=np.float64)
        E_search = np.asarray(E_search, dtype=np.float64)

    tree = cKDTree(X_ref)
    M = X_search.shape[0]
    keep = np.ones(M, dtype=bool)

    if dE_max is None:
        for i in range(M):
            neigh = tree.query_ball_point(X_search[i], r=dmax, p=1)
            if len(neigh) > 0:
                keep[i] = False
    else:
        dEmax = float(dE_max)
        for i in range(M):
            neigh = tree.query_ball_point(X_search[i], r=dmax, p=1)
            if len(neigh) == 0:
                continue
            Ei = E_search[i]
            dup = False
            for j in neigh:
                dE = E_ref[j] - Ei
                if dE < 0.0:
                    dE = -dE
                if dE <= dEmax:
                    dup = True
                    break
            if dup:
                keep[i] = False

    return keep

@njit
def manhattan_threshold(x, y, dmax):
    """Check if the Manhattan (L1) distance between two descriptor vectors is below a threshold.

    in:
        x (numpy.ndarray): first descriptor vector.
        y (numpy.ndarray): second descriptor vector.
        dmax (float): distance threshold.
    out:
        bool: True if the L1 distance is below dmax.
    """
    s = 0.0
    D = x.shape[0]
    for d in range(D):
        diff = x[d] - y[d]
        if diff < 0.0:
            diff = -diff
        s += diff
        if s > dmax:
            return False
    return True

@njit
def prefiltro_core(X, dmax):
    """Fast sequential pre-filter using geometry only; keeps the first occurrence in each similarity cluster.

    in:
        X (numpy.ndarray): descriptor matrix of shape (N, D).
        dmax (float): maximum L1 distance to consider as duplicate.
    out:
        numpy.ndarray: boolean mask of shape (N,); True means 'keep'.
    """
    N, D = X.shape
    keep = np.ones(N, dtype=np.bool_)
    last_keep = 0
    for i in range(1, N):
        if manhattan_threshold(X[i], X[last_keep], dmax):
            keep[i] = False
        else:
            last_keep = i
    return keep

@njit
def prefiltro_energy_core(X, E, dmax, dE_max):
    """Fast sequential pre-filter using both geometry and energy similarity.

    in:
        X (numpy.ndarray): descriptor matrix of shape (N, D).
        E (numpy.ndarray): energy array of shape (N,).
        dmax (float): maximum L1 distance threshold.
        dE_max (float): maximum energy difference threshold in eV.
    out:
        numpy.ndarray: boolean mask of shape (N,); True means 'keep'.
    """
    N, D = X.shape
    keep = np.ones(N, dtype=np.bool_)
    last_keep = 0

    for i in range(1, N):
        dE = E[i] - E[last_keep]
        if dE < 0.0:
            dE = -dE
        if dE > dE_max:
            last_keep = i
            continue

        if manhattan_threshold(X[i], X[last_keep], dmax):
            keep[i] = False
        else:
            last_keep = i
    return keep
