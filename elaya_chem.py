"""
elaya_chem.py — chemistry layer of ELAYA (RDKit based, stateless, no disk writes).

Everything the web API needs that is *chemistry* lives here so that it can be unit
tested and used from scripts:

    parse_smiles / mol_report      validation + descriptors + warnings
    embed_conformers               ETKDGv3 seed pool (+ MMFF/UFF clean-up)
    rotor_specs / build_problem_dict   chemistry-aware torsion definition for GLOMOS
    stereo_qa                      does the 3D geometry reproduce the input stereo?
    rotational_constants           A, B, C from a geometry (most-abundant isotopes)
    xyz helpers, export_structure  XYZ / MOL / SDF / PDB (RDKit), MOL2 / CML (OpenBabel, optional)

The rotational-constant routine is pure numpy and works without RDKit.
"""
import math
import numpy as np

try:                                           # RDKit is optional for the pure-numpy helpers
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors, Crippen, Lipinski
    HAVE_RDKIT = True
except Exception:                              # pragma: no cover - depends on environment
    Chem = AllChem = Descriptors = rdMolDescriptors = Crippen = Lipinski = None
    HAVE_RDKIT = False

# --------------------------------------------------------------------------------------
# Physical constants / data
# --------------------------------------------------------------------------------------
# Masses (u) of the most abundant isotope.  Used for rotational constants.
MASSES = {
    1: 1.00782503223, 5: 11.00930536, 6: 12.0, 7: 14.00307400443, 8: 15.99491461957,
    9: 18.99840316273, 14: 27.97692653465, 15: 30.97376199842, 16: 31.9720711744,
    17: 34.968852682, 35: 78.9183376, 53: 126.9044719,
}
SYMBOL_TO_Z = {"H": 1, "B": 5, "C": 6, "N": 7, "O": 8, "F": 9, "Si": 14, "P": 15,
               "S": 16, "Cl": 17, "Br": 35, "I": 53}
Z_TO_SYMBOL = {v: k for k, v in SYMBOL_TO_Z.items()}
# B[MHz] = H_OVER_8PI2 / I[u*A^2]; h/(8 pi^2) in MHz*u*A^2
#   h = 6.62607015e-34 J s, u = 1.66053906660e-27 kg, A = 1e-10 m
H_OVER_8PI2 = 6.62607015e-34 / (8.0 * math.pi ** 2) / (1.66053906660e-27 * 1e-20) / 1e6
MHZ_TO_CM1 = 1.0 / 29979.2458           # 1 cm^-1 = 29979.2458 MHz


class ChemError(ValueError):
    """User-facing chemistry error (bad SMILES, unsupported molecule...)."""


def _need_rdkit():
    if not HAVE_RDKIT:
        raise ChemError("RDKit is not installed in this environment.")


# --------------------------------------------------------------------------------------
# XYZ helpers
# --------------------------------------------------------------------------------------
def parse_xyz(text):
    """XYZ text -> (symbols, coords[N,3]). Reads only the first structure."""
    lines = [l for l in text.strip().splitlines()]
    try:
        n = int(lines[0].split()[0])
    except (IndexError, ValueError):
        raise ChemError("Invalid XYZ: first line must be the number of atoms")
    body = lines[2:2 + n]
    if len(body) < n:
        raise ChemError("Invalid XYZ: expected %d atoms, found %d" % (n, len(body)))
    sym, xyz = [], []
    for l in body:
        p = l.split()
        if len(p) < 4:
            raise ChemError("Invalid XYZ line: %r" % l)
        sym.append(p[0].capitalize())
        xyz.append([float(p[1]), float(p[2]), float(p[3])])
    return sym, np.array(xyz, dtype=float)


def format_xyz(symbols, coords, comment=""):
    out = ["%d" % len(symbols), comment.replace("\n", " ")]
    for s, (x, y, z) in zip(symbols, coords):
        out.append("%-2s %14.8f %14.8f %14.8f" % (s, x, y, z))
    return "\n".join(out) + "\n"


def mol_to_xyz(mol, conf_id=-1, comment=""):
    conf = mol.GetConformer(conf_id)
    syms = [a.GetSymbol() for a in mol.GetAtoms()]
    pos = np.array([list(conf.GetAtomPosition(i)) for i in range(mol.GetNumAtoms())])
    return format_xyz(syms, pos, comment)


