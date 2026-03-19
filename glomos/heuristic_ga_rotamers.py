import numpy as np
from ase.io                import read
from glomos.libutils        import writexyzs, sort_by_energy, cutter_energy, rename, adjacency_matrix
from glomos.libstdio        import read_main_input
from glomos.librotamers     import get_bridge_left_right, make_random_rotamers, make_crossover_rotamers, make_mutant_rotamers
from glomos.libsel_roulette import get_fitness, get_roulette_wheel_selection
from glomos.libdisc_usr     import deduplicate_by_usr, filter_against_reference_usr
from glomos.libcalc_ani    import ANI
ndigit1=3
ndigit2=4
preclist=[1E-03, 1E-04]
#-------------------------------------------------------------------------------
def display_mol_info(moleculein, flagsum=1):
    """Print a ranked energy summary of a rotamer population with optional fitness values.

    in:
        moleculein (list of ase.Atoms): rotamer structures to display; each must have
            info['e'] and info['i'].
        flagsum (int): 1 to include fitness values in the output, 0 to omit them.
    out:
        None.
    """
    if len(moleculein)==0:
        print("\n------------ALL MOLECULES DISCRIMINATED. GLOMOS FINISH.------------")
    molzz=sort_by_energy(moleculein, 1)
    for ii, imol in enumerate(molzz):
        deltae=imol.info['e'] - molzz[0].info['e']
        jj=str(ii+1).zfill(5)
        if flagsum == 1:
            fitness=get_fitness(moleculein)
            print("#%s %-12s %.6f kcal/mol (%.6f) (f=%.2f)" %(jj, imol.info['i'], imol.info['e'], deltae, fitness[ii]))
        else:
            print("#%s %-12s %.6f kcal/mol (%.6f)" %(jj, imol.info['i'], imol.info['e'], deltae))
