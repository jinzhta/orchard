import time
from pyscf import scf
import os, time
import numpy as np
from ciderpress.analyzers import ElectronAnalyzer, RHFAnalyzer, UHFAnalyzer
from orchard.workflow_utils import get_save_dir, SAVE_ROOT, load_mol_ids
from ciderpress.density import get_exchange_descriptors2, LDA_FACTOR, GG_AMIN
from ciderpress.data import get_unique_coord_indexes_spherical, get_total_weights_spherical
import logging
import yaml
from ase.data import chemical_symbols, atomic_numbers, ground_state_magnetic_moments
from collections import Counter

from argparse import ArgumentParser

"""
Script to compile a dataset from the CIDER DB for training a CIDER functional.
"""

def compile_dataset2(DATASET_NAME, MOL_IDS, SAVE_ROOT, FUNCTIONAL, BASIS,
                     spherical_atom=False, version='a', sparse_level=None,
                     analysis_level=1, **gg_kwargs):

    all_descriptor_data = []
    all_rho_data = []
    all_values = []
    all_weights = []
    cutoffs = [0]

    for MOL_ID in MOL_IDS:
        logging.info('Computing descriptors for {}'.format(MOL_ID))
        data_dir = get_save_dir(SAVE_ROOT, 'KS', BASIS, MOL_ID, FUNCTIONAL)
        start = time.monotonic()
        analyzer = ElectronAnalyzer.load(data_dir + '/analysis_L{}.hdf5'.format(analysis_level))
        if sparse_level is not None:
            Analyzer = UHFAnalyzer if analyzer.atype == 'UHF' else RHFAnalyzer
            analyzer = Analyzer(analyzer.mol, analyzer.dm, grids_level=sparse_level)
            analyzer.perform_full_analysis()
            level = sparse_level
        else:
            analyzer.get_rho_data()
            level = analysis_level
        if isinstance(level, int):
            sparse_tag = '_{}'.format(level)
        else:
            sparse_tag = '_{}_{}'.format(level[0], level[1])
        restricted = False if analyzer.atype == 'UHF' else True
        end = time.monotonic()
        logging.info('Analyzer load time {}'.format(end - start))

        if spherical_atom:
            start = time.monotonic()
            indexes = get_unique_coord_indexes_spherical(analyzer.grids.coords)
            uwts = get_total_weights_spherical(analyzer.grids.coords[indexes], analyzer.grids.coords, analyzer.grids.weights)
            end = time.monotonic()
            logging.info('Index scanning time {}'.format(end - start))
        start = time.monotonic()
        if restricted:
            descriptor_data = get_exchange_descriptors2(
                analyzer, restricted=True, version=version,
                **gg_kwargs
            )
        else:
            descriptor_data_u, descriptor_data_d = \
                              get_exchange_descriptors2(
                                analyzer, restricted=False, version=version,
                                **gg_kwargs
                              )
            descriptor_data = np.append(descriptor_data_u, descriptor_data_d,
                                        axis=1)
        end = time.monotonic()
        logging.info('Get descriptor time {}'.format(end - start))
        values = analyzer.get('ex_energy_density')
        rho_data = analyzer.rho_data
        if spherical_atom:
            if not restricted:
                raise ValueError('Spherical atom not supported with spin pol.')
            values = values[indexes]
            descriptor_data = descriptor_data[:,indexes]
            rho_data = rho_data[:,indexes]
            weights = uwts
        else:
            weights = analyzer.grids.weights
        if not restricted:
            values = 2 * np.append(values[0], values[1])
            rho_data = 2 * np.append(rho_data[0], rho_data[1], axis=1)
            weights = 0.5 * np.append(weights, weights)

        all_rho_data.append(rho_data)
        all_values.append(values)
        all_weights.append(weights)
        all_descriptor_data.append(descriptor_data)
        cutoffs.append(cutoffs[-1] + values.size)

    all_rho_data = np.concatenate(all_rho_data, axis=-1)
    all_values = np.concatenate(all_values)
    all_weights = np.concatenate(all_weights)
    all_descriptor_data = np.concatenate(all_descriptor_data, axis=-1)

    DATASET_NAME = os.path.basename(DATASET_NAME)
    save_dir = os.path.join(SAVE_ROOT, 'DATASETS',
                            FUNCTIONAL, BASIS, version+sparse_tag, DATASET_NAME)
    if not os.path.isdir(save_dir):
        os.makedirs(save_dir, exist_ok=True)
    rho_file = os.path.join(save_dir, 'rho.npy')
    desc_file = os.path.join(save_dir, 'desc.npy')
    val_file = os.path.join(save_dir, 'val.npy')
    wt_file = os.path.join(save_dir, 'wt.npy')
    cut_file = os.path.join(save_dir, 'cut.npy')
    np.save(rho_file, all_rho_data)
    np.save(desc_file, all_descriptor_data)
    np.save(val_file, all_values)
    np.save(wt_file, all_weights)
    np.save(cut_file, np.array(cutoffs))
    settings = {
        'DATASET_NAME': DATASET_NAME,
        'MOL_IDS': MOL_IDS,
        'SAVE_ROOT': SAVE_ROOT,
        'FUNCTIONAL': FUNCTIONAL,
        'BASIS': BASIS,
        'spherical_atom': spherical_atom,
        'version': version,
    }
    settings.update(gg_kwargs)
    with open(os.path.join(save_dir, 'settings.yaml'), 'w') as f:
        yaml.dump(settings, f)


