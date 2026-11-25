import sys, time, json, statistics
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else ".")
from elaya_smiles import MolecularTools
import elaya_chem as ec
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors
MOLS = [
 ("Ethanol","CCO"),
 ("n-Butane","CCCC"),
 ("(E)-2-Butene","C/C=C/C"),
 ("(Z)-2-Butene","C/C=C\\C"),
 ("L-Alanine","N[C@@H](C)C(=O)O"),
 ("Aspirin","CC(=O)Oc1ccccc1C(=O)O"),
 ("Dopamine","C1=CC(=C(C=C1CCN)O)O"),
 ("Serotonin","NCCc1c[nH]c2ccc(O)cc12"),
 ("Melatonin","COc1ccc2c(c1)c(c[nH]2)CCNC(=O)C"),
 ("beta-D-Glucose","OC[C@H]1O[C@@H](O)[C@H](O)[C@@H](O)[C@@H]1O"),
 ("(S)-Ibuprofen","CC(C)Cc1ccc(cc1)[C@H](C)C(=O)O"),
 ("Cholesterol","C[C@H](CCCC(C)C)[C@H]1CC[C@@H]2[C@@]1(CC[C@H]3[C@H]2CC=C4[C@@]3(CC[C@@H](C4)O)C)C"),
 ("Oxytocin","N[C@H]1CSSC[C@H](NC(=O)[C@H](CC(N)=O)NC(=O)[C@H](CCC(N)=O)NC(=O)[C@@H](NC(=O)[C@H](Cc2ccc(O)cc2)NC1=O)[C@@H](C)CC)C(=O)N3CCC[C@H]3C(=O)N[C@@H](CC(C)C)C(=O)NCC(N)=O"),
]
CONFIGS = [("RDKit (ETKDGv3) + MMFF94","rdkit","mmff"),("RDKit (ETKDGv3) + UFF","rdkit","uff"),("Open Babel","openbabel","mmff94"),("NetworkX layout","networkx",None)]
T = MolecularTools()
rows=[]
for name, smi in MOLS:
    m = Chem.MolFromSmiles(smi)
    info = dict(name=name, smiles=smi, formula=rdMolDescriptors.CalcMolFormula(m), heavy=m.GetNumHeavyAtoms(),
                atoms=Chem.AddHs(m).GetNumAtoms(), rotb=rdMolDescriptors.CalcNumRotatableBonds(m),
                stereo=len(Chem.FindMolChiralCenters(m, includeUnassigned=True, useLegacyImplementation=False)))
    for label, meth, ff in CONFIGS:
        times=[]; res=None; err=None
        for rep in range(3):
            t=time.perf_counter()
            try:
                res = T.convert(smi, method=meth, force_field=ff or "mmff")
            except Exception as e:
                err=str(e)[:80]; break
            times.append(time.perf_counter()-t)
        r = dict(info, config=label)
        if err: r.update(ok=False, error=err)
        else:
            cc = res.get("connectivity_check") or {}
            sq = res.get("stereo_qa")
            r.update(ok=True, time_s=statistics.median(times), bonds_ok=cc.get("ok"), stereo=sq, keys=list(res.keys()))
        rows.append(r)
json.dump(rows, open(sys.argv[2] if len(sys.argv) > 2 else "benchmark_builders.json", "w"), indent=1, default=str)
print(rows[0]["keys"] if rows[0].get("keys") else rows[0])
