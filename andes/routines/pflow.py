from collections import OrderedDict

from andes.utils.misc import elapsed
from andes.routines.base import BaseRoutine
from andes.variables.report import Report
from andes.shared import np, matrix, sparse, newton_krylov

import logging
logger = logging.getLogger(__name__)


class PFlow(BaseRoutine):

    def __init__(self, system=None, config=None):
        super().__init__(system, config)
        self.config.add(OrderedDict((('tol', 1e-6),
                                     ('max_iter', 25),
                                     ('report', 1),
                                     )))
        self.models = system.get_models_with_flag('pflow')

        self.converged = False
        self.inc = None
        self.A = None
        self.niter = None
        self.mis = []

    def _initialize(self):
        self.converged = False
        self.inc = None
        self.A = None
        self.niter = None
        self.mis = []
        self.system.initialize(self.models)
        logger.info('Power flow initialized.')
        return self.system.dae.xy

    def nr_step(self):
        """
        Single stepping for Newton Raphson method
        Returns
        -------

        """
        system = self.system
        # evaluate discrete, differential, algebraic, and jacobians
        system.e_clear()
        system.l_update_var()
        system.f_update()
        system.g_update()
        system.l_check_eq()
        system.l_set_eq()
        system.fg_to_dae()
        system.j_update()

        # prepare and solve linear equations
        self.inc = -matrix([matrix(system.dae.f),
                            matrix(system.dae.g)])

        self.A = sparse([[system.dae.fx, system.dae.gx],
                         [system.dae.fy, system.dae.gy]])

        self.inc = self.solver.solve(self.A, self.inc)

        system.dae.x += np.ravel(np.array(self.inc[:system.dae.n]))
        system.dae.y += np.ravel(np.array(self.inc[system.dae.n:]))

        mis = np.max(np.abs(system.dae.fg))
        self.mis.append(mis)

        system.vars_to_models()

        return mis

    def run(self):
        """
        Full Newton-Raphson method

        Returns
        -------

        """
        system = self.system
        logger.info('-> Power flow calculation with Newton Raphson method:')
        self._initialize()
        if system.dae.m == 0:
            logger.error("Loaded case file contains no element.")
            return False

        t0, _ = elapsed()
        self.niter = 0
        while True:
            mis = self.nr_step()
            logger.info(f'{self.niter}: |F(x)| = {mis:<10g}')

            if mis < self.config.tol:
                self.converged = True
                break
            elif self.niter > self.config.max_iter:
                break
            elif mis > 1e4 * self.mis[0]:
                logger.error('Mismatch increased too fast. Convergence not likely.')
                break
            self.niter += 1

        _, s1 = elapsed(t0)

        if not self.converged:
            if abs(self.mis[-1] - self.mis[-2]) < self.config.tol:
                max_idx = np.argmax(np.abs(system.dae.xy))
                name = system.dae.xy_name[max_idx]
                logger.error('Mismatch is not correctable possibly due to large load-generation imbalance.')
                logger.error(f'Largest mismatch on equation associated with <{name}>')
            else:
                logger.error(f'Power flow failed after {self.niter + 1} iterations for {system.files.case}.')

        else:
            logger.info(f'Converged in {self.niter+1} iterations in {s1}.')
            if self.config.report:
                system.PFlow.write_report()

        return self.converged

    def write_report(self):
        if self.system.files.no_output is False:
            r = Report(self.system)
            r.write()

    def _fg_wrapper(self, xy):
        """
        Wrapper for algebraic equations to be used with Newton-Krylov general solver

        Parameters
        ----------
        xy

        Returns
        -------

        """
        system = self.system
        system.dae.x = xy[:system.dae.n]
        system.dae.y = xy[system.dae.n:]
        system.vars_to_models()
        system.e_clear()

        system.l_update_var()
        system.f_update()
        system.g_update()
        system.l_check_eq()
        system.l_set_eq()
        system.fg_to_dae()
        return system.dae.fg

    def newton_krylov(self, verbose=False):
        """
        Full Newton-Krylov method

        Warnings
        --------
        The result might be wrong if discrete are in use!

        Parameters
        ----------
        verbose

        Returns
        -------

        """
        system = self.system
        system.initialize()
        v0 = system.dae.xy
        try:
            ret = newton_krylov(self._fg_wrapper, v0, verbose=verbose)
        except ValueError as e:
            logger.error('Mismatch is not correctable. Equations may be intrinsically unsolvable.')
            raise e

        return ret
