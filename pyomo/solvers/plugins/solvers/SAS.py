__all__ = ['SAS']

import logging
import sys
import os

from io import StringIO
from abc import ABC, abstractmethod
from contextlib import redirect_stdout

from pyomo.opt.base import ProblemFormat, ResultsFormat, OptSolver
from pyomo.opt.base.solvers import SolverFactory
from pyomo.common.collections import Bunch
from pyomo.opt.results import (
    SolverResults,
    SolverStatus,
    TerminationCondition,
    SolutionStatus,
    ProblemSense,
)
from pyomo.common.tempfiles import TempfileManager
from pyomo.core.base import Var
from pyomo.core.base.block import _BlockData
from pyomo.core.kernel.block import IBlock


logger = logging.getLogger('pyomo.solvers')


STATUS_TO_SOLVERSTATUS = {
    "OK": SolverStatus.ok,
    "SYNTAX_ERROR": SolverStatus.error,
    "DATA_ERROR": SolverStatus.error,
    "OUT_OF_MEMORY": SolverStatus.aborted,
    "IO_ERROR": SolverStatus.error,
    "ERROR": SolverStatus.error,
}

# This combines all status codes from OPTLP/solvelp and OPTMILP/solvemilp
SOLSTATUS_TO_TERMINATIONCOND = {
    "OPTIMAL": TerminationCondition.optimal,
    "OPTIMAL_AGAP": TerminationCondition.optimal,
    "OPTIMAL_RGAP": TerminationCondition.optimal,
    "OPTIMAL_COND": TerminationCondition.optimal,
    "TARGET": TerminationCondition.optimal,
    "CONDITIONAL_OPTIMAL": TerminationCondition.optimal,
    "FEASIBLE": TerminationCondition.feasible,
    "INFEASIBLE": TerminationCondition.infeasible,
    "UNBOUNDED": TerminationCondition.unbounded,
    "INFEASIBLE_OR_UNBOUNDED": TerminationCondition.infeasibleOrUnbounded,
    "SOLUTION_LIM": TerminationCondition.maxEvaluations,
    "NODE_LIM_SOL": TerminationCondition.maxEvaluations,
    "NODE_LIM_NOSOL": TerminationCondition.maxEvaluations,
    "ITERATION_LIMIT_REACHED": TerminationCondition.maxIterations,
    "TIME_LIM_SOL": TerminationCondition.maxTimeLimit,
    "TIME_LIM_NOSOL": TerminationCondition.maxTimeLimit,
    "TIME_LIMIT_REACHED": TerminationCondition.maxTimeLimit,
    "ABORTED": TerminationCondition.userInterrupt,
    "ABORT_SOL": TerminationCondition.userInterrupt,
    "ABORT_NOSOL": TerminationCondition.userInterrupt,
    "OUTMEM_SOL": TerminationCondition.solverFailure,
    "OUTMEM_NOSOL": TerminationCondition.solverFailure,
    "FAILED": TerminationCondition.solverFailure,
    "FAIL_SOL": TerminationCondition.solverFailure,
    "FAIL_NOSOL": TerminationCondition.solverFailure,
}


