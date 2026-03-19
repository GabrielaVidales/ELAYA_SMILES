import random
import numpy as np
from glomos.libutils import sort_by_energy
#-------------------------------------------------------------------------------
def get_fitness(moleculelist):
    """Compute a fitness value in (0, 1] for each structure based on energy ranking.

in:
    moleculelist (list of ase.Atoms): structures to evaluate; each must have info['e'].
out:
    list of float: fitness values in (0, 1] sorted from lowest to highest energy.
    Uses a tanh-based transformation: fi = 0.5 * (1 - tanh(2*EFEi - 1)) where
    EFEi is the normalized energy fraction (Ei-Emin)/(Emax-Emin).
"""
    if len(moleculelist)==1:
       fitness=[float(1.0)]
    else:
       fitness=[]
       listmolecule=sort_by_energy(moleculelist,1)
       Emin=listmolecule[0].info['e']
       Emax=listmolecule[-1].info['e']
       for imol in listmolecule:
           Ei=imol.info['e']
           EFEi=(Ei-Emin)/(Emax-Emin)
           fi=0.5*(1.0-np.tanh(((2.0*EFEi)-1.0)))
           fitness.append(float(fi))
    return fitness
#-------------------------------------------------------------------------------
def get_roulette_wheel_selection(moleculelist, nmating):
    """Select structures from a population using fitness-proportional roulette wheel selection.

in:
    moleculelist (list of ase.Atoms): population to select from; each must have info['e'].
    nmating (int): number of structures to select (with replacement).
out:
    list of ase.Atoms: nmating structures sampled proportionally to their fitness.
    Lower-energy structures have higher fitness and are more likely to be selected.
"""
    listmolecule=sort_by_energy(moleculelist,1)
    fitness=get_fitness(listmolecule)
    sum_of_fitness=sum(fitness)
    previous_probability=0.0
    n=len(listmolecule)
    pp=[]
    for ix in range(n):
        previous_probability= previous_probability+ (fitness[ix]/sum_of_fitness)
        if ix==n-1: pp.append(1.0)
        else: pp.append(previous_probability)
    roulette = []
    for i in range(nmating):
        random_number = random.random()
        for ii, p in enumerate(pp):
            if random_number <= p:
                roulette.append(listmolecule[ii])
                break
    return roulette
#-------------------------------------------------------------------------------
