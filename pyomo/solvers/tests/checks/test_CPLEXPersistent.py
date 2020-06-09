#  ___________________________________________________________________________
#
#  Pyomo: Python Optimization Modeling Objects
#  Copyright 2017 National Technology and Engineering Solutions of Sandia, LLC
#  Under the terms of Contract DE-NA0003525 with National Technology and
#  Engineering Solutions of Sandia, LLC, the U.S. Government retains certain
#  rights in this software.
#  This software is distributed under the 3-clause BSD License.
#  ___________________________________________________________________________

import pyutilib.th as unittest

from pyomo.core import ConcreteModel, Var, Objective, Constraint
from pyomo.opt import SolverFactory

try:
    import cplex

    cplexpy_available = True
except ImportError:
    cplexpy_available = False


@unittest.skipIf(not cplexpy_available, "The 'cplex' python bindings are not available")
class TestQuadraticObjective(unittest.TestCase):
    def test_quadratic_objective_is_set(self):
        model = ConcreteModel()
        model.X = Var(bounds=(-2, 2))
        model.Y = Var(bounds=(-2, 2))
        model.O = Objective(expr=model.X ** 2 + model.Y ** 2)
        model.C1 = Constraint(expr=model.Y >= 2 * model.X - 1)
        model.C2 = Constraint(expr=model.Y >= -model.X + 2)
        opt = SolverFactory("cplex_persistent")
        opt.set_instance(model)
        opt.solve()

        self.assertAlmostEqual(model.X.value, 1, places=3)
        self.assertAlmostEqual(model.Y.value, 1, places=3)

        del model.O
        model.O = Objective(expr=model.X ** 2)
        opt.set_objective(model.O)
        opt.solve()
        self.assertAlmostEqual(model.X.value, 0, places=3)
        self.assertAlmostEqual(model.Y.value, 2, places=3)
