# -*- coding: utf-8 -*-
#  ___________________________________________________________________________
#
#  Pyomo: Python Optimization Modeling Objects
#  Copyright 2017 National Technology and Engineering Solutions of Sandia, LLC
#  Under the terms of Contract DE-NA0003525 with National Technology and
#  Engineering Solutions of Sandia, LLC, the U.S. Government retains certain
#  rights in this software.
#  This software is distributed under the 3-clause BSD License.
#  ___________________________________________________________________________

import os
import time

from six import StringIO, BytesIO

from pyomo.common.log import LoggingIntercept
import pyomo.common.unittest as unittest

import pyomo.common.tee as tee

class TestTeeStream(unittest.TestCase):
    def test_stdout(self):
        a = StringIO()
        b = StringIO()
        with tee.TeeStream(a,b) as t:
            t.STDOUT.write("Hello\n")
        self.assertEqual(a.getvalue(), "Hello\n")
        self.assertEqual(b.getvalue(), "Hello\n")

    def test_err_and_out_are_different(self):
        with tee.TeeStream() as t:
            out = t.STDOUT
            self.assertIs(out, t.STDOUT)
            err = t.STDERR
            self.assertIs(err, t.STDERR)
            self.assertIsNot(out, err)

    @unittest.skipIf(not tee._peek_available,
                     "Requires the _mergedReader, but _peek_available==False")
    def test_merge_out_and_err(self):
        # Test that the STDERR/STDOUT streams are merged correctly
        # (i.e., STDOUT is line buffered and STDERR is not).  This merge
        # logic is only applicable when using the merged reader (i.e.,
        # _peek_available is True)
        a = StringIO()
        b = StringIO()
        with tee.TeeStream(a,b) as t:
            # This is a slightly nondeterministic (on Windows), so a
            # flush() and short pause should help
            t.STDOUT.write("Hello\nWorld")
            t.STDOUT.flush()
            time.sleep(tee._poll_interval*1.1)
            t.STDERR.write("interrupting\ncow")
            t.STDERR.flush()
            time.sleep(tee._poll_interval*2)
        self.assertEqual(a.getvalue(), "Hello\ninterrupting\ncowWorld")
        self.assertEqual(b.getvalue(), "Hello\ninterrupting\ncowWorld")

    def test_merged_out_and_err_without_peek(self):
        a = StringIO()
        b = StringIO()
        try:
            _tmp, tee._peek_available = tee._peek_available, False
            with tee.TeeStream(a,b) as t:
                # Ensure both threads are running
                t.STDOUT
                t.STDERR
                # ERR should come out before OUT, but this is slightly
                # nondeterministic, so a short pause should help
                t.STDERR.write("Hello\n")
                t.STDERR.flush()
                time.sleep(tee._poll_interval*1.1)
                t.STDOUT.write("World\n")
        finally:
            tee._peek_available = _tmp
        self.assertEqual(a.getvalue(), "Hello\nWorld\n")
        self.assertEqual(b.getvalue(), "Hello\nWorld\n")

    def test_binary_tee(self):
        a = BytesIO()
        b = BytesIO()
        with tee.TeeStream(a,b) as t:
            t.open('wb').write(b"Hello\n")
        self.assertEqual(a.getvalue(), b"Hello\n")
        self.assertEqual(b.getvalue(), b"Hello\n")

    def test_decoder_and_buffer_errors(self):
        ref = "Hello, ©"
        bytes_ref = ref.encode()
        log = StringIO()
        with LoggingIntercept(log):
            # Note: we must force the encoding for Windows
            with tee.TeeStream(encoding='utf-8') as t:
                os.write(t.STDOUT.fileno(), bytes_ref[:-1])
        self.assertEqual(
            log.getvalue(),
            "Stream handle closed with a partial line in the output buffer "
            "that was not emitted to the output stream(s):\n"
            "\t'Hello, '\n"
            "Stream handle closed with un-decoded characters in the decoder "
            "buffer that was not emitted to the output stream(s):\n"
            "\tb'\\xc2'\n"
        )

        out = StringIO()
        log = StringIO()
        with LoggingIntercept(log):
            with tee.TeeStream(out) as t:
                out.close()
                t.STDOUT.write("hi\n")
        self.assertEqual(
            log.getvalue(),
            "Output stream closed before all output was written to it. "
            "The following was left in the output buffer:\n\t'hi\\n'\n"
        )

    def test_capture_output(self):
        out = StringIO()
        with tee.capture_output(out) as OUT:
            print('Hello World')
        self.assertEqual(OUT.getvalue(), 'Hello World\n')

    def test_duplicate_capture_output(self):
        out = StringIO()
        capture = tee.capture_output(out)
        capture.setup()
        with self.assertRaisesRegex(RuntimeError, 'Duplicate call to capture_output.setup'):
            capture.setup()

    def test_capture_output_logfile_string(self):
        currdir = os.getcwd()
        logfile = os.path.join(currdir, 'tee_log.log')
        self.assertTrue(isinstance(logfile, str))
        with tee.capture_output(logfile):
            print('HELLO WORLD')
        self.assertEqual('HELLO WORLD\n', open(logfile, 'r').read())
        os.remove(logfile)
