"""
librotamers.py — torsion-space operators for the GLOMOS rotamer genetic algorithm.

Why this file was rewritten
---------------------------
The original operators rotated about *every* acyclic bridge of the graph, which

  * included C=C, C#C and (partially double) amide/ester C-N / C-O bonds, so the
    "conformers" could be E/Z or cis/trans-amide *isomers* after ANI relaxation;
  * used ``while fall:`` without an upper bound (infinite loop for compact
    molecules whose rotation always clashed);
  * built crossover children with ``align_bond_to_z``, whose basis vectors were not
    normalised, anisotropically squashing the geometry by sin(theta);
  * could not describe the flexibility of rings at all.

Here a conformer is described by its **torsion vector** over a list of
chemically meaningful rotors. Rotors are supplied by the caller (RDKit knows the
bond orders; see elaya_chem.rotor_specs). Operators:

    random_torsions / mutate_angles / crossover_angles   (angle vectors)
    build_from_angles                                    (angles -> geometry)

and every geometry is validated (clashes, connectivity, stereochemistry) before it
is sent to the expensive ANI optimisation.

Geometry convention (verified numerically, see tests/test_torsions.py):
rotating the atoms on the *b* side of axis a->b by +d changes the dihedral
i-a-b-l by +d; rotating the *a* side by +d changes it by -d.
"""
import random
import numpy as np
from glomos.libutils import (adjacency_matrix, neighbor_lists, reachable_without,
                             dihedral_deg, wrap180, rodrigues_rotation_matrix,
                             angular_distance, topological_distances, VDW_RADII)

# Torsion alphabets (degrees). Used for the initial population and mutations; the
# ANI optimisation then relaxes each structure to the nearest true minimum.
ALPHABETS = {
    "sp3":     (60.0, 180.0, -60.0),                        # staggered
    "xh":      (60.0, 180.0, -60.0),                        # O-H / N-H / S-H orientation
    "planar":  (0.0, 180.0),                                # amide / ester / acid: cis/trans
    "generic": (0.0, 60.0, 90.0, 120.0, 180.0, -120.0, -90.0, -60.0),
}
MAX_TRIES = 12            # attempts to obtain a valid geometry for one child
JITTER_DEG = 10.0


# =============================================================================
# Rotors
# =============================================================================
class Rotor:
    """A rotatable bond (a, b) with the atoms that move when it is rotated."""

    __slots__ = ("a", "b", "i", "l", "moving", "sign", "kind", "alphabet")

    def __init__(self, a, b, i, l, moving, sign, kind, alphabet):
        self.a, self.b, self.i, self.l = int(a), int(b), int(i), int(l)
        self.moving = np.array(sorted(moving), dtype=int)
        self.sign = int(sign)
        self.kind = kind
        self.alphabet = tuple(alphabet)

    def as_dict(self):
        return {"a": self.a, "b": self.b, "i": self.i, "l": self.l,
                "kind": self.kind, "n_moving": int(len(self.moving))}


def _best_neighbor(nbrs, center, exclude, numbers):
    """Neighbour of ``center`` (not ``exclude``) used to define the dihedral.

    Prefers heavy atoms (larger Z), ties -> lowest index, so the definition is
    deterministic.
    """
    cands = [int(n) for n in nbrs[center] if n != exclude]
    if not cands:
        return None
    cands.sort(key=lambda n: (-int(numbers[n]), n))
    return cands[0]


def _in_ring(nbrs, a, b):
    """True if the bond a-b belongs to a cycle (b still reaches a once the edge is removed)."""
    seen, stack = {b}, [b]
    while stack:
        u = stack.pop()
        for v in nbrs[u]:
            v = int(v)
            if (u == a and v == b) or (u == b and v == a):
                continue
            if v == a:
                return True
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return False


def build_rotors(adjmatrix, numbers, specs=None):
    """Create Rotor objects.

    in:
        adjmatrix: (N, N) reference adjacency (from the *bond graph*, not geometry)
        numbers:   atomic numbers
        specs:     list of {"a": int, "b": int, "kind": str}. If None, every
                   acyclic bond whose two fragments both have >1 atom is used with
                   the 'generic' alphabet (legacy behaviour of the original GLOMOS,
                   *including* multiple bonds — only for manual use).
    out:
        list[Rotor] ordered by index of the first atom.
    """
    nbrs = neighbor_lists(adjmatrix)
    n = adjmatrix.shape[0]
    if specs is None:
        specs = []
        for u in range(n):
            for v in nbrs[u]:
                if v > u:
                    specs.append({"a": u, "b": int(v), "kind": "generic"})
    rotors = []
    for s in specs:
        a, b = int(s["a"]), int(s["b"])
        if adjmatrix[a, b] == 0:
            continue
        if _in_ring(nbrs, a, b):              # ring bond: cannot rotate rigidly
            continue
        side_b = reachable_without(nbrs, b, a)
        side_a = set(range(n)) - side_b
        if len(side_a) < 2 or len(side_b) < 2:
            continue
        i = _best_neighbor(nbrs, a, b, numbers)
        l = _best_neighbor(nbrs, b, a, numbers)
        if i is None or l is None:
            continue
        if len(side_b) <= len(side_a):
            moving, sign = side_b, +1
        else:
            moving, sign = side_a, -1
        kind = s.get("kind", "generic")
        rotors.append(Rotor(a, b, i, l, moving, sign, kind, ALPHABETS.get(kind, ALPHABETS["generic"])))
    rotors.sort(key=lambda r: (r.a, r.b))
    return rotors