# --------------------------------------------------------------------------------------
# Rotational constants
# --------------------------------------------------------------------------------------
def rotational_constants(symbols, coords):
    """Rotational constants of a rigid structure.

    Returns dict(A, B, C in MHz and GHz and cm^-1, kappa, moments in u*A^2, top).
    Principal axes sorted so that A >= B >= C.  Linear molecules (one moment ~0) get
    A = None.  Uses the most abundant isotope of each element.
    """
    coords = np.asarray(coords, dtype=float)
    try:
        m = np.array([MASSES[SYMBOL_TO_Z[s]] if s in SYMBOL_TO_Z else MASSES[int(s)] for s in symbols])
    except (KeyError, ValueError):
        raise ChemError("Unsupported element for rotational constants")
    com = (m[:, None] * coords).sum(0) / m.sum()
    r = coords - com
    I = np.zeros((3, 3))
    for mi, ri in zip(m, r):
        I += mi * (np.dot(ri, ri) * np.eye(3) - np.outer(ri, ri))
    ev = np.sort(np.linalg.eigvalsh(I))              # Ia <= Ib <= Ic  (u*A^2)
    tol = 1e-6
    consts = []
    for v in ev:
        consts.append(None if v < tol else H_OVER_8PI2 / v)
    A, B, C = consts[0], consts[1], consts[2]       # A from smallest moment => largest constant
    out = {"moments_uA2": [float(x) for x in ev]}
    linear = ev[0] < 1e-4 * max(ev[2], 1e-12) or ev[0] < tol
    if linear:
        out["top"] = "linear" if len(symbols) > 1 else "atom"
        out["A_MHz"] = None
    else:
        out["A_MHz"] = A
    out["B_MHz"], out["C_MHz"] = B, C
    if not linear and A and B and C:
        out["kappa"] = (2 * B - A - C) / (A - C) if abs(A - C) > 1e-9 else 0.0
        if abs(A - B) < 1e-3 * A and abs(B - C) < 1e-3 * A:
            out["top"] = "spherical"
        elif abs(B - C) < 1e-3 * A:
            out["top"] = "prolate symmetric"
        elif abs(A - B) < 1e-3 * A:
            out["top"] = "oblate symmetric"
        else:
            out["top"] = "asymmetric"
    for k in ("A", "B", "C"):
        v = out.get(k + "_MHz")
        out[k + "_GHz"] = None if v is None else v / 1000.0
        out[k + "_cm1"] = None if v is None else v * MHZ_TO_CM1
    return out


# --------------------------------------------------------------------------------------
# Parsing and reports
# --------------------------------------------------------------------------------------
MAX_HEAVY_ATOMS = 120


def parse_smiles(smiles, max_heavy=MAX_HEAVY_ATOMS):
    """Sanitised RDKit molecule (no explicit H) or ChemError with a readable message."""
    _need_rdkit()
    s = (smiles or "").strip()
    if not s:
        raise ChemError("Empty SMILES")
    if len(s) > 2000:
        raise ChemError("SMILES too long (max 2000 characters)")
    mol = Chem.MolFromSmiles(s)
    if mol is None:
        raise ChemError("RDKit could not parse the SMILES (check ring closures, valences and brackets): %s" % s[:80])
    if mol.GetNumHeavyAtoms() > max_heavy:
        raise ChemError("Molecule too large (%d heavy atoms, limit %d)" % (mol.GetNumHeavyAtoms(), max_heavy))
    return mol


def _stereo_info(mol):
    centers = Chem.FindMolChiralCenters(mol, includeUnassigned=True, useLegacyImplementation=False)
    specified = [(i, c) for i, c in centers if c in ("R", "S")]
    unspecified = [i for i, c in centers if c not in ("R", "S")]
    dbl = {"E": 0, "Z": 0, "undefined": 0}
    ranks = None
    for b in mol.GetBonds():
        # double bonds in rings of 3-7 atoms cannot be E/Z-isomeric (RDKit API: IsInRingSize)
        if b.GetBondType() != Chem.BondType.DOUBLE or any(b.IsInRingSize(n) for n in range(3, 8)):
            continue
        st = b.GetStereo()
        if st in (Chem.BondStereo.STEREOE, Chem.BondStereo.STEREOTRANS):
            dbl["E"] += 1
        elif st in (Chem.BondStereo.STEREOZ, Chem.BondStereo.STEREOCIS):
            dbl["Z"] += 1
        else:
            # potential stereo bond without label?
            a1, a2 = b.GetBeginAtom(), b.GetEndAtom()
            if a1.GetDegree() >= 2 and a2.GetDegree() >= 2:
                nb1 = {n.GetIdx() for n in a1.GetNeighbors()} - {a2.GetIdx()}
                nb2 = {n.GetIdx() for n in a2.GetNeighbors()} - {a1.GetIdx()}
                if ranks is None:
                    ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False))
                r1 = {ranks[i] for i in nb1}
                r2 = {ranks[i] for i in nb2}
                if len(r1) == len(nb1) and len(r2) == len(nb2):
                    dbl["undefined"] += 1
    return specified, unspecified, dbl