def main():
    logging.basicConfig(level=logging.INFO)

    m_desc = 'Compile dataset of XC descriptors'

    parser = ArgumentParser(description=m_desc)
    parser.add_argument('mol_id_file', type=str,
                        help='yaml file from which to read mol_ids to parse')
    parser.add_argument('basis', metavar='basis', type=str,
                        help='basis set code')
    parser.add_argument('--functional', metavar='functional', type=str, default=None,
                        help='exchange-correlation functional, HF for Hartree-Fock')
    parser.add_argument('--spherical-atom', action='store_true',
                        default=False, help='whether dataset contains spherical atoms')
    parser.add_argument('--version', default='c', type=str,
                        help='version of descriptor set. Default c')
    parser.add_argument('--gg-a0', default=8.0, type=float)
    parser.add_argument('--gg-facmul', default=1.0, type=float)
    parser.add_argument('--gg-amin', default=GG_AMIN, type=float)
    parser.add_argument('--gg-vvmul', default=1.0, type=float, help='For version b only, mul to get second coord exponent')
    parser.add_argument('--suffix', default=None, type=str,
                        help='customize data directories with this suffix')
    parser.add_argument('--analysis-level', default=1, type=int,
                        help='Level of analysis to search for each system, looks for analysis_L{analysis-level}.hdf5')
    parser.add_argument('--sparse-grid', default=None, type=int, nargs='+',
                        help='use a sparse grid to compute features, etc. If set, recomputes data.')
    args = parser.parse_args()

    version = args.version.lower()
    if version not in ['a', 'b', 'c', 'd', 'e', 'f']:
        raise ValueError('Unsupported descriptor set')

    mol_ids = load_mol_ids(args.mol_id_file)
    if args.mol_id_file.endswith('.yaml'):
        mol_id_code = args.mol_id_file[:-5]
    else:
        mol_id_code = args.mol_id_file

    dataname = 'XTR{}_{}'.format(version.upper(), mol_id_code.upper())
    if args.spherical_atom:
        pass#dataname = 'SPH_' + dataname
    if args.suffix is not None:
        dataname = dataname + '_' + args.suffix

    if args.sparse_grid is None:
        sparse_level = None
    elif len(args.sparse_grid) == 1:
        sparse_level = args.sparse_grid[0]
    elif len(args.sparse_grid) == 2:
        sparse_level = (args.sparse_grid[0], args.sparse_grid[1])
    else:
        raise ValueError('Sparse grid must be 1 or 2 integers')

    gg_kwargs = {
        'amin': args.gg_amin,
        'a0': args.gg_a0,
        'fac_mul': args.gg_facmul
    }
    if version in ['b', 'd', 'e']:
        gg_kwargs['vvmul'] = args.gg_vvmul
    compile_dataset2(
        dataname, mol_ids, SAVE_ROOT, args.functional, args.basis, 
        spherical_atom=args.spherical_atom, version=version,
        analysis_level=args.analysis_level, sparse_level=sparse_level,
        **gg_kwargs
    )

if __name__ == '__main__':
    main()