SOLSTATUS_TO_MESSAGE = {
    "OPTIMAL": "The solution is optimal.",
    "OPTIMAL_AGAP": "The solution is optimal within the absolute gap specified by the ABSOBJGAP= option.",
    "OPTIMAL_RGAP": "The solution is optimal within the relative gap specified by the RELOBJGAP= option.",
    "OPTIMAL_COND": "The solution is optimal, but some infeasibilities (primal, bound, or integer) exceed tolerances due to scaling or choice of a small INTTOL= value.",
    "TARGET": "The solution is not worse than the target specified by the TARGET= option.",
    "CONDITIONAL_OPTIMAL": "The solution is optimal, but some infeasibilities (primal, dual or bound) exceed tolerances due to scaling or preprocessing.",
    "FEASIBLE": "The problem is feasible. This status is displayed when the IIS=TRUE option is specified and the problem is feasible.",
    "INFEASIBLE": "The problem is infeasible.",
    "UNBOUNDED": "The problem is unbounded.",
    "INFEASIBLE_OR_UNBOUNDED": "The problem is infeasible or unbounded.",
    "SOLUTION_LIM": "The solver reached the maximum number of solutions specified by the MAXSOLS= option.",
    "NODE_LIM_SOL": "The solver reached the maximum number of nodes specified by the MAXNODES= option and found a solution.",
    "NODE_LIM_NOSOL": "The solver reached the maximum number of nodes specified by the MAXNODES= option and did not find a solution.",
    "ITERATION_LIMIT_REACHED": "The maximum allowable number of iterations was reached.",
    "TIME_LIM_SOL": "The solver reached the execution time limit specified by the MAXTIME= option and found a solution.",
    "TIME_LIM_NOSOL": "The solver reached the execution time limit specified by the MAXTIME= option and did not find a solution.",
    "TIME_LIMIT_REACHED": "The solver reached its execution time limit.",
    "ABORTED": "The solver was interrupted externally.",
    "ABORT_SOL": "The solver was stopped by the user but still found a solution.",
    "ABORT_NOSOL": "The solver was stopped by the user and did not find a solution.",
    "OUTMEM_SOL": "The solver ran out of memory but still found a solution.",
    "OUTMEM_NOSOL": "The solver ran out of memory and either did not find a solution or failed to output the solution due to insufficient memory.",
    "FAILED": "The solver failed to converge, possibly due to numerical issues.",
    "FAIL_SOL": "The solver stopped due to errors but still found a solution.",
    "FAIL_NOSOL": "The solver stopped due to errors and did not find a solution.",
}


CAS_OPTION_NAMES = [
    "hostname",
    "port",
    "username",
    "password",
    "session",
    "locale",
    "name",
    "nworkers",
    "authinfo",
    "protocol",
    "path",
    "ssl_ca_list",
    "authcode",
]


@SolverFactory.register('sas', doc='The SAS LP/MIP solver')
class SAS(OptSolver):
    """The SAS optimization solver"""

    def __new__(cls, *args, **kwds):
        mode = kwds.pop('solver_io', None)
        if mode != None:
            return SolverFactory(mode)
        else:
            # Choose solver factory automatically
            # bassed on what can be loaded.
            s = SolverFactory('_sas94', **kwds)
            if not s.available():
                s = SolverFactory('_sascas', **kwds)
            return s