# Functional groups shown in "More information" (name, SMARTS). Counted as non-overlapping matches.
FUNCTIONAL_GROUPS = [
    ("Carboxylic acid", "[CX3](=O)[OX2H1]"),
    ("Ester", "[#6][CX3](=O)[OX2H0][#6]"),
    ("Amide", "[NX3][CX3](=[OX1])"),
    ("Aldehyde", "[CX3H1](=O)"),
    ("Ketone", "[#6][CX3](=O)[#6]"),
    ("Alcohol", "[OX2H][CX4]"),
    ("Phenol", "[OX2H]c"),
    ("Ether", "[OX2]([#6;!$(C=[O,S,N])])[#6;!$(C=[O,S,N])]"),
    ("Amine", "[NX3;!$(N-C=[O,S,N]);!$(N-a);!$(N-[!#6;!#1])]"),
    ("Aromatic amine", "[NX3;!$(N-C=[O,S,N])]-a"),
    ("Imine", "[CX3]=[NX2]"),
    ("Nitrile", "[CX2]#[NX1]"),
    ("Nitro", "[$([NX3](=O)=O),$([NX3+](=O)[O-])]"),
    ("Thiol", "[SX2H]"),
    ("Disulfide", "[SX2][SX2]"),
    ("Thioether", "[SX2;!$(S-S)]([#6])[#6]"),
    ("Halogen", "[F,Cl,Br,I]"),
    ("Alkene", "[CX3;!a]=[CX3;!a]"),
    ("Alkyne", "[CX2]#[CX2]"),
    ("Aromatic heterocycle", "[a;!c;r]"),
]
_FG_PATTERNS = None


def functional_groups(mol):
    """[(name, count)] of the FUNCTIONAL_GROUPS present (aromatic heterocycles counted per ring)."""
    global _FG_PATTERNS
    if _FG_PATTERNS is None:
        _FG_PATTERNS = [(n, Chem.MolFromSmarts(sm)) for n, sm in FUNCTIONAL_GROUPS]
    out = []
    for name, patt in _FG_PATTERNS:
        if patt is None:
            continue
        if name == "Aromatic heterocycle":
            ri = mol.GetRingInfo()
            n = sum(1 for ring in ri.AtomRings()
                    if all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in ring)
                    and any(mol.GetAtomWithIdx(i).GetSymbol() != "C" for i in ring))
        else:
            n = len(mol.GetSubstructMatches(patt))
        if n:
            out.append((name, n))
    return out


