import random
import numpy as np
import networkx as nx
from ase import Atoms
from glomos.libutils import adjacency_matrix, rodrigues_rotation_matrix, rotate_vector_angle_deg, rename
#-------------------------------------------------------------------------------
zeta=np.array([0.0, 0.0, 1.0])
zero=np.array([0.0, 0.0, 0.0])
ndigit=5
#-------------------------------------------------------------------------------
def get_bridge_left_right(adjmatrix):
    """Find all bridge bonds and their left/right fragment atom index lists.

in:
    adjmatrix (numpy.ndarray): square adjacency matrix of the molecular graph.
out:
    list of list: each entry is [atom_a, atom_b, left_indices, right_indices] where
    (atom_a, atom_b) is a bridge bond, left_indices and right_indices are the atom
    index lists of the two fragments (left has fewer atoms). Only bridges where both
    fragments have more than one atom are included.
"""
    G = nx.from_numpy_array(adjmatrix)
    bridges = list(nx.bridges(G))
    all=[]
    for bridge in bridges:
        [u, v] = bridge
        G_temp = G.copy()
        G_temp.remove_edge(u, v)
        componentes = list(nx.connected_components(G_temp))
        left,right=list(componentes[0]),list(componentes[1])
        if len(left)>1 and len(right)>1:
            (a,b)=bridge
            if len(left) <= len(right):
                all.append([a, b, left, right])
            else:
                all.append([b, a, right, left])
    return all
#-------------------------------------------------------------------------------
def dihedral_rotation(moleculein, bridgelist, ibridge, qdeg):
    """Rotate atoms on the 'left' side of a bridge bond by a given angle.

in:
    moleculein (ase.Atoms): structure to rotate in-place.
    bridgelist (list of list): bridge list from get_bridge_left_right.
    ibridge (int): index into bridgelist specifying which bond to rotate around.
    qdeg (float): rotation angle in degrees.
out:
    ase.Atoms: the modified structure (same object, rotated in-place).
"""
    sua=bridgelist[ibridge][0]
    nua=bridgelist[ibridge][1]
    lista=bridgelist[ibridge][2]
    vec=(moleculein[sua].position - moleculein[nua].position)
    vet=(moleculein[sua].position + moleculein[nua].position)/2.0
    rodriguesrm=rodrigues_rotation_matrix(vec, qdeg)
    for ii in range(len(moleculein)):
        if ii in lista:
            vri = np.matmul(rodriguesrm, moleculein[ii].position - vet)
            moleculein[ii].position=vri + vet
    return moleculein
#-------------------------------------------------------------------------------
def check_connectivity(atoms, adjmatrix_ref):
    """Check whether the current structure has the same connectivity as a reference.

in:
    atoms (ase.Atoms): structure whose adjacency matrix is computed and compared.
    adjmatrix_ref (numpy.ndarray): reference adjacency matrix to compare against.
out:
    bool: True if the adjacency matrices match, False otherwise.
"""
    adjmatrix_x=adjacency_matrix(atoms)
    return ( np.array_equiv(adjmatrix_x,adjmatrix_ref) or np.array_equal(adjmatrix_x,adjmatrix_ref) )
#-------------------------------------------------------------------------------
def rattle(moleculeseed, bridgelist, adjmatrix_ref, qdegamp=180.0):
    """Apply random dihedral rotations to all bridges while preserving connectivity.

in:
    moleculeseed (ase.Atoms): starting structure.
    bridgelist (list of list): bridge list from get_bridge_left_right.
    adjmatrix_ref (numpy.ndarray): reference adjacency matrix for connectivity checks.
    qdegamp (float): maximum rotation amplitude in degrees (default 180.0).
out:
    ase.Atoms: new conformer with each bridge bond rotated by a random valid angle.
"""
    nbridges=len(bridgelist)
    moleculeout=moleculeseed.copy()
    for ibridge in range(nbridges):
        fall = True
        while fall:
            qdeg=random.randint(-int(qdegamp),int(qdegamp))
            dihedral_rotation(moleculeout, bridgelist, ibridge, qdeg)
            fall = False if ( check_connectivity(moleculeout, adjmatrix_ref) ) else True
    return moleculeout
