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
"""Start flax as Windows Service.

"""
__docformat__ = "restructuredtext en"

import regutil
import servicemanager
import win32api
import win32con
import win32service
import win32serviceutil
import win32event
import win32evtlogutil

import os
import sys

# We need to do a lot of messing about with paths, as when running as a service
# it's not clear what our actual path is. The path to the executable is set in
# the Registry by the installation script.

REGKEY_BASE = "SOFTWARE\\Lemur Consulting Ltd\\Flax\\"

# Get the path to the installed application from the Registry 
try:
    runtimepath = win32api.RegQueryValue(regutil.GetRootKey(),
                                        REGKEY_BASE + "RuntimePath")
except:
    runtimepath = r"c:\Program Files\Flax"
# We need to do the following so we can load any further modules
sys.path.insert(0,runtimepath)

# Get the path to the data folder from the Registry
try:
    datapath = win32api.RegQueryValue(regutil.GetRootKey(),
                                      REGKEY_BASE + "DataPath")
except:
    datapath = r"c:\Program Files\Flax"

# We have to set sys.executable to a normal Python interpreter.  It won't point
# to one because we will have been run by PythonService.exe (and sys.executable
# will be the path to that executable).  However, the "processing" extension
# module uses sys.executable to emulate a fork, and needs it to be the correct
# python interpreter.  We'll try to read it from a registry entry, and try
# making it up otherwise.
try:
    try:
        exepath = win32api.RegQueryValue(regutil.GetRootKey(),
                                         REGKEY_BASE + "PythonExePath")
    except:
        exepath = win32api.RegQueryValue(regutil.GetRootKey(),
                                         regutil.BuildDefaultPythonKey())
    # If exepath points to a directory, add the name of the default python
    # interpreter to get a path to a file.
    if os.path.isdir(exepath):
        exepath = os.path.join(exepath, 'Python.exe')
    if not os.path.exists(exepath):
        raise ValueError("Python installation not complete (interpreter not "
                         "found at %s)" % exepath)
except:
    # No useful registry entries; try looking for Python.exe in the parents of
    # the current value of sys.executable.
    exedir = sys.executable
    while True:
        newdir = os.path.dirname(exedir)
        if newdir == exedir:
            break
        exedir = newdir
        exepath = os.path.join(exedir, 'Python.exe')
        if os.path.exists(exepath):
            break
    if not os.path.exists(exepath):
        raise ValueError("Cannot find python executable (looked in parent "
                         "directories of %s)" % os.path.dirname(sys.executable))
sys.executable = exepath

# TODO - fix up any other paths

# Prevent buffer overflows by redirecting stdout & stderr to a file
stdoutpath = os.path.join(datapath, 'flax_stdout.log')
stderrpath = os.path.join(datapath, 'flax_stderr.log')

# The "processing" module attempts to set a signal handler (by calling
# signal.signal).  However, this is not possible when we're installing as a
# service, since signal.signal only works in the main thread, and we are run in
# a subthread by the service handling code.  Therefore, we install a dummy
# signal handler to avoid an exception being thrown.
# Signals are pretty unused on windows anyway, so hopefully this won't cause a
# problem.  If it does cause a problem, we'll have to work out a way to set a
# signal handler (perhaps, by running the whole of Flax in a sub-process).
def _dummy_signal(*args, **kwargs):
    pass
import signal
signal.signal = _dummy_signal

# Pacify processing 0.35.
# If we don't set argv[0] to '', processing 0.35 will raise an error due to an
# attempt to access sys.modules['__main__'], which doesn't exist when running
# as a service.
# FIXME - check that the above comment is a correct description of what goes
# wrong with 0.35 if the following two lines aren't used.
if __name__ != '__main__':
    sys.argv[0] = ''

# Import start module, which implements starting and stopping Flax.
import start
import processing

class FlaxService(win32serviceutil.ServiceFramework):

    _svc_name_ = "FlaxService"
    _svc_display_name_ = "Flax Service"
    _svc_deps_ = ["EventLog"]

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        servicemanager.SetEventSourceName(self._svc_display_name_)
        
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)

        # Set options according to our configuration, and create the class
        # which manages starting and stopping the flax threads and processes.
        self._options = start.StartupOptions(main_dir = runtimepath,
                                             dbs_dir = datapath)
        self._flax_main = start.FlaxMain(self._options)
        
    def logmsg(self, event):
        """Log a service event using servicemanager.LogMsg

        """
        try:
            servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                                  event,
                                  (self._svc_name_,
                                   " (%s)" % self._svc_display_name_))
        except win32api.error, details:
            # Failed to write a log entry - most likely problem is
            # that the event log is full.  We don't want this to kill us.
            try:
                print "FAILED to write INFO event", event, ":", details
            except IOError:
                pass        

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

        # This call to stop() may take some time, but this shouldn't cause
        # windows to complain because the SvcDoRun thread will have awoken and
        # be sending SERVICE_STOP_PENDING messages every 4 seconds until join()
        # returns True.
        self._flax_main.stop()

    def SvcDoRun(self):
        # Write a 'started' event to the event log...
        self.logmsg(servicemanager.PYS_SERVICE_STARTED)

        # Redirect stdout and stderr to avoid buffer overflows and to allow
        # debugging while acting as a service
        sys.stderr = open(stderrpath, 'w')
        sys.stdout = open(stdoutpath, 'w')
        
        # Start flax, non-blocking.
        self._flax_main.start(blocking = False)
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)

        # Wait for message telling us that we're stopping.
        win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)

        # Wait for the service to stop (and reassure windows that we're still
        # trying to stop).
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, 5000)
        while not self._flax_main.join(4):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, 5000)

        # Perform cleanup.
        # Call sys.exitfunc() directly as a workaround: this is meant to be
        # called when python exits, but doesn't seem to be for some reason.
        # FIXME - work out why this doesn't happen automatically.
        # FIXME - should we be calling processing.process._exit_func() instead?
        # FIXME - Or get a public interface to this added to the processing
        # module, and use it instead of calling this internal interface.
        #sys.exitfunc()
        processing.process._exit_func()
        # Write a 'stopped' event to the event log...
        self.logmsg(servicemanager.PYS_SERVICE_STOPPED)
        
def ctrlHandler(ctrlType):
    """A windows control message handler.

    This is needed to prevent the service exiting when the user who started it
    exits.

    FIXME - we should probably handle ctrlType = CTRL_SHUTDOWN_EVENT
    differently.

    """
    return True

if __name__ == '__main__':
    win32api.SetConsoleCtrlHandler(ctrlHandler, True)
    win32serviceutil.HandleCommandLine(FlaxService)