#-------------------------------------------------------------------------------
def conformational(inputfile='INPUT.txt'):
    """Run the GLOMOS rotamer genetic algorithm for conformational exploration of a molecule.

    in:
        inputfile (str): path to the input file containing the rotamer seed file, algorithm
            parameters, discrimination settings, halt criteria, and theory level.
    out:
        list of ase.Atoms: final sorted population of low-energy conformers.
    """
    #Reading variables
    df = read_main_input(inputfile)
    rotamer_seed=df.get_str(key='rotamer_seed', default='rotamer.xyz')
    nof_initpop=df.get_int(key='nof_initpop', default=10)
    nof_matings=df.get_int(key='nof_matings', default=5)
    nof_mutants=df.get_int(key='nof_mutants', default=5)
    tol_similarity=df.get_float(key='tol_similarity', default=0.95)
    tol_energy=df.get_float(key='tol_energy', default=0.1)
    cutoff_energy=df.get_float(key='cutoff_energy', default=5.0)
    cutoff_population=df.get_int(key='cutoff_population', default=8)
    nof_generations=df.get_int(key='nof_generations', default=3)
    nof_repeats=df.get_int(key='nof_repeats', default=2)
    nof_stagnant=df.get_int(key='nof_stagnant', default=3)
    calculator=df.get_str(key='calculator', default='ANI1ccx')
    nof_processes=df.get_int(key='nof_processes', default=1)
    atoms = read(rotamer_seed, format='xyz') 
    atoms.info['e']=0.0
    atoms.info['i']='Rotamer'
    #Welcome
    adjmatrix = adjacency_matrix(atoms)
    bridgelist = get_bridge_left_right(adjmatrix)
    print('----------------- Genetic Algorithm for Rotamers -----------------')
    print('Chemical Formula      = %s'    %(atoms.get_chemical_formula()))
    if ( len(bridgelist) == 0 ):
        print('Selected XYZ Mol File has not bridges.')
        print('Choose (as seed) a molecule with at least a rotable bond.')
        exit()
    print("Number of bridges     = %d" %(len(bridgelist)))
    for ibridge in range(len(bridgelist)):
        print(' -Bridge[%d]           = (%d, %d)' %(ibridge+1, bridgelist[ibridge][0]+1, bridgelist[ibridge][1]+1))
    print('\nEVOLUTIVE PARAMETERS:')
    print('Initial Population    = %d'    %(nof_initpop))
    print('Number of matings     = %d'    %(nof_matings))
    print('Number of mutants     = %d'    %(nof_mutants))
    print('\nDISCRIMINATION PARAMETERS:')
    print('Tol for similarity    = %4.2f' %(tol_similarity))
    print('Energy Cut-off        = %.2f'  %(cutoff_energy))
    print('Max population size   = %d'    %(cutoff_population))
    print('\nSTOP CRITERION:')
    print('Max generations       = %d'    %(nof_generations))
    print('Max repeated rotamers = %d'    %(nof_repeats))
    print('Max stagnant cycles   = %d'    %(nof_stagnant))
    print()
    print('Theory Level          = %s'    %(calculator))
    #Main Algorithm
    print('---------------------------GENERATION 0---------------------------')
    print('Construction of the guest rotamers. Initial seed (random_000_001) as reference\n')
    xrand=make_random_rotamers(atoms, nof_initpop, bridgelist, adjmatrix)
    rename(xrand, 'random_'+str(0).zfill(ndigit1), ndigit2)
    writexyzs(xrand, 'initial000.xyz')
    print('Optimization at %s:' %(calculator))
    xopt=ANI(xrand, n_jobs=nof_processes, opt=calculator, preclist=preclist)
    writexyzs(xopt, 'initial000_opt.xyz')

    print('')
    print('Discrimination: Energy Cut-off=%.2f; Structural similarity tol=%4.2f;Max population size=%d' %(cutoff_energy, tol_similarity, cutoff_population))
    n1=len(xopt)
    xopt=cutter_energy(xopt, cutoff_energy)
    n2=len(xopt)
    print("Energy Cut-off: [%d -> %d]" % (n1, n2))

    xopt_sort=sort_by_energy(xopt, 1)
    xopt_sort=deduplicate_by_usr(xopt_sort, tol_similarity, tol_energy, mono=False, flag=1)
    xopt_sort=xopt_sort[:cutoff_population]
    print('\nGLOBAL SUMMARY')
    display_mol_info(xopt_sort)
    writexyzs(xopt_sort, 'summary.xyz')
    namesi=[imol.info['i'] for imol in xopt_sort][:nof_repeats]
    count=0
    for igen in range(nof_generations):
        print("\n---------------------------GENERATION %d---------------------------" %(igen+1))
        print('Construction of crossovers ... ', end='', flush=True)
        list_p=get_roulette_wheel_selection(xopt_sort, nof_matings)
        list_m=get_roulette_wheel_selection(xopt_sort, nof_matings)
        atoms_list_out=make_crossover_rotamers(list_p, list_m, bridgelist, adjmatrix)
        rename(atoms_list_out, 'mating_'+str(igen+1).zfill(ndigit1), ndigit2)
        n3=len(atoms_list_out)
        print("[%d of %d]" % (n3, nof_matings))

        print('Construction of mutants    ... ')
        atoms_list_mut=make_mutant_rotamers(xopt_sort[:nof_mutants], bridgelist, adjmatrix)
        rename(atoms_list_mut, 'mutant_'+str(igen+1).zfill(ndigit1), ndigit2)

        print('Optimization at %s:' %(calculator))
        generation_opt=ANI(atoms_list_out+atoms_list_mut, n_jobs=nof_processes, opt=calculator, preclist=preclist)
        writexyzs(generation_opt, 'initial'+str(igen+1).zfill(3)+'_opt.xyz')
        print('\nDiscrimination: Energy Cut-off=%.2f; Structural similarity tol=%4.2f;Max population size=%d' %(cutoff_energy, tol_similarity, cutoff_population))

        generation_opt=cutter_energy(generation_opt, cutoff_energy)
        generation_opt=sort_by_energy(generation_opt,1)
        generation_opt=deduplicate_by_usr(generation_opt, tol_similarity, tol_energy, mono=False, flag=1)
        generation_opt=filter_against_reference_usr(generation_opt, xopt_sort, tols=tol_similarity, tole=tol_energy, mono=False, flag=1)
        xopt_sort=sort_by_energy(xopt_sort+generation_opt, 1)
        xopt_sort=xopt_sort[:cutoff_population]
        print('\nGLOBAL SUMMARY')
        display_mol_info(xopt_sort)
        writexyzs(xopt_sort, 'summary.xyz')
        namesj=[imol.info['i'] for imol in xopt_sort][:nof_repeats]
        numij=[1 for i, j in zip(namesi,namesj) if i == j]
        count=count+1 if sum(numij) == nof_repeats else 1
        if count == nof_stagnant:
            print("\nEarly termination. Max repeated isomers (%d) reached at the Max stagnant cycles (%d)." %(nof_repeats, nof_stagnant))
            break
        namesi=namesj
    print("\nGlobal optimization complete.")
    return xopt_sort
#-------------------------------------------------------------------------------