class SASAbc(ABC, OptSolver):
    """Abstract base class for the SAS solver interfaces. Simply to avoid code duplication."""

    def __init__(self, **kwds):
        """Initialize the SAS solver interfaces."""
        kwds['type'] = 'sas'
        super(SASAbc, self).__init__(**kwds)

        #
        # Set up valid problem formats and valid results for each
        # problem format
        #
        self._valid_problem_formats = [ProblemFormat.mps]
        self._valid_result_formats = {ProblemFormat.mps: [ResultsFormat.soln]}

        self._keepfiles = False
        self._capabilities.linear = True
        self._capabilities.integer = True

        super(SASAbc, self).set_problem_format(ProblemFormat.mps)

    def _presolve(self, *args, **kwds):
        """ "Set things up for the actual solve."""
        # create a context in the temporary file manager for
        # this plugin - is "pop"ed in the _postsolve method.
        TempfileManager.push()

        # Get the warmstart flag
        self.warmstart_flag = kwds.pop('warmstart', False)

        # Call parent presolve function
        super(SASAbc, self)._presolve(*args, **kwds)

        # Store the model, too bad this is not done in the base class
        for arg in args:
            if isinstance(arg, (_BlockData, IBlock)):
                # Store the instance
                self._instance = arg
                self._vars = []
                for block in self._instance.block_data_objects(active=True):
                    for vardata in block.component_data_objects(
                        Var, active=True, descend_into=False
                    ):
                        self._vars.append(vardata)
                # Store the symbal map, we need this for example when writing the warmstart file
                if isinstance(self._instance, IBlock):
                    self._smap = getattr(self._instance, "._symbol_maps")[self._smap_id]
                else:
                    self._smap = self._instance.solutions.symbol_map[self._smap_id]

        # Create the primalin data
        if self.warmstart_flag:
            filename = self._warm_start_file_name = TempfileManager.create_tempfile(
                ".sol", text=True
            )
            smap = self._smap
            numWritten = 0
            with open(filename, 'w') as file:
                file.write('_VAR_,_VALUE_\n')
                for var in self._vars:
                    if (var.value is not None) and (id(var) in smap.byObject):
                        name = smap.byObject[id(var)]
                        file.write(
                            "{name},{value}\n".format(name=name, value=var.value)
                        )
                        numWritten += 1
            if numWritten == 0:
                # No solution available, disable warmstart
                self.warmstart_flag = False

    def available(self, exception_flag=False):
        """True if the solver is available"""
        return self._python_api_exists

    def _has_integer_variables(self):
        """True if the problem has integer variables."""
        for vardata in self._vars:
            if vardata.is_binary() or vardata.is_integer():
                return True
        return False

    def _create_results_from_status(self, status, solution_status):
        """Create a results object and set the status code and messages."""
        results = SolverResults()
        results.solver.name = "SAS"
        results.solver.status = STATUS_TO_SOLVERSTATUS[status]
        if results.solver.status == SolverStatus.ok:
            results.solver.termination_condition = SOLSTATUS_TO_TERMINATIONCOND[
                solution_status
            ]
            results.solver.message = (
                results.solver.termination_message
            ) = SOLSTATUS_TO_MESSAGE[solution_status]
            results.solver.status = TerminationCondition.to_solver_status(
                results.solver.termination_condition
            )
        elif results.solver.status == SolverStatus.aborted:
            results.solver.termination_condition = TerminationCondition.userInterrupt
            results.solver.message = (
                results.solver.termination_message
            ) = SOLSTATUS_TO_MESSAGE["ABORTED"]
        else:
            results.solver.termination_condition = TerminationCondition.error
            results.solver.message = (
                results.solver.termination_message
            ) = SOLSTATUS_TO_MESSAGE["FAILED"]
        return results

    @abstractmethod
    def _apply_solver(self):
        """The routine that performs the solve"""
        raise NotImplemented("This is an abstract function and thus not implemented!")

    def _postsolve(self):
        """Clean up at the end, especially the temp files."""
        # Let the base class deal with returning results.
        results = super(SASAbc, self)._postsolve()

        # Finally, clean any temporary files registered with the temp file
        # manager, created populated *directly* by this plugin. does not
        # include, for example, the execution script. but does include
        # the warm-start file.
        TempfileManager.pop(remove=not self._keepfiles)

        return results

    def warm_start_capable(self):
        """True if the solver interface supports MILP warmstarting."""
        return True