def mol_report(smiles):
    """Descriptors, stereo summary and warnings for the web 'report' panel."""
    mol = parse_smiles(smiles)
    molh = Chem.AddHs(mol)
    specified, unspecified, dbl = _stereo_info(mol)
    warnings = []
    frags = Chem.GetMolFrags(mol)
    charge = Chem.GetFormalCharge(mol)
    radicals = sum(a.GetNumRadicalElectrons() for a in mol.GetAtoms())
    n_rot = rdMolDescriptors.CalcNumRotatableBonds(mol)
    if len(frags) > 1:
        warnings.append("The SMILES has %d fragments (salt / mixture): 3D conversion keeps them, "
                        "GLOMOS needs a single molecule." % len(frags))
    if unspecified:
        warnings.append("%d stereocentre(s) without configuration (atoms %s): ELAYA will build an arbitrary "
                        "stereoisomer. Specify @/@@ in the SMILES if the configuration matters."
                        % (len(unspecified), ", ".join(str(i + 1) for i in unspecified)))
    if dbl["undefined"]:
        warnings.append("%d double bond(s) without E/Z label." % dbl["undefined"])
    if radicals:
        warnings.append("Open-shell species: ANI (GLOMOS) only supports closed-shell molecules.")
    if charge:
        warnings.append("Net charge %+d: ANI is parametrised for neutral molecules; GLOMOS energies are unreliable." % charge)
    elems = sorted({a.GetSymbol() for a in mol.GetAtoms()})
    if not set(elems) <= {"H", "C", "N", "O", "F", "S", "Cl"}:
        warnings.append("Elements outside ANI-2x coverage (H,C,N,O,F,S,Cl): %s" % ", ".join(elems))
    try:
        inchi = Chem.MolToInchi(mol)
        inchikey = Chem.MolToInchiKey(mol)
    except Exception:
        inchi = inchikey = None
    nonarom = [b for b in mol.GetBonds() if not b.GetIsAromatic()]
    n_double = sum(1 for b in nonarom if b.GetBondType() == Chem.BondType.DOUBLE)
    n_triple = sum(1 for b in nonarom if b.GetBondType() == Chem.BondType.TRIPLE)
    n_stereo_bonds = dbl["E"] + dbl["Z"] + dbl["undefined"]
    n_stereo = len(specified) + len(unspecified) + n_stereo_bonds
    return {
        "canonical_smiles": Chem.MolToSmiles(mol),
        "isomeric_smiles": Chem.MolToSmiles(mol, isomericSmiles=True),
        "formula": rdMolDescriptors.CalcMolFormula(mol),
        "mol_weight": round(Descriptors.MolWt(mol), 4),
        "exact_mass": round(Descriptors.ExactMolWt(mol), 5),
        "heavy_atoms": mol.GetNumHeavyAtoms(),
        "atoms_with_h": molh.GetNumAtoms(),
        "charge": charge,
        "n_fragments": len(frags),
        "rings": rdMolDescriptors.CalcNumRings(mol),
        "aromatic_rings": rdMolDescriptors.CalcNumAromaticRings(mol),
        "rotatable_bonds": n_rot,
        "hbd": Lipinski.NumHDonors(mol),
        "hba": Lipinski.NumHAcceptors(mol),
        "tpsa": round(rdMolDescriptors.CalcTPSA(mol), 2),
        "logp": round(Crippen.MolLogP(mol), 3),
        "stereocenters": [{"atom": i + 1, "cip": c} for i, c in specified],
        "undefined_stereocenters": [i + 1 for i in unspecified],
        "double_bond_stereo": dbl,
        "inchi": inchi,
        "inchikey": inchikey,
        "double_bonds": n_double,
        "triple_bonds": n_triple,
        "stereo_double_bonds": n_stereo_bonds,
        # upper bound: every stereo element independent (meso forms make the real number smaller)
        "possible_stereoisomers": 2 ** n_stereo,
        "fraction_csp3": round(rdMolDescriptors.CalcFractionCSP3(mol), 3),
        "functional_groups": [{"name": n, "count": c} for n, c in functional_groups(mol)],
        "ani_supported": bool(set(elems) <= {"H", "C", "N", "O", "F", "S", "Cl"} and not radicals),
        "warnings": warnings,
    }


# --------------------------------------------------------------------------------------
# 3D embedding
# --------------------------------------------------------------------------------------
def _ff_minimize(mol, conf_ids, max_iters=2000, ff="mmff"):
    """Minimise conformers with MMFF94 (fallback UFF). Returns the force field actually used."""
    used = "uff"
    if ff.lower() != "uff" and AllChem.MMFFHasAllMoleculeParams(mol):
        props = AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94")
        for cid in conf_ids:
            f = AllChem.MMFFGetMoleculeForceField(mol, props, confId=cid)
            f.Minimize(maxIts=max_iters)
        return "mmff94"
    for cid in conf_ids:
        AllChem.UFFOptimizeMolecule(mol, confId=cid, maxIters=max_iters)
    return used