#-------------------------------------------------------------------------------
def make_random_rotamers(moleculeseed, number, bridgelist, adjmatrix_ref):
    """Generate a set of random conformers (rotamers) from a seed structure.

in:
    moleculeseed (ase.Atoms): reference conformer.
    number (int): total number of conformers to generate (including the seed).
    bridgelist (list of list): bridge list from get_bridge_left_right.
    adjmatrix_ref (numpy.ndarray): reference adjacency matrix for connectivity checks.
out:
    list of ase.Atoms: list of conformers with info['i'] labeled 'seed00_NNNNN'
    for the first and 'random_NNNNN' for subsequent ones; info['e']=0.0.
"""
    qdegamp=180
    id='seed00_'+str(1).zfill(ndigit)
    #print("\nBuild guest rotamer: %s (Initial seed as reference)" %(id))
    moleculetmp=moleculeseed.copy()
    moleculetmp.info['i']=id
    moleculeout=[moleculetmp]
    for key in range(number-1):
        id='random_'+str(int(key+2)).zfill(ndigit)
        #print("Build guest rotamer: %s" %(id))
        moleculetmp=rattle(moleculeseed, bridgelist, adjmatrix_ref, qdegamp)
        moleculetmp.info['i']=id
        moleculetmp.info['e']=0.0
        moleculeout.extend([moleculetmp])
    return moleculeout
#-------------------------------------------------------------------------------
def make_mutant_rotamers(rotamerlist, bridgelist, adjmatrix_ref):
    """Create mutant conformers by accumulating rotations around the two most symmetric bridges.

in:
    rotamerlist (list of ase.Atoms): input conformers to mutate.
    bridgelist (list of list): bridge list from get_bridge_left_right.
    adjmatrix_ref (numpy.ndarray): reference adjacency matrix for connectivity checks.
out:
    list of ase.Atoms: mutated conformers with info['i'] labeled 'mutant_NNNNN'
    and info['e']=0.0. Up to 25 attempts are made per bridge rotation.

Strategy:
    - Start from input rotamer.
    - Apply random rotation to bridge 1 (most symmetric).
    - If valid: keep and continue to bridge 2.
    - If invalid: try another angle (up to 25 attempts).
    - Repeat for bridge 2, starting from the state after bridge 1.
"""
    qdegamp = 180
    max_attempts = 25

    # Sort bridges by symmetry (smallest difference in fragment sizes)
    lista = [[i, np.abs(len(xa[2]) - len(xa[3]))] for i, xa in enumerate(bridgelist)]
    liste = sorted(lista, key=lambda x: float(x[1]))
    indexes = [x[0] for x in liste]

    moleculeout = []

    for i, imol in enumerate(rotamerlist):
        # Start with the input rotamer (this will accumulate rotations)
        tmp = imol.copy()

        # Rotate around the 2 most symmetric bridges (accumulative)
        for bridge_idx, index in enumerate(indexes[:2]):
            success = False
            attempts = 0

            while not success and attempts < max_attempts:
                # Try a rotation starting from current accumulated state
                tmp_attempt = tmp.copy()  # Copy current state (with previous rotations)

                # Generate random rotation angle
                qdeg = random.randint(-int(qdegamp), int(qdegamp))

                # Apply rotation
                dihedral_rotation(tmp_attempt, bridgelist, index, qdeg)

                # Check if connectivity is preserved
                if check_connectivity(tmp_attempt, adjmatrix_ref):
                    # SUCCESS: Keep this rotation and continue accumulating
                    tmp = tmp_attempt  # Update to new valid state
                    success = True
                    print(f"  Mutant {i+1}/{len(rotamerlist)} - Bridge {bridge_idx+1}/2: {qdeg:+4d}° applied",
                          end='\r', flush=True)
                else:
                    # FAILED: Discard tmp_attempt, try another angle
                    # tmp remains unchanged (keeps previous valid rotations)
                    pass

                attempts += 1

            if not success:
                # Clear the progress line before printing warning
                print(" " * 80, end='\r', flush=True)
                print(f"WARNING: Mutant {i+1} - Could not rotate bridge {index} after {max_attempts} attempts")

        # Assign new ID and add to output
        id_name = 'mutant_' + str(i + 1).zfill(ndigit)
        tmp.info['i'] = id_name
        tmp.info['e'] = 0.0
        moleculeout.append(tmp)

        # Clear the progress line
        print(" " * 80, end='\r', flush=True)
        print(f"Mutant {i+1}/{len(rotamerlist)}: {id_name} created", end='\r', flush=True)

    print()  # New line at the end
    return moleculeout
