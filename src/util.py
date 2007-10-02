"""
A variety of utilities for Flax.
"""

import os
import sys
import datetime
import threading
import re

def setup_sys_path():
    "modify sys.path to in order to find libraries"
    sys.path =  [os.path.normpath(os.path.join(__file__, '..', '..','libs', 'xappy'))]+sys.path

def setup_psyco():
    "If psyco is available ensure that it is used"
    try:
        import psyco
        psyco.background()
    except ImportError:
        pass

td_re = re.compile(r'(?P<days>\d{0,3})\s+(?P<hours>\d{0,2})\s+(?P<minutes>\d{0,2})')

def parse_timedelta(s):
    'make a timedelta from a string of the format "days hours minutes"'
    m=td_re.match(s)
    if m:
        return datetime.timedelta(days = int(m.group('days')),
                                  hours = int(m.group('hours')),
                                  minutes = int(m.group('minutes')))
    else:
        return None

def render_timedelta(td):
    'render a timedelta in the same format as that expected by parse_timedelta'
    return "%s %s %s" % (td.days, td.seconds % 3600, td.seconds % 60)


def gen_until_exception(it, ex, test):
    """ Make an iterator that yields the elements of it, and stops if
        exception ex matching predicate test is raised other
        exceptions are passed through
    """
    try:
        for x in it:
            yield x
    except ex, e:
        if test(e):
            raise StopIteration
        else:
            raise

def join_all_threads():
    for thread in threading.enumerate():
        if thread != threading.currentThread():
            thread.join()


import Pyro.core
import Pyro.naming

def run_server(name, server, shutdown_actions=None):
    remoting_server = Pyro.core.ObjBase()
    remoting_server.delegateTo(server)
    Pyro.core.initServer()
    daemon = Pyro.core.Daemon()
    ns = Pyro.naming.NameServerLocator().getNS()
    daemon.useNameServer(ns)
    try:
        ns.unregister(name)
    except Pyro.errors.NamingError:
        pass

    daemon.connect(remoting_server, name)

    try:
        while 1:
            daemon.handleRequests(3)
    except KeyboardInterrupt:
        print "Finishing"
        if shutdown_actions:
            shutdown_actions()
    finally:
        daemon.shutdown(True)