def embed_conformers(smiles, n_confs=1, seed=665, force_field="mmff", prune_rms=0.5, max_attempts=5):
    """ETKDGv3 embedding.  Returns (mol_with_Hs, [conf_ids], info).

    Fixes over the original code:
      * random seed is configurable and recorded
      * if embedding fails, retries with random coordinates (needed for macrocycles / cages)
      * MMFF94 is the default (more accurate than UFF); UFF is the fallback
      * the force field *actually used* is reported
    """
    _need_rdkit()
    mol = parse_smiles(smiles)
    molh = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = int(seed)
    params.pruneRmsThresh = float(prune_rms) if n_confs > 1 else -1.0
    params.numThreads = 1
    cids = list(AllChem.EmbedMultipleConfs(molh, numConfs=max(1, int(n_confs)), params=params))
    tries = 0
    while not cids and tries < max_attempts:
        params.useRandomCoords = True
        params.randomSeed = int(seed) + 17 * (tries + 1)
        cids = list(AllChem.EmbedMultipleConfs(molh, numConfs=max(1, int(n_confs)), params=params))
        tries += 1
    if not cids:
        raise ChemError("RDKit could not generate 3D coordinates for this molecule.")
    used = "none"
    if force_field and force_field.lower() not in ("none", ""):
        used = _ff_minimize(molh, cids, ff=force_field)
    return molh, cids, {"embedding": "ETKDGv3", "seed": int(seed), "force_field": used,
                        "n_conformers": len(cids)}


# --------------------------------------------------------------------------------------
# Rotors / stereo restraints for GLOMOS
# --------------------------------------------------------------------------------------
def _is_top(mol, ranks, centre, partner):
    """True when ``centre`` is a symmetric top about the bond to ``partner`` (CH3, CF3, tBu, ...)."""
    nbrs = [n.GetIdx() for n in mol.GetAtomWithIdx(centre).GetNeighbors() if n.GetIdx() != partner]
    return len(nbrs) >= 3 and len({ranks[n] for n in nbrs}) == 1


def rotor_specs(molh):
    """Torsional degrees of freedom for GLOMOS from the *chemistry* (not from geometry).

    A bond is a rotor if it is single, acyclic, non-aromatic, not triple-bond adjacent
    (sp-hybridised end), has a non-H neighbour on both sides... except X-H rotors (OH, SH,
    NH2 hydrogens), which are included because they change the energy through
    hydrogen bonding.  Symmetric tops (CH3, CF3, C(CH3)3) are excluded: rotating them
    does not create new conformers.
    """
    ranks = list(Chem.CanonicalRankAtoms(molh, breakTies=False))
    specs = []
    for b in molh.GetBonds():
        if b.GetBondType() != Chem.BondType.SINGLE or b.IsInRing() or b.GetIsAromatic():
            continue
        a1, a2 = b.GetBeginAtom(), b.GetEndAtom()
        if a1.GetAtomicNum() == 1 or a2.GetAtomicNum() == 1:
            continue
        if a1.GetHybridization() == Chem.HybridizationType.SP or a2.GetHybridization() == Chem.HybridizationType.SP:
            continue                                   # rotation about a linear axis is trivial
        i, j = a1.GetIdx(), a2.GetIdx()
        if a1.GetDegree() < 2 or a2.GetDegree() < 2:
            continue
        if _is_top(molh, ranks, i, j) or _is_top(molh, ranks, j, i):
            continue
        # classify
        def has_terminal_h(a, other):
            return any(n.GetAtomicNum() == 1 for n in a.GetNeighbors() if n.GetIdx() != other)
        def heavy_nbrs(a, other):
            return [n for n in a.GetNeighbors() if n.GetIdx() != other and n.GetAtomicNum() > 1]
        kind = "generic"
        def carbonyl_like(a, other):
            if a.GetAtomicNum() not in (6, 16, 15):
                return False
            return any(bb.GetBondType() == Chem.BondType.DOUBLE and bb.GetOtherAtom(a).GetAtomicNum() in (7, 8, 16)
                       for bb in a.GetBonds() if bb.GetOtherAtomIdx(a.GetIdx()) != other)
        if (carbonyl_like(a1, j) and a2.GetAtomicNum() in (7, 8)) or (carbonyl_like(a2, i) and a1.GetAtomicNum() in (7, 8)):
            kind = "planar"                             # amide / ester / acid: C(=O)-X
        elif ((a1.GetAtomicNum() in (7, 8, 16) and not heavy_nbrs(a1, j) and has_terminal_h(a1, j)) or
              (a2.GetAtomicNum() in (7, 8, 16) and not heavy_nbrs(a2, i) and has_terminal_h(a2, i))):
            kind = "xh"
        elif a1.GetHybridization() == Chem.HybridizationType.SP3 and a2.GetHybridization() == Chem.HybridizationType.SP3:
            kind = "sp3"
        specs.append({"a": i, "b": j, "kind": kind})
    return specs