def get_bridge_left_right(adjmatrix):
    """Backward-compatible helper: [a, b, left, right] for each graph bridge."""
    numbers = np.ones(adjmatrix.shape[0], dtype=int)
    out = []
    nbrs = neighbor_lists(adjmatrix)
    for r in build_rotors(adjmatrix, numbers):
        side = set(int(x) for x in r.moving)
        other = set(range(adjmatrix.shape[0])) - side
        out.append([r.a, r.b, sorted(side), sorted(other)])
    return out


# =============================================================================
# Torsions
# =============================================================================
def get_torsion(pos, rotor):
    return dihedral_deg(pos[rotor.i], pos[rotor.a], pos[rotor.b], pos[rotor.l])


def get_torsions(pos, rotors):
    return np.array([get_torsion(pos, r) for r in rotors], dtype=float)


def set_torsion(pos, rotor, target_deg):
    """Rotate the moving fragment (in place on an (N,3) array) so that the dihedral
    i-a-b-l equals ``target_deg``."""
    delta = wrap180(target_deg - get_torsion(pos, rotor))
    if abs(delta) < 1e-9:
        return pos
    origin = pos[rotor.a].copy()
    axis = pos[rotor.b] - origin
    R = rodrigues_rotation_matrix(axis, rotor.sign * delta)
    idx = rotor.moving
    pos[idx] = (pos[idx] - origin) @ R.T + origin
    return pos


def apply_angles(pos, rotors, angles):
    """Return a *new* (N,3) array with every rotor set to the requested torsion.

    Torsions of different rotors are independent (a rigid rotation about one bond
    leaves every other dihedral invariant), so the order does not matter.
    """
    out = np.array(pos, dtype=float, copy=True)
    for r, t in zip(rotors, angles):
        set_torsion(out, r, t)
    return out


# =============================================================================
# Problem definition + geometry validation
# =============================================================================
class Problem:
    """Everything the GA needs to know about the molecule (independent of RDKit).

    numbers : atomic numbers (explicit H included)
    ref_adj : reference adjacency from the bond graph
    rotors  : list[Rotor]
    chiral  : list of (center, n1, n2, n3, sign) — sign of (n1-c).((n2-c)x(n3-c))
    ez      : list of (x, a, b, y, is_cis) for stereo double bonds
    """

    def __init__(self, numbers, ref_adj, rotors, chiral=None, ez=None, charge=0, clash_scale=0.55):
        self.numbers = np.asarray(numbers, dtype=int)
        self.ref_adj = np.asarray(ref_adj, dtype=np.int64)
        self.rotors = list(rotors)
        self.chiral = list(chiral or [])
        self.ez = list(ez or [])
        self.charge = int(charge)
        n = len(self.numbers)
        topo = topological_distances(self.ref_adj)
        vdw = np.array([VDW_RADII.get(int(z), 1.8) for z in self.numbers])
        self._thr = clash_scale * (vdw[:, None] + vdw[None, :])
        self._mask = np.triu(topo >= 4, k=1)           # 1-5 and farther (or disconnected)
        self.n = n

    # -- individual checks --------------------------------------------------------
    def clash(self, pos):
        d = np.linalg.norm(pos[:, None, :] - pos[None, :, :], axis=-1)
        return bool(np.any((d < self._thr) & self._mask))

    def connectivity_ok(self, atoms):
        return check_connectivity(atoms, self.ref_adj)

    def stereo_ok(self, pos):
        for c, n1, n2, n3, sign in self.chiral:
            v = np.dot(pos[n1] - pos[c], np.cross(pos[n2] - pos[c], pos[n3] - pos[c]))
            if abs(v) > 1e-3 and np.sign(v) != sign:
                return False
        for x, a, b, y, is_cis in self.ez:
            phi = abs(dihedral_deg(pos[x], pos[a], pos[b], pos[y]))
            if is_cis and phi > 60.0:
                return False
            if (not is_cis) and phi < 120.0:
                return False
        return True

    def why_invalid(self, atoms, check_clash=True):
        """None if the structure is acceptable, else a short reason."""
        pos = atoms.get_positions()
        if not np.all(np.isfinite(pos)):
            return "non-finite coordinates"
        if check_clash and self.clash(pos):
            return "steric clash"
        if not self.connectivity_ok(atoms):
            return "connectivity changed"
        if not self.stereo_ok(pos):
            return "stereochemistry changed"
        return None


def check_connectivity(atoms, adjmatrix_ref):
    """True if the geometric adjacency of ``atoms`` equals the reference."""
    return bool(np.array_equal(adjacency_matrix(atoms), adjmatrix_ref))


