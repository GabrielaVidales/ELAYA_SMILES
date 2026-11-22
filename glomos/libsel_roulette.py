import random
import numpy as np
from glomos.libutils import sort_by_energy
#-------------------------------------------------------------------------------
def get_fitness(moleculelist):
    """Fitness in (0, 1] for each structure, ordered from lowest to highest energy.

in:
    moleculelist (list of ase.Atoms): structures; each needs info['e'] (kcal/mol).
out:
    list of float. fi = 0.5 * (1 - tanh(2*EFEi - 1)) with EFEi = (Ei-Emin)/(Emax-Emin).

Fix: the original divided by (Emax - Emin), which raised ZeroDivisionError for a
population whose members share the same energy. In that degenerate case every
structure now gets the same fitness.
"""
    if len(moleculelist) == 0:
        return []
    if len(moleculelist) == 1:
        return [1.0]
    listmolecule = sort_by_energy(moleculelist, 1)
    Emin = float(listmolecule[0].info['e'])
    Emax = float(listmolecule[-1].info['e'])
    span = Emax - Emin
    if span < 1e-12:
        return [1.0] * len(listmolecule)
    fitness = []
    for imol in listmolecule:
        EFEi = (float(imol.info['e']) - Emin) / span
        fitness.append(float(0.5 * (1.0 - np.tanh((2.0 * EFEi) - 1.0))))
    return fitness
#-------------------------------------------------------------------------------
def get_roulette_wheel_selection(moleculelist, nmating, rng=None):
    """Fitness-proportional (roulette wheel) selection with replacement.

in:
    moleculelist (list of ase.Atoms): population; each needs info['e'].
    nmating (int): number of structures to draw.
    rng: optional ``random.Random`` instance (reproducible runs); defaults to the
        module-level generator.
out:
    list of ase.Atoms (lower energy -> more likely to be drawn).
"""
    if len(moleculelist) == 0 or nmating <= 0:
        return []
    rnd = rng.random if rng is not None else random.random
    listmolecule = sort_by_energy(moleculelist, 1)
    fitness = get_fitness(listmolecule)
    total = sum(fitness)
    cumulative, running = [], 0.0
    for f in fitness:
        running += f / total
        cumulative.append(running)
    cumulative[-1] = 1.0
    roulette = []
    for _ in range(nmating):
        x = rnd()
        for ii, p in enumerate(cumulative):
            if x <= p:
                roulette.append(listmolecule[ii])
                break
    return roulette
#-------------------------------------------------------------------------------