def _dihedral(p0, p1, p2, p3):
    b0, b1, b2 = p0 - p1, p2 - p1, p3 - p2
    b1n = b1 / np.linalg.norm(b1)
    v = b0 - np.dot(b0, b1n) * b1n
    w = b2 - np.dot(b2, b1n) * b1n
    x = np.dot(v, w)
    y = np.dot(np.cross(b1n, v), w)
    return math.degrees(math.atan2(y, x))


def build_problem_dict(molh, conf_id=-1):
    """Bond graph, rotors and stereo restraints for GLOMOS from an embedded molecule."""
    conf = molh.GetConformer(conf_id)
    pos = np.array([list(conf.GetAtomPosition(i)) for i in range(molh.GetNumAtoms())])
    bonds = [[b.GetBeginAtomIdx(), b.GetEndAtomIdx()] for b in molh.GetBonds()]
    chiral = []
    for idx, label in Chem.FindMolChiralCenters(molh, includeUnassigned=False, useLegacyImplementation=False):
        nb = sorted(n.GetIdx() for n in molh.GetAtomWithIdx(idx).GetNeighbors())
        if len(nb) < 3:
            continue
        n1, n2, n3 = nb[:3]
        vol = np.dot(pos[n1] - pos[idx], np.cross(pos[n2] - pos[idx], pos[n3] - pos[idx]))
        chiral.append([idx, n1, n2, n3, 1 if vol > 0 else -1])
    ez = []
    for b in molh.GetBonds():
        if b.GetBondType() != Chem.BondType.DOUBLE:
            continue
        if b.GetStereo() in (Chem.BondStereo.STEREONONE, Chem.BondStereo.STEREOANY):
            continue
        sa = list(b.GetStereoAtoms())
        if len(sa) != 2:
            continue
        a, c = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
        d = _dihedral(pos[sa[0]], pos[a], pos[c], pos[sa[1]])
        ez.append([sa[0], a, c, sa[1], abs(d) < 90.0])
    return {
        "bonds": bonds,
        "rotors": rotor_specs(molh),
        "chiral": chiral,
        "ez": ez,
        "charge": Chem.GetFormalCharge(molh),
    }


def glomos_seed_pool(smiles, n_seeds=4, seed=665):
    """Seeds for GLOMOS: ETKDG pool.  Returns (molh, multi-xyz text, problem dict, info)."""
    mol = parse_smiles(smiles)
    if len(Chem.GetMolFrags(mol)) > 1:
        raise ChemError("GLOMOS needs a single molecule (the SMILES has several fragments).")
    molh, cids, info = embed_conformers(smiles, n_confs=n_seeds, seed=seed)
    problem = build_problem_dict(molh, cids[0])
    # keep only seeds whose stereo agrees with the input
    chunks, kept = [], []
    for cid in cids:
        qa = stereo_qa(molh, smiles, cid)
        if qa["ok"]:
            chunks.append(mol_to_xyz(molh, cid, "seed %d" % cid))
            kept.append(cid)
    if not chunks:
        chunks = [mol_to_xyz(molh, cids[0], "seed %d" % cids[0])]
        kept = [cids[0]]
    info["n_seeds"] = len(kept)
    return molh, "".join(chunks), problem, info


