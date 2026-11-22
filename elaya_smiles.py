# -*- coding: utf-8 -*-
"""
ELAYA SMILES — Energy-minimized Linear-to-structure Atom Yielding Algorithm
Gabriela Vidales, Luis Gonzalez, Filiberto Ortiz, Gabriel Merino

Facade used by the web API (app.py).  Compared with the original module:

* No banner / directories / files are created at import or construction time (a web
  server must not write per-request files; downloads are generated on demand).
* RDKit and OpenBabel are imported lazily, so the server starts (and /api/health works)
  even if one of them is missing or broken.
* OpenBabel atoms are written with their real element symbol (``atom.GetType()[0]`` gave
  'C' for Cl and 'B' for Br).
* Every conversion returns ``info`` (method, force field really used, seed) and a stereo QA.
* The NetworkX layout is flagged as *approximate* (it is a graph drawing, not a geometry).
* GLOMOS is no longer started from here: see elaya_jobs.py / glomos_worker.py.
"""
import numpy as np

import elaya_chem as ec
from elaya_chem import ChemError

# Covalent radii (A) for bond perception from XYZ (Cordero et al. 2008)
COVALENT = {"H": 0.31, "B": 0.84, "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57, "Si": 1.11,
            "P": 1.07, "S": 1.05, "Cl": 1.02, "Br": 1.20, "I": 1.39}


