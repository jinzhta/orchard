import os
from orchard.workflow_utils import MLDFTDB_ROOT, read_accdb_structure, get_save_dir
import yaml
import numpy as np

KCAL_PER_HA = 627.509608

def get_run_energy_and_nbond(dirname):
    with open(os.path.join(dirname, 'run_info.yaml'), 'r') as f:
        data = yaml.load(f, Loader=yaml.Loader)
    nb = 0#get_nbond(data['mol']['atom'])
    return data['e_tot'], nb

def get_run_total_energy(dirname):
    with open(os.path.join(dirname, 'run_info.yaml'), 'r') as f:
        data = yaml.load(f, Loader=yaml.Loader)
    return data['e_tot']

def get_accdb_data(formula, FUNCTIONAL, BASIS, per_bond=False):
    pred_energy = 0
    if per_bond:
        nbond = 0
        #nbond = None
    for sname, count in zip(formula['structs'], formula['counts']):
        struct, mol_id, spin, charge = read_accdb_structure(sname)
        mol_id = mol_id.replace('ACCDB', 'GMTKN55')
        CALC_TYPE = 'KS'
        dname = get_save_dir(MLDFTDB_ROOT, CALC_TYPE, BASIS, mol_id, FUNCTIONAL)
        if per_bond:
            en, nb = get_run_energy_and_nbond(dname)
            pred_energy += count * en
            nbond += count * nb
        else:
            pred_energy += count * get_run_total_energy(dname)

    if per_bond:
        return pred_energy, formula['energy'], abs(nbond)
    else:
        return pred_energy, formula['energy']

def get_accdb_formulas(dataset_eval_name):
    with open(dataset_eval_name, 'r') as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            lines[i] = line.split(',')
        formulas = {}
        for line in lines:
            counts = line[1:-1:2]
            structs = line[2:-1:2]
            energy = float(line[-1])
            counts = [int(c) for c in counts]
            formulas[line[0]] = {'structs': structs, 'counts': counts, 'energy': energy}
    return formulas

def parse_dataset_eval(subdb_names, dataset_fname):
    formulas = get_accdb_formulas(dataset_fname)
    cats = {}
    sumabs = {}
    counts = {}
    for name in subdb_names:
        cats[name] = []
        sumabs[name] = 0
        counts[name] = 0
    for dname, formula in list(formulas.items()):
        for name in subdb_names:
            if dname.startswith(name):
                cats[name].append(dname)
                counts[name] += 1
                sumabs[name] += abs(formula['energy'])
                break
        else:
            raise RuntimeError('Datapoint {} not matched to subdb'.format(dname))
    return cats, counts, sumabs

def get_accdb_performance(dataset_eval_name, FUNCTIONAL, BASIS, data_names,
                          per_bond=False, comp_functional=None):
    formulas = get_accdb_formulas(dataset_eval_name)
    result = {}
    errs = []
    nbonds = 0
    for data_point_name, formula in list(formulas.items()):
        if data_point_name not in data_names:
            continue
        pred_energy, energy, nbond = get_accdb_data(formula, FUNCTIONAL, BASIS,
                                                    per_bond=True)
        nbonds += nbond
        result[data_point_name] = {
            'pred' : pred_energy,
            'true' : energy
        }
        print(data_point_name, pred_energy * KCAL_PER_HA, energy * KCAL_PER_HA)
        if comp_functional is not None:
            pred_ref, _, _ = get_accdb_data(formula, comp_functional, BASIS,
                                            per_bond=True)
            energy = pred_ref
            result[data_point_name]['true'] = pred_ref
        #print(pred_energy-energy, pred_energy, energy)
        errs.append(pred_energy-energy)
    errs = np.array(errs)
    #print(errs.shape)
    me = np.mean(errs)
    mae = np.mean(np.abs(errs))
    rmse = np.sqrt(np.mean(errs**2))
    std = np.std(errs)
    if per_bond:
        return nbonds, np.sum(errs) / nbonds, np.sum(np.abs(errs)) / nbonds
    else:
        return me, mae, rmse, std, result

def get_accdb_errors(formulas, FUNCTIONAL, BASIS, data_names, comp_functional=None):
    errs = []
    result = {}
    for data_name in data_names:
        pred_energy, energy = get_accdb_data(formulas[data_name], FUNCTIONAL, BASIS)
        if comp_functional is not None:
            energy, _ = get_accdb_data(formulas[data_name], comp_functional, BASIS)
            energy *= KCAL_PER_HA
        pred_energy *= KCAL_PER_HA
        result[data_name] = {
            'pred' : pred_energy,
            'true' : energy,
        }
        errs.append(pred_energy-energy)
    errs = np.array(errs)
    me = np.mean(errs)
    mae = np.mean(np.abs(errs))
    rmse = np.sqrt(np.mean(errs**2))
    std = np.std(errs)
    return me, mae, rmse, std, result