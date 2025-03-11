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

#
# Only run the tests in this package if the pyomo.contrib.example package
# has been successfully imported.
#

import pyomo.contrib.example
import pyomo.common.unittest as unittest


class Tests(unittest.TestCase):
    def test1(self):
        pass


if __name__ == "__main__":
    unittest.main()