class MolecularTools:
    """Stateless facade; kept as a class for backward compatibility."""

    # ---------------------------------------------------------------------------------
    def rdkit_conversion(self, smiles, identifier="mol1", force_field="mmff", optimize=True, seed=665):
        molh, cids, info = ec.embed_conformers(smiles, n_confs=1, seed=seed,
                                               force_field=force_field if optimize else "none")
        cid = cids[0]
        qa = ec.stereo_qa(molh, smiles, cid)
        xyz = ec.mol_to_xyz(molh, cid, "%s | %s" % (identifier, smiles))
        from rdkit import Chem
        info.update({"method": "rdkit"})
        return {"xyz": xyz, "mol": Chem.MolToMolBlock(molh, confId=cid), "info": info, "stereo_qa": qa,
                "atom_order": "rdkit"}

    # ---------------------------------------------------------------------------------
    def openbabel_conversion(self, smiles, identifier="mol1", force_field="mmff94"):
        try:
            from openbabel import pybel
        except Exception as exc:
            raise ChemError("OpenBabel is not available in this deployment (%s)." % exc)
        ec.parse_smiles(smiles)                                   # same validation / limits
        ff = (force_field or "").lower()
        ff = {"mmff": "mmff94", "uff": "uff", "gaff": "gaff", "ghemical": "ghemical"}.get(ff, ff)
        mol = pybel.readstring("smi", smiles)
        mol.addh()
        used = "none"
        if ff and ff != "none":
            if ff not in pybel.forcefields:
                ff = "mmff94" if "mmff94" in pybel.forcefields else "uff"
            mol.make3D(forcefield=ff, steps=2000)
            used = ff
        else:
            mol.make3D(forcefield="uff", steps=0)
        syms = [ec.Z_TO_SYMBOL.get(a.atomicnum) or _symbol(a.atomicnum) for a in mol.atoms]
        pos = np.array([a.coords for a in mol.atoms])
        xyz = ec.format_xyz(syms, pos, "%s | %s" % (identifier, smiles))
        qa = None
        try:                                                  # same atom order as RDKit for ELAYA's SMILES
            qa = ec.stereo_qa(ec.mol_with_coords(smiles, xyz), smiles, 0)
        except Exception:                                     # noqa: BLE001
            pass
        return {"xyz": xyz, "mol": mol.write("sdf"),
                "info": {"method": "openbabel", "force_field": used, "embedding": "OBBuilder"},
                "stereo_qa": qa, "atom_order": "openbabel"}

    # ---------------------------------------------------------------------------------
    def networkx_conversion(self, smiles, identifier="mol1"):
        """3D graph layout with NetworkX (Kamada-Kawai stress majorisation).

        Target distances for every atom pair come from the molecular graph (RDKit topological
        distance bounds: bond lengths, 1-3 distances from ideal angles, ring and 1-4 limits), so
        the layout has chemically sensible bond lengths and angles. Distances cannot tell
        enantiomers apart: wrongly oriented stereocentres / double bonds are inverted afterwards
        and the layout is relaxed again. Still an approximate sketch: no force field.
        """
        import networkx as nx
        from rdkit import Chem
        from rdkit.Chem import rdDistGeom
        mol = Chem.AddHs(ec.parse_smiles(smiles))
        n = mol.GetNumAtoms()
        G = nx.Graph()
        G.add_nodes_from(range(n))
        G.add_edges_from((b.GetBeginAtomIdx(), b.GetEndAtomIdx()) for b in mol.GetBonds())
        B = rdDistGeom.GetMoleculeBoundsMatrix(mol)       # upper triangle: upper bounds; lower: lower
        # through-bond path length (A) for pairs without a finite upper bound: using only the
        # lower bound (~van der Waals contact) as target would pull distant atoms together
        bl = {(b.GetBeginAtomIdx(), b.GetEndAtomIdx()): 0.5 * (B[b.GetEndAtomIdx(), b.GetBeginAtomIdx()]
                                                              + B[b.GetBeginAtomIdx(), b.GetEndAtomIdx()])
              if b.GetBeginAtomIdx() < b.GetEndAtomIdx() else
              0.5 * (B[b.GetBeginAtomIdx(), b.GetEndAtomIdx()] + B[b.GetEndAtomIdx(), b.GetBeginAtomIdx()])
              for b in mol.GetBonds()}
        Gw = nx.Graph()
        Gw.add_weighted_edges_from((i, j, w_) for (i, j), w_ in bl.items())
        path = dict(nx.all_pairs_dijkstra_path_length(Gw))
        T = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                lo, hi = B[j, i], B[i, j]
                if hi < 50.0:
                    t = 0.5 * (lo + hi)
                else:
                    t = max(lo, 0.8 * path.get(i, {}).get(j, lo))
                T[i, j] = T[j, i] = t
        dist = {i: {j: float(T[i, j]) for j in range(n)} for i in range(n)}
        iu = np.triu_indices(n, 1)
        w = 1.0 / T[iu] ** 2

        def layout(start):
            pos = nx.kamada_kawai_layout(G, dist=dist, pos={i: start[i] for i in range(n)}, dim=3, scale=1.0)
            P = np.array([pos[i] for i in range(n)])
            d = np.linalg.norm(P[:, None] - P[None], axis=-1)[iu]
            P *= (w * d * T[iu]).sum() / (w * d * d).sum()  # least-squares scale back to angstrom
            return P - P.mean(axis=0)

        rng = np.random.default_rng(586)
        P = layout(rng.normal(size=(n, 3)))
        syms = [a.GetSymbol() for a in mol.GetAtoms()]
        fixed = 0
        for _ in range(6):
            wrong = _wrong_stereo(mol, smiles, P)
            if not wrong:
                break
            for kind, idx in wrong:
                P = _invert_stereo(mol, P, kind, idx)
                fixed += 1
            P = layout(P)
        xyz = ec.format_xyz(syms, P, "%s | %s | NetworkX graph layout (approximate)" % (identifier, smiles))
        molblock = None
        try:
            m3 = ec.mol_with_coords(smiles, xyz)
            molblock = Chem.MolToMolBlock(m3)
            qa = ec.stereo_qa(m3, smiles, 0)
        except Exception:                                    # noqa: BLE001
            qa = None
        return {"xyz": xyz, "mol": molblock,
                "info": {"method": "networkx", "force_field": "none",
                         "embedding": "Kamada-Kawai layout with topological distance targets (approximate)",
                         "stereo_inversions": fixed},
                "stereo_qa": qa, "atom_order": "rdkit", "approximate": True}

    # ---------------------------------------------------------------------------------
    def convert(self, smiles, method="rdkit", force_field="mmff", identifier="mol1", seed=665):
        method = (method or "rdkit").lower()
        if method == "rdkit":
            res = self.rdkit_conversion(smiles, identifier, force_field, True, seed)
        elif method == "openbabel":
            res = self.openbabel_conversion(smiles, identifier, force_field)
        elif method == "networkx":
            res = self.networkx_conversion(smiles, identifier)
        else:
            raise ChemError("Unsupported method: %s" % method)
        syms, pos = ec.parse_xyz(res["xyz"])
        try:
            res["rotational_constants"] = ec.rotational_constants(syms, pos)
        except ChemError:                       # element without a tabulated mass: still return the structure
            res["rotational_constants"] = None
        res["connectivity_check"] = self.check_bonds(smiles, syms, pos)
        return res

    # ---------------------------------------------------------------------------------
    @staticmethod
    def adjacency_from_xyz(symbols, coords, factor=1.2):
        coords = np.asarray(coords)
        r = np.array([COVALENT.get(s, 1.5) for s in symbols])
        d = np.linalg.norm(coords[:, None, :] - coords[None, :, :], axis=-1)
        adj = (d < factor * (r[:, None] + r[None, :])).astype(int)
        np.fill_diagonal(adj, 0)
        return adj

    def check_bonds(self, smiles, symbols, coords):
        """Does the geometry have the same bond graph as the SMILES? (atom order must match)."""
        try:
            from rdkit import Chem
            mol = Chem.AddHs(ec.parse_smiles(smiles))
            if mol.GetNumAtoms() != len(symbols):
                return {"ok": None, "detail": "atom order differs from RDKit; not checked"}
            ref = np.zeros((len(symbols),) * 2, dtype=int)
            for b in mol.GetBonds():
                ref[b.GetBeginAtomIdx(), b.GetEndAtomIdx()] = ref[b.GetEndAtomIdx(), b.GetBeginAtomIdx()] = 1
            if [a.GetSymbol() for a in mol.GetAtoms()] != list(symbols):
                return {"ok": None, "detail": "atom order differs from RDKit; not checked"}
            adj = self.adjacency_from_xyz(symbols, coords)
            diff = np.argwhere(np.triu(adj != ref, 1))
            return {"ok": len(diff) == 0,
                    "detail": "" if len(diff) == 0 else "bond mismatch at atoms: " +
                    ", ".join("%d-%d" % (i + 1, j + 1) for i, j in diff[:6])}
        except Exception as exc:                                  # noqa: BLE001
            return {"ok": None, "detail": str(exc)}

    # ---------------------------------------------------------------------------------
    def export(self, smiles, xyz_text, fmt, name="ELAYA", properties=None):
        """Structure in the requested format. Falls back to OpenBabel when the atom order is not RDKit's."""
        try:
            return ec.export_structure(smiles, xyz_text, fmt, name, properties)
        except ChemError as first:
            if "mismatch" not in str(first) and "atoms but" not in str(first):
                raise
            try:
                from openbabel import pybel
            except Exception:
                raise first
            m = pybel.readstring("xyz", xyz_text)
            m.title = name
            return m.write(fmt)

    @staticmethod
    def connectivity_matrix(xyz_text, factor=1.2):
        """Connectivity from a geometry with covalent radii (the old fixed 2.0 A cut-off linked
        every non-bonded pair in dense molecules and missed C-I / long bonds)."""
        syms, pos = ec.parse_xyz(xyz_text)
        return syms, MolecularTools.adjacency_from_xyz(syms, pos, factor)


