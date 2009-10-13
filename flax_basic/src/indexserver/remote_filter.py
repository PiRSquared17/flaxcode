# Copyright (C) 2007 Lemur Consulting Ltd
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""Support for running filters in a subprocess.

This is intended to protect the main indexing process against badly behaved
filters: filters which take too long can be killed, and filters which crash or
fail in other ways will not break the whole indexing process.

"""
__docformat__ = "restructuredtext en"

import sys
import multiprocessing
import functools
import logging
import logclient

class FilterRunner(logclient.LogClientProcess):

    def __init__(self, filter, i, o):
        self.i = i
        self.o = o
        self.filter = filter
        self.daemon = True
        self.start()
        
    def run(self):
        """Repeatedly receive a filename on `self.i`, run
        self.filter on that file, send output to `o`"""
        remote_log = logging.getLogger("filtering.remote_filter.remote")
        while 1:
            filename = self.i.recv()
            try:
                results = self.filter(filename, log=remote_log)
                # because the filter returns an iterator we won't
                # see all errors until we actually compute the
                # values so this next needs to be in the try
                # block as well.
                if not isinstance(results, Exception):
                    results = list(results)
            except Exception, e:
                remote_log.warning("FilterRunner: %s caught exception: %s" % (str(self), str(e)))
                results = e
            self.o.send(results)

class TimeOutError(Exception):
    "Signal that a remote filter is taking too long to process a file"
    pass

log = logging.getLogger("filtering.remote_filter")

class RemoteFilterRunner(object):
    """
    A filter that runs another filter in a subprocess, with a timeout.
    """

    def __init__(self, filter, timeout=30, restart_limit=1000):
        self.filter = filter
        self.timeout = timeout
        self.server = None
        self.restart_limit = restart_limit
        # count is the number of calls we've processed since the remote process was started.
        self.count = 0

    def __call__(self, file_name):
        self.count += 1
        if self.count > self.restart_limit:
            self.kill_server()
        self.maybe_start_server()
        self.outpipe[0].send(file_name)
        if self.inpipe[1].poll(self.timeout):
            blocks = self.inpipe[1].recv()
            if isinstance(blocks, Exception):
                # if there was an exception raised then we should
                # restart the remote process immediately
                # otherwise the next document may timeout because the
                # remote process is not responding
                log.warning("Killing remote filter - it raised the exception: %s" %
                          str(blocks))
                self.kill_server()
                raise blocks
            for block in blocks:
                yield block
        else:
            log.warning("Killing remote filter due to timeout")
            self.kill_server()
            raise TimeOutError("The server took too long to process file %s, giving up" % file_name)

    def kill_server(self):
        if self.server:
            log.info("killing remote filter process with pid: %d" % self.server.getPid())
            self.server.terminate()
        self.count = 0
        self.server = self.inpipe = self.outpipe = None

    def maybe_start_server(self):
        if not self.server or (self.server and not self.server.is_alive()):
            if self.server:
                self.kill_server()
            self.inpipe = processing.Pipe()
            self.outpipe = processing.Pipe()
            self.server = FilterRunner(self.filter, self.outpipe[1], self.inpipe[0])
            log.info("Starting a remote filter process with pid: %d" % self.server.pid)


# just for expermenting/testing
if __name__ == "__main__":
    def forever_filter(filename):
        while 1:
            pass

    def find_filter(filter_spec):
        mod_name, obj_name = filter_spec.split('.')
        mod = __import__(mod_name)
        obj = getattr(mod, obj_name)
        if not callable(obj):
            raise TypeError("Need a callable")
        else:
            return obj

    filter = RemoteFilterRunner(find_filter(sys.argv[1]))
    while 1:
        filename = raw_input("Filename to filter: ")
        if filename == '0':
            break
        else:
            print "invoking filter"
            blocks = filter(filename)
            print "blocks are:"
            print list(blocks)