@SolverFactory.register('_sas94', doc='SAS 9.4 interface')
class SAS94(SASAbc):
    """
    Solver interface for SAS 9.4 using saspy. See the saspy documentation about
    how to create a connection.
    """

    def __init__(self, **kwds):
        """Initialize the solver interface and see if the saspy package is available."""
        super(SAS94, self).__init__(**kwds)

        try:
            import saspy

            self._sas = saspy
        except ImportError:
            self._python_api_exists = False
        except Exception as e:
            self._python_api_exists = False
            # For other exceptions, raise it so that it does not get lost
            raise e
        else:
            self._python_api_exists = True
            self._sas.logger.setLevel(logger.level)

    def _create_statement_str(self, statement):
        """Helper function to create the strings for the statements of the proc OPTLP/OPTMILP code."""
        stmt = self.options.pop(statement, None)
        if stmt:
            return (
                statement.strip()
                + " "
                + " ".join(option + "=" + str(value) for option, value in stmt.items())
                + ";"
            )
        else:
            return ""

    def _apply_solver(self):
        """ "Prepare the options and run the solver. Then store the data to be returned."""
        logger.debug("Running SAS")

        # Set return code to issue an error if we get interrupted
        self._rc = -1

        # Figure out if the problem has integer variables
        with_opt = self.options.pop("with", None)
        if with_opt == "lp":
            proc = "OPTLP"
        elif with_opt == "milp":
            proc = "OPTMILP"
        else:
            # Check if there are integer variables, this might be slow
            proc = "OPTMILP" if self._has_integer_variables() else "OPTLP"

        # Remove CAS options in case they were specified
        for opt in CAS_OPTION_NAMES:
            self.options.pop(opt, None)

        # Get the rootnode options
        decomp_str = self._create_statement_str("decomp")
        decompmaster_str = self._create_statement_str("decompmaster")
        decompmasterip_str = self._create_statement_str("decompmasterip")
        decompsubprob_str = self._create_statement_str("decompsubprob")
        rootnode_str = self._create_statement_str("rootnode")

        # Handle warmstart
        warmstart_str = ""
        if self.warmstart_flag:
            # Set the warmstart basis option
            if proc != "OPTLP":
                warmstart_str = """
                                proc import datafile='{primalin}'
                                    out=primalin
                                    dbms=csv
                                    replace;
                                    getnames=yes;
                                    run;
                                """.format(
                    primalin=self._warm_start_file_name
                )
                self.options["primalin"] = "primalin"

        # Convert options to string
        opt_str = " ".join(
            option + "=" + str(value) for option, value in self.options.items()
        )

        # Start a SAS session, submit the code and return the results``
        with self._sas.SASsession() as sas:
            # Find the version of 9.4 we are using
            if sas.sasver.startswith("9.04.01M5"):
                # In 9.4M5 we have to create an MPS data set from an MPS file first
                # Earlier versions will not work because the MPS format in incompatible
                res = sas.submit(
                    """
                                {warmstart}
                                %MPS2SASD(MPSFILE="{mpsfile}", OUTDATA=mpsdata, MAXLEN=256, FORMAT=FREE);
                                proc {proc} data=mpsdata {options} primalout=primalout dualout=dualout;
                                {decomp}
                                {decompmaster}
                                {decompmasterip}
                                {decompsubprob}
                                {rootnode}
                                run;
                                """.format(
                        warmstart=warmstart_str,
                        proc=proc,
                        mpsfile=self._problem_files[0],
                        options=opt_str,
                        decomp=decomp_str,
                        decompmaster=decompmaster_str,
                        decompmasterip=decompmasterip_str,
                        decompsubprob=decompsubprob_str,
                        rootnode=rootnode_str,
                    ),
                    results="TEXT",
                )
            else:
                # Since 9.4M6+ optlp/optmilp can read mps files directly
                res = sas.submit(
                    """
                                {warmstart}
                                proc {proc} mpsfile=\"{mpsfile}\" {options} primalout=primalout dualout=dualout;
                                {decomp}
                                {decompmaster}
                                {decompmasterip}
                                {decompsubprob}
                                {rootnode}
                                run;
                                """.format(
                        warmstart=warmstart_str,
                        proc=proc,
                        mpsfile=self._problem_files[0],
                        options=opt_str,
                        decomp=decomp_str,
                        decompmaster=decompmaster_str,
                        decompmasterip=decompmasterip_str,
                        decompsubprob=decompsubprob_str,
                        rootnode=rootnode_str,
                    ),
                    results="TEXT",
                )

            # Store log and ODS output
            self._log = res["LOG"]
            self._lst = res["LST"]
            # Print log if requested by the user
            if self._tee:
                print(self._log)
            if "ERROR 22-322: Syntax error" in self._log:
                raise ValueError(
                    "An option passed to the SAS solver caused a syntax error: {log}".format(
                        log=self._log
                    )
                )
            self._macro = dict(
                (key.strip(), value.strip())
                for key, value in (
                    pair.split("=") for pair in sas.symget("_OR" + proc + "_").split()
                )
            )
            primal_out = sas.sd2df("primalout")
            dual_out = sas.sd2df("dualout")

        # Prepare the solver results
        results = self.results = self._create_results_from_status(
            self._macro.get("STATUS", "ERROR"),
            self._macro.get("SOLUTION_STATUS", "ERROR"),
        )

        if "Objective Sense            Maximization" in self._lst:
            results.problem.sense = ProblemSense.maximize
        else:
            results.problem.sense = ProblemSense.minimize

        # Prepare the solution information
        if results.solver.termination_condition == TerminationCondition.optimal:
            sol = results.solution.add()

            # Store status in solution
            sol.status = SolutionStatus.feasible
            sol.termination_condition = TerminationCondition.optimal

            # Store objective value in solution
            sol.objective['__default_objective__'] = {'Value': self._macro["OBJECTIVE"]}

            if proc == "OPTLP":
                # Convert primal out data set to variable dictionary
                # Use panda functions for efficiency
                primal_out = primal_out[['_VAR_', '_VALUE_', '_STATUS_', '_R_COST_']]
                primal_out = primal_out.set_index('_VAR_', drop=True)
                primal_out = primal_out.rename(
                    {'_VALUE_': 'Value', '_STATUS_': 'Status', '_R_COST_': 'rc'},
                    axis='columns',
                )
                sol.variable = primal_out.to_dict('index')

                # Convert dual out data set to constraint dictionary
                # Use pandas functions for efficiency
                dual_out = dual_out[['_ROW_', '_VALUE_', '_STATUS_', '_ACTIVITY_']]
                dual_out = dual_out.set_index('_ROW_', drop=True)
                dual_out = dual_out.rename(
                    {'_VALUE_': 'dual', '_STATUS_': 'Status', '_ACTIVITY_': 'slack'},
                    axis='columns',
                )
                sol.constraint = dual_out.to_dict('index')
            else:
                # Convert primal out data set to variable dictionary
                # Use pandas functions for efficiency
                primal_out = primal_out[['_VAR_', '_VALUE_']]
                primal_out = primal_out.set_index('_VAR_', drop=True)
                primal_out = primal_out.rename({'_VALUE_': 'Value'}, axis='columns')
                sol.variable = primal_out.to_dict('index')

        self._rc = 0
        return Bunch(rc=self._rc, log=self._log)