def _symbol(z):
    try:
        from rdkit import Chem
        return Chem.GetPeriodicTable().GetElementSymbol(int(z))
    except Exception:                                             # noqa: BLE001
        raise ChemError("Unknown atomic number %s" % z)


def _wrong_stereo(mol, smiles, P):
    """[(kind, index)] of stereocentres ('atom') / double bonds ('bond') that P gets wrong."""
    from rdkit import Chem
    ref = ec.parse_smiles(smiles)
    want_c = dict(Chem.FindMolChiralCenters(ref, includeUnassigned=False, useLegacyImplementation=False))
    want_b = {b.GetIdx(): b.GetStereo() for b in ref.GetBonds()
              if b.GetStereo() in (Chem.BondStereo.STEREOE, Chem.BondStereo.STEREOZ,
                                   Chem.BondStereo.STEREOCIS, Chem.BondStereo.STEREOTRANS)}
    if not want_c and not want_b:
        return []
    m3 = Chem.Mol(mol)
    m3.RemoveAllConformers()
    conf = Chem.Conformer(m3.GetNumAtoms())
    for i, p in enumerate(P):
        conf.SetAtomPosition(i, [float(v) for v in p])
    m3.AddConformer(conf, assignId=True)
    Chem.AssignStereochemistryFrom3D(m3, confId=0, replaceExistingTags=True)
    got_c = dict(Chem.FindMolChiralCenters(m3, includeUnassigned=False, useLegacyImplementation=False))
    out = [("atom", i) for i, c in want_c.items() if got_c.get(i) != c]
    for bi, st in want_b.items():
        if str(m3.GetBondWithIdx(bi).GetStereo()) != str(st):
            out.append(("bond", bi))
    return out


def _branch(mol, root, blocked):
    """Atoms reachable from ``root`` without crossing ``blocked`` (None if that loops back)."""
    seen, stack = {root}, [root]
    while stack:
        a = stack.pop()
        for nb in mol.GetAtomWithIdx(a).GetNeighbors():
            j = nb.GetIdx()
            if j == blocked and a != root:
                return None                                # ring: the branch is not separable
            if j != blocked and j not in seen:
                seen.add(j)
                stack.append(j)
    return seen


def _invert_stereo(mol, P, kind, idx):
    """Invert one stereocentre (reflect its smallest branch through the plane of the other
    three neighbours) or one double bond (rotate one side by 180 degrees)."""
    P = P.copy()
    if kind == "atom":
        nbrs = [nb.GetIdx() for nb in mol.GetAtomWithIdx(idx).GetNeighbors()]
        branches = [(len(b), k, b) for k, b in ((k, _branch(mol, k, idx)) for k in nbrs) if b]
        if not branches or len(nbrs) < 3:
            return P
        _, k, branch = min(branches)
        others = [j for j in nbrs if j != k][:3]
        if len(others) == 3:
            a, b, c = (P[j] for j in others)
            nrm = np.cross(b - a, c - a)
        else:                                              # 3-coordinate centre: plane of centre + 2 neighbours
            a, b, c = P[idx], P[others[0]], P[others[1]]
            nrm = np.cross(b - a, c - a)
        nrm /= np.linalg.norm(nrm) or 1.0
        for j in branch:
            P[j] -= 2.0 * np.dot(P[j] - a, nrm) * nrm
    else:
        bond = mol.GetBondWithIdx(idx)
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        side = _branch(mol, j, i)
        if side:
            axis = P[j] - P[i]
            axis /= np.linalg.norm(axis) or 1.0
            for k in side:                                  # 180 degree rotation about the bond axis
                v = P[k] - P[j]
                P[k] = P[j] + 2.0 * np.dot(v, axis) * axis - v
    return P
