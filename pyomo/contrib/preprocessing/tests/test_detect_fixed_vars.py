#  ___________________________________________________________________________
#
#  Pyomo: Python Optimization Modeling Objects
#  Copyright (c) 2008-2025
#  National Technology and Engineering Solutions of Sandia, LLC
#  Under the terms of Contract DE-NA0003525 with National Technology and
#  Engineering Solutions of Sandia, LLC, the U.S. Government retains certain
#  rights in this software.
#  This software is distributed under the 3-clause BSD License.
#  ___________________________________________________________________________

"""Tests detection of fixed variables."""

import pyomo.common.unittest as unittest
from pyomo.environ import ConcreteModel, TransformationFactory, Var, value


class TestDetectFixedVars(unittest.TestCase):
    """Tests detection of fixed variables."""

    def test_fixed_var_propagate(self):
        """Test for detecting de-facto fixed variables and fixing them."""
        m = ConcreteModel()
        m.v1 = Var(initialize=1)
        m.v2 = Var(initialize=2)
        m.v1.setub(2)
        m.v1.setlb(2)

        TransformationFactory('contrib.detect_fixed_vars').apply_to(m)
        self.assertTrue(m.v1.fixed)
        self.assertFalse(m.v2.fixed)

    def test_fixed_var_revert(self):
        """Test for reversion of fixed variables."""
        m = ConcreteModel()
        m.v1 = Var(initialize=1)
        m.v2 = Var(initialize=2)
        m.v1.setub(2)
        m.v1.setlb(2)

        xfrm = TransformationFactory('contrib.detect_fixed_vars')
        xfrm.apply_to(m, tmp=True)
        self.assertTrue(m.v1.fixed)
        self.assertFalse(m.v2.fixed)
        xfrm.revert(m)
        self.assertFalse(m.v1.fixed)
        self.assertEqual(value(m.v1), 1)


if __name__ == '__main__':
    unittest.main()