# --------------------------------------------------------------------------------------
# Stereo QA
# --------------------------------------------------------------------------------------
def stereo_qa(molh, smiles, conf_id=-1):
    """Compare CIP labels / E-Z of the 3D geometry with the stereo specified in the SMILES."""
    ref = parse_smiles(smiles)
    ref_c = {i: c for i, c in Chem.FindMolChiralCenters(ref, includeUnassigned=False,
                                                          useLegacyImplementation=False)}
    m3 = Chem.Mol(molh, confId=conf_id) if False else Chem.Mol(molh)
    m3.RemoveAllConformers()
    m3.AddConformer(Chem.Conformer(molh.GetConformer(conf_id)), assignId=True)
    Chem.AssignStereochemistryFrom3D(m3, confId=0, replaceExistingTags=True)
    got_c = {i: c for i, c in Chem.FindMolChiralCenters(m3, includeUnassigned=False,
                                                          useLegacyImplementation=False)}
    problems = []
    for i, c in ref_c.items():                        # heavy atom indices coincide (H appended last)
        if got_c.get(i) != c:
            problems.append("atom %d: expected %s, 3D geometry gives %s" % (i + 1, c, got_c.get(i)))
    ref_b = {}
    for b in ref.GetBonds():
        if b.GetStereo() in (Chem.BondStereo.STEREOE, Chem.BondStereo.STEREOZ,
                             Chem.BondStereo.STEREOCIS, Chem.BondStereo.STEREOTRANS):
            ref_b[b.GetIdx()] = str(b.GetStereo())
    for b in m3.GetBonds():
        if b.GetIdx() in ref_b and str(b.GetStereo()) != ref_b[b.GetIdx()]:
            problems.append("double bond %d-%d: expected %s, got %s"
                            % (b.GetBeginAtomIdx() + 1, b.GetEndAtomIdx() + 1, ref_b[b.GetIdx()], b.GetStereo()))
    return {"ok": not problems, "problems": problems, "n_checked": len(ref_c) + len(ref_b)}


# --------------------------------------------------------------------------------------
# From coordinates back to RDKit / exports
# --------------------------------------------------------------------------------------
def mol_with_coords(smiles, xyz_text):
    """RDKit molecule (with Hs, bonds from SMILES) carrying the coordinates of ``xyz_text``.

    Requires the XYZ atom order = RDKit order of AddHs(MolFromSmiles) (true for every XYZ
    that ELAYA produces).  Verifies element symbols atom by atom.
    """
    mol = Chem.AddHs(parse_smiles(smiles))
    syms, pos = parse_xyz(xyz_text)
    if len(syms) != mol.GetNumAtoms():
        raise ChemError("XYZ has %d atoms but the SMILES (with H) has %d" % (len(syms), mol.GetNumAtoms()))
    for a, s in zip(mol.GetAtoms(), syms):
        if a.GetSymbol() != s:
            raise ChemError("Atom order mismatch at atom %d: SMILES says %s, XYZ says %s"
                            % (a.GetIdx() + 1, a.GetSymbol(), s))
    conf = Chem.Conformer(mol.GetNumAtoms())
    for i, p in enumerate(pos):
        conf.SetAtomPosition(i, p.tolist())
    mol.RemoveAllConformers()
    mol.AddConformer(conf, assignId=True)
    return mol


EXPORT_FORMATS = {
    "xyz": ("chemical/x-xyz", "xyz"), "mol": ("chemical/x-mdl-molfile", "mol"),
    "sdf": ("chemical/x-mdl-sdfile", "sdf"), "pdb": ("chemical/x-pdb", "pdb"),
    "mol2": ("chemical/x-mol2", "mol2"), "cml": ("chemical/x-cml", "cml"),
}


def export_structure(smiles, xyz_text, fmt, name="ELAYA", properties=None):
    """Text of the structure in ``fmt``.  mol2/cml need OpenBabel (optional dependency)."""
    fmt = fmt.lower()
    if fmt not in EXPORT_FORMATS:
        raise ChemError("Unsupported export format: %s" % fmt)
    mol = mol_with_coords(smiles, xyz_text)
    mol.SetProp("_Name", name)
    for k, v in (properties or {}).items():
        mol.SetProp(str(k), str(v))
    if fmt == "xyz":
        return xyz_text if xyz_text.endswith("\n") else xyz_text + "\n"
    if fmt == "mol":
        return Chem.MolToMolBlock(mol)
    if fmt == "sdf":
        body = Chem.MolToMolBlock(mol)
        props = "".join(">  <%s>\n%s\n\n" % (k, v) for k, v in
                        [("SMILES", smiles), ("Source", "ELAYA")] + list((properties or {}).items()))
        return body + props + "$$$$\n"
    if fmt == "pdb":
        return Chem.MolToPDBBlock(mol)
    try:
        from openbabel import pybel
    except Exception:
        raise ChemError("Format %s needs OpenBabel, which is not installed in this deployment." % fmt)
    ob_mol = pybel.readstring("mol", Chem.MolToMolBlock(mol))
    ob_mol.title = name
    return ob_mol.write(fmt)