#-------------------------------------------------------------------------------
def align_bond_to_z(atoms, i, j):
    """Rotate a molecule so that the bond between atoms i and j is aligned with Z.

in:
    atoms (ase.Atoms): molecular structure.
    i (int): index of the first bond atom.
    j (int): index of the second bond atom.
out:
    ase.Atoms: copy of the structure rotated so that bond i-j lies along the Z axis.
    Returns an unmodified copy if the bond is already along Z.
"""
    vec=(atoms[j].position - atoms[i].position)
    vet=(atoms[j].position + atoms[i].position)/2.0
    gv1=vec/np.linalg.norm(vec)
    moleculeout=atoms.copy()
    if ( np.cross(gv1, zeta) == zero).all():
        return moleculeout
    m1 = np.array([gv1[1], -gv1[0], 0.0])
    m2 = np.cross(gv1, m1)
    tmatrix = np.array([m1, m2, gv1])
    moleculeout.set_positions(np.dot(atoms.get_positions() - vet, tmatrix.T))
    return moleculeout
#-------------------------------------------------------------------------------
def crossover_rotamers(mola, molb, bridgelist, adjmatrix_ref):
    """Perform a crossover between two conformers by swapping fragments at a bridge bond.

in:
    mola (ase.Atoms): first parent conformer.
    molb (ase.Atoms): second parent conformer.
    bridgelist (list of list): bridge list from get_bridge_left_right.
    adjmatrix_ref (numpy.ndarray): reference adjacency matrix for connectivity checks.
out:
    ase.Atoms: child conformer combining the left fragment of mola with the right
    fragment of molb (rotated in 5-degree steps until connectivity is preserved);
    False if no valid rotation is found.
"""
    lista=[[i, np.abs(len(xa[2])-len(xa[3]))] for i,xa in enumerate(bridgelist)]
    liste = sorted(lista, key=lambda x: float(x[1]))
    indexes=[x[0] for x in liste]
    moleculeout=[]
    for index in indexes:
        i=bridgelist[index][0]
        j=bridgelist[index][1]
        aliga=align_bond_to_z(mola, i, j)
        aligb=align_bond_to_z(molb, i, j)
        left=bridgelist[index][2]
        right=bridgelist[index][3]
        for angle in range(0, 360, 5):
            var=aligb.copy()
            rotate_vector_angle_deg(var, zeta, angle)
            hijo=aliga.copy()
            for ii in right: hijo[ii].position=var[ii].position
            test=check_connectivity(hijo, adjmatrix_ref)
            if test:
                hijo.info['e']=float(0.0)
                hijo.info['i']='pre_child'+str(angle).zfill(4)
                return hijo
    if test is False: return False
#-------------------------------------------------------------------------------
def make_crossover_rotamers(papy, mamy, bridgelist, adjmatrix_ref):
    """Apply conformer crossover to paired lists of parent structures.

in:
    papy (list of ase.Atoms): first list of parent conformers.
    mamy (list of ase.Atoms): second list of parent conformers (same length as papy).
    bridgelist (list of list): bridge list from get_bridge_left_right.
    adjmatrix_ref (numpy.ndarray): reference adjacency matrix for connectivity checks.
out:
    list of ase.Atoms: child conformers from successful crossovers, renamed with
    'mating' prefix and ndigit zero-padding.
"""
    moleculeout=[]
    total_molecules=len(papy)
    for imol in range(total_molecules):
         ichildren=crossover_rotamers(papy[imol],mamy[imol],bridgelist, adjmatrix_ref)
         if ichildren: moleculeout.extend([ichildren])
    rename(moleculeout, 'mating', ndigit)
    return moleculeout
