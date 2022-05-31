from gpaw import GPAW, PW
import copy, os

def setup_gpaw(settings_inp):
    settings = settings_inp['calc']
    control = settings_inp['control']
    if control.get('cider') is not None:
        from mldftdat.gpaw.cider_paw import CiderGGAPASDW
        cider_settings = control['cider']
        fname = cider_settings.pop('fname')
        settings['xc'] = CiderGGAPASDW.from_joblib(
            fname, **cider_settings
        )
    if control['mode'] != 'fd':
        settings['mode'] = PW(control['mode'])
    return GPAW(**settings)

def call_gpaw():
    import yaml
    import sys
    import ase.io
    from ase.parallel import paropen
    from ase.units import Ha
    from gpaw import KohnShamConvergenceError

    with open(sys.argv[1], 'r') as f:
        settings = yaml.load(f, Loader=yaml.Loader)
    atoms = ase.io.read(sys.argv[2])
    atoms.calc = setup_gpaw(settings)
    try:
        e_tot = atoms.get_potential_energy()
        converged = True
    except KohnShamConvergenceError as e:
        converged = False

    with paropen('gpaw_outdata.tmp', 'w') as f:
        f.write('e_tot : {}\n'.format(e_tot / Ha))
        f.write('converged : {}\n'.format(converged))
        txtfile = settings['calc'].get('txt')
        if txtfile is not None:
            assert os.path.exists(txtfile)
            f.write('logfile : {}\n'.format(os.path.abspath(txtfile)))
        else:
            f.write('logfile : None\n')

    if settings['control'].get('save_calc') is not None:
        assert settings['control']['save_calc'].endswith('.gpw')
        atoms.calc.write(settings['control']['save_calc'], mode='all')


if __name__ == '__main__':
    call_gpaw()
