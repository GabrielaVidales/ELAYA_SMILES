import time
import warnings
warnings.filterwarnings("ignore", message="cuaev not installed")
warnings.filterwarnings("ignore", category=UserWarning, module="torchani")
import os
import sys
os.environ['TORCHANI_NO_WARN_EXTENSIONS'] = "1"
import torch
if not hasattr(torch.compiler, 'is_compiling'):
    torch.compiler.is_compiling = lambda: False
import torchani
import queue
import contextlib
from multiprocessing import Process, Queue
from ase.optimize import BFGS
from glomos.libutils import readxyzs, writexyzs
#-------------------------------------------------------------------------------
#EN MODO PRUEBA
os.environ['TORCHANI_NO_WARN_EXTENSIONS'] = "1"
eVtokcalpermol = 23.060548012069496
#-------------------------------------------------------------------------------
@contextlib.contextmanager
def suppress_stdout():
    with open(os.devnull, "w") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:
            yield
        finally:
            sys.stdout = old_stdout
#-------------------------------------------------------------------------------
def ANI_single(atoms, opt='ANI1ccx', preclist=[1E-03, 1E-04, 1E-05]):
    timein=time.strftime("%c")
    print('%s at %s' %(atoms.info['i'], timein))
    moleculeout=atoms.copy()
    for prec in preclist:
        with suppress_stdout():
            calculator = {
                'ANI1x':   torchani.models.ANI1x().ase(),
                'ANI1ccx': torchani.models.ANI1ccx().ase(),
                'ANI2x':   torchani.models.ANI2x().ase()
            }[opt]
        moleculeout.calc = calculator
        dyn = BFGS(moleculeout, logfile=None)
        dyn.run(fmax=prec, steps=200)
    energy = moleculeout.get_potential_energy()
    moleculeout.info['e'] = energy * eVtokcalpermol
    return moleculeout
#-------------------------------------------------------------------------------
def ANI_single_to_file(atoms, outname, opt='ANI1ccx', preclist=[1E-03, 1E-04, 1E-05]):
    moleculeout= ANI_single(atoms, opt, preclist)
    writexyzs(moleculeout, outname)
#-------------------------------------------------------------------------------
def do_job(tasks_to_accomplish, tasks_that_are_done, opt='ANI1ccx', preclist=[1E-03, 1E-04, 1E-05]):
    while True:
        try:
            task = tasks_to_accomplish.get_nowait()
        except queue.Empty:
            break
        else:
            mol = task
            outname = f"{mol.info['i']}_opt.xyz"
            ANI_single_to_file(mol, outname, opt, preclist)
            tasks_that_are_done.put(outname)
#-------------------------------------------------------------------------------
def ANI(moleculelist, n_jobs=1, opt='ANI1ccx', preclist=[1E-03, 1E-04, 1E-05]):
    tasks_to_accomplish = Queue()
    tasks_that_are_done = Queue()
    processes = []
    for mol in moleculelist:
        tasks_to_accomplish.put(mol)
    for _ in range(n_jobs):
        p = Process(target=do_job, args=(tasks_to_accomplish, tasks_that_are_done, opt, preclist))
        processes.append(p)
        p.start()
    for p in processes:
        p.join()
    optimized_molecules = []
    while not tasks_that_are_done.empty():
        xyzfile = tasks_that_are_done.get()
        mol = readxyzs(xyzfile)[0]
        mol.info['c']=1
        optimized_molecules.append(mol)
        os.remove(xyzfile)
    return optimized_molecules
#-------------------------------------------------------------------------------
#from joblib import Parallel, delayed
#def ANI_parallel_without_queuing(mol_list, n_jobs = 1, opt='ANI1ccx', preclist=[1E-03, 1E-04, 1E-05]):
#    results = Parallel(n_jobs = n_jobs)(delayed(ANI)(mol, opt, preclist) for mol in mol_list)
#    return results
#-------------------------------------------------------------------------------