# =============================================================================
# Angle-vector operators
# =============================================================================
def random_torsions(rotors, rng, jitter=JITTER_DEG):
    return np.array([wrap180(rng.choice(r.alphabet) + rng.gauss(0.0, jitter)) for r in rotors])


def mutate_angles(angles, rotors, rng, jitter=JITTER_DEG):
    """Re-draw one or two torsions (weighted towards rotors that move a lot)."""
    angles = np.array(angles, dtype=float, copy=True)
    nr = len(rotors)
    if nr == 0:
        return angles
    k = 2 if (nr > 1 and rng.random() < 0.5) else 1
    weights = [max(1, len(r.moving)) for r in rotors]
    chosen = []
    pool = list(range(nr))
    for _ in range(k):
        tot = float(sum(weights[p] for p in pool))
        x, acc = rng.random() * tot, 0.0
        for p in pool:
            acc += weights[p]
            if x <= acc:
                chosen.append(p)
                pool.remove(p)
                break
    for p in chosen:
        cur = angles[p]
        far = [a for a in rotors[p].alphabet if angular_distance(a, cur) > 30.0]
        pick = rng.choice(far if far else list(rotors[p].alphabet))
        angles[p] = wrap180(pick + rng.gauss(0.0, jitter))
    return angles


def crossover_angles(ang_a, ang_b, rng):
    """Uniform crossover in torsion space; guaranteed to mix both parents.

    Returns None when there are fewer than two rotors (crossover is meaningless).
    """
    nr = len(ang_a)
    if nr < 2:
        return None
    mask = [rng.random() < 0.5 for _ in range(nr)]
    if all(mask) or not any(mask):
        mask[rng.randrange(nr)] = not mask[0]
    return np.array([ang_a[i] if mask[i] else ang_b[i] for i in range(nr)], dtype=float)


# =============================================================================
# Geometry builders (angle vector -> validated ase.Atoms)
# =============================================================================
def build_from_angles(base_atoms, problem, angles, rng, name="child", jitter=JITTER_DEG):
    """Build a valid structure from a torsion vector, retrying with small jitter.

    The geometry of ``base_atoms`` (rings, bond lengths/angles) is preserved; only
    the rotor torsions change. Returns ase.Atoms or None if no valid geometry was
    found within MAX_TRIES attempts.
    """
    base = base_atoms.get_positions()
    for attempt in range(MAX_TRIES):
        trial = np.array(angles, dtype=float)
        if attempt:
            trial = trial + np.array([rng.gauss(0.0, jitter * attempt / 2.0) for _ in trial])
        pos = apply_angles(base, problem.rotors, trial)
        child = base_atoms.copy()
        child.set_positions(pos)
        child.info = {"e": 0.0, "i": name}
        if problem.why_invalid(child) is None:
            return child
    return None


def make_random_rotamers(seedpool, number, problem, rng):
    """Initial population: the pool of seeds first, then random torsion variants.

    in:
        seedpool: list[ase.Atoms] (RDKit ETKDG pool; the first one is the primary seed)
        number:   target population size
    out:
        list[ase.Atoms] named seed00_NNNNN / random_NNNNN (info['e']=0.0)
    """
    out = []
    for k, s in enumerate(seedpool[:number]):
        m = s.copy()
        m.info = {"e": 0.0, "i": "seed00_" + str(k + 1).zfill(5)}
        out.append(m)
    attempts = 0
    while len(out) < number and attempts < 50 * max(1, number):
        attempts += 1
        base = rng.choice(seedpool)
        angles = random_torsions(problem.rotors, rng) if problem.rotors else np.array([])
        child = build_from_angles(base, problem, angles, rng, name="random_" + str(len(out) + 1).zfill(5))
        if child is not None:
            out.append(child)
        elif not problem.rotors:
            break
    return out


def make_mutant_rotamers(rotamerlist, problem, rng):
    """One mutant per parent (the best structures of the current population)."""
    out = []
    for parent in rotamerlist:
        cur = get_torsions(parent.get_positions(), problem.rotors)
        child = None
        for _ in range(MAX_TRIES):
            new = mutate_angles(cur, problem.rotors, rng)
            child = build_from_angles(parent, problem, new, rng, name="mutant_%05d" % (len(out) + 1))
            if child is not None:
                break
        if child is not None:
            out.append(child)
    return out


def make_crossover_rotamers(papy, mamy, problem, rng):
    """Children from paired parent lists; the first parent supplies the geometry."""
    out = []
    for pa, ma in zip(papy, mamy):
        ang_a = get_torsions(pa.get_positions(), problem.rotors)
        ang_b = get_torsions(ma.get_positions(), problem.rotors)
        child = None
        for _ in range(MAX_TRIES):
            new = crossover_angles(ang_a, ang_b, rng)
            if new is None:
                new = mutate_angles(ang_a, problem.rotors, rng)   # <2 rotors: degrade to mutation
            child = build_from_angles(pa, problem, new, rng, name="mating_%05d" % (len(out) + 1))
            if child is not None:
                break
        if child is not None:
            out.append(child)
    return out