class SASLogWriter:
    """Helper class to take the log from stdout and put it also in a StringIO."""

    def __init__(self, tee):
        """Set up the two outputs."""
        self.tee = tee
        self._log = StringIO()
        self.stdout = sys.stdout

    def write(self, message):
        """If the tee options is specified, write to both outputs."""
        if self.tee:
            self.stdout.write(message)
        self._log.write(message)

    def flush(self):
        """Nothing to do, just here for compatibility reasons."""
        # Do nothing since we flush right away
        pass

    def log(self):
        """ "Get the log as a string."""
        return self._log.getvalue()


@SolverFactory.register('_sascas', doc='SAS Viya CAS Server interface')
class SASCAS(SASAbc):
    """
    Solver interface connection to a SAS Viya CAS server using swat.
    See the documentation for the swat package about how to create a connection.
    The swat connection options can be passed as options to the solve function.
    """

    def __init__(self, **kwds):
        """Initialize and try to load the swat package."""
        super(SASCAS, self).__init__(**kwds)

        try:
            import swat

            self._sas = swat
        except ImportError:
            self._python_api_exists = False
        except Exception as e:
            self._python_api_exists = False
            # For other exceptions, raise it so that it does not get lost
            raise e
        else:
            self._python_api_exists = True

    def _apply_solver(self):
        """ "Prepare the options and run the solver. Then store the data to be returned."""
        logger.debug("Running SAS Viya")

        # Set return code to issue an error if we get interrupted
        self._rc = -1

        # Extract CAS connection options
        cas_opts = {}
        for opt in CAS_OPTION_NAMES:
            val = self.options.pop(opt, None)
            if val != None:
                cas_opts[opt] = val

        # Figure out if the problem has integer variables
        with_opt = self.options.pop("with", None)
        if with_opt == "lp":
            action = "solveLp"
        elif with_opt == "milp":
            action = "solveMilp"
        else:
            # Check if there are integer variables, this might be slow
            action = "solveMilp" if self._has_integer_variables() else "solveLp"

        # Connect to CAS server
        with redirect_stdout(SASLogWriter(self._tee)) as self._log_writer:
            s = self._sas.CAS(**cas_opts)
            try:
                # Load the optimization action set
                s.loadactionset('optimization')

                # Upload mps file to CAS
                if os.stat(self._problem_files[0]).st_size >= 2 * 1024**3:
                    # For large files, use convertMPS, first create file for upload
                    mpsWithIdFileName = TempfileManager.create_tempfile(
                        ".mps.csv", text=True
                    )
                    with open(mpsWithIdFileName, 'w') as mpsWithId:
                        mpsWithId.write('_ID_\tText\n')
                        with open(self._problem_files[0], 'r') as f:
                            id = 0
                            for line in f:
                                id += 1
                                mpsWithId.write(str(id) + '\t' + line.rstrip() + '\n')

                    # Upload .mps.csv file
                    s.upload_file(
                        mpsWithIdFileName,
                        casout={"name": "mpscsv", "replace": True},
                        importoptions={"filetype": "CSV", "delimiter": "\t"},
                    )

                    # Convert .mps.csv file to .mps
                    s.optimization.convertMps(
                        data="mpscsv",
                        casOut={"name": "mpsdata", "replace": True},
                        format="FREE",
                    )
                else:
                    # For small files, use loadMPS
                    with open(self._problem_files[0], 'r') as mps_file:
                        s.optimization.loadMps(
                            mpsFileString=mps_file.read(),
                            casout={"name": "mpsdata", "replace": True},
                            format="FREE",
                        )

                if self.warmstart_flag:
                    # Upload warmstart file to CAS
                    s.upload_file(
                        self._warm_start_file_name,
                        casout={"name": "primalin", "replace": True},
                        importoptions={"filetype": "CSV"},
                    )
                    self.options["primalin"] = "primalin"

                # Solve the problem in CAS
                if action == "solveMilp":
                    r = s.optimization.solveMilp(
                        data={"name": "mpsdata"},
                        primalOut={"name": "primalout", "replace": True},
                        **self.options
                    )
                else:
                    r = s.optimization.solveLp(
                        data={"name": "mpsdata"},
                        primalOut={"name": "primalout", "replace": True},
                        dualOut={"name": "dualout", "replace": True},
                        **self.options
                    )

                # Prepare the solver results
                if r:
                    # Get back the primal and dual solution data sets
                    results = self.results = self._create_results_from_status(
                        r.get("status", "ERROR"), r.get("solutionStatus", "ERROR")
                    )

                    if r.ProblemSummary["cValue1"][1] == "Maximization":
                        results.problem.sense = ProblemSense.maximize
                    else:
                        results.problem.sense = ProblemSense.minimize

                    # Prepare the solution information
                    if (
                        results.solver.termination_condition
                        == TerminationCondition.optimal
                    ):
                        sol = results.solution.add()

                        # Store status in solution
                        sol.status = SolutionStatus.feasible
                        sol.termination_condition = TerminationCondition.optimal

                        # Store objective value in solution
                        sol.objective['__default_objective__'] = {
                            'Value': r["objective"]
                        }

                        if action == "solveMilp":
                            primal_out = s.CASTable(name="primalout")
                            # Use pandas functions for efficiency
                            primal_out = primal_out[['_VAR_', '_VALUE_']]
                            sol.variable = {}
                            for row in primal_out.itertuples(index=False):
                                sol.variable[row[0]] = {'Value': row[1]}
                        else:
                            # Convert primal out data set to variable dictionary
                            # Use panda functions for efficiency
                            primal_out = s.CASTable(name="primalout")
                            primal_out = primal_out[
                                ['_VAR_', '_VALUE_', '_STATUS_', '_R_COST_']
                            ]
                            sol.variable = {}
                            for row in primal_out.itertuples(index=False):
                                sol.variable[row[0]] = {
                                    'Value': row[1],
                                    'Status': row[2],
                                    'rc': row[3],
                                }

                            # Convert dual out data set to constraint dictionary
                            # Use pandas functions for efficiency
                            dual_out = s.CASTable(name="dualout")
                            dual_out = dual_out[
                                ['_ROW_', '_VALUE_', '_STATUS_', '_ACTIVITY_']
                            ]
                            sol.constraint = {}
                            for row in dual_out.itertuples(index=False):
                                sol.constraint[row[0]] = {
                                    'dual': row[1],
                                    'Status': row[2],
                                    'slack': row[3],
                                }
                else:
                    results = self.results = SolverResults()
                    results.solver.name = "SAS"
                    results.solver.status = SolverStatus.error
                    raise ValueError(
                        "An option passed to the SAS solver caused a syntax error."
                    )

            finally:
                s.close()

        self._log = self._log_writer.log()
        if self._tee:
            print(self._log)
        self._rc = 0
        return Bunch(rc=self._rc, log=self._log)
