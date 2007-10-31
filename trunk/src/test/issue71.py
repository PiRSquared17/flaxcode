import copy
import sys
import os
sys.path.append('..')
sys.path.append('../indexserver')


# tests/experiments related to issue 71
# http://code.google.com/p/flaxcode/issues/detail?id=71

# try running this and see what happens to memory use.  If this keeps
# eating memory then the problem is probably not specifically to do
# with the ifilter_filter.

import remote_filter
def filter_forever():

    s = ' '.join((str(x) for x in xrange(100000)))
    def filter(filename):
        for x in xrange(50):
            yield ('content', copy.copy(s))

    rf = remote_filter.RemoteFilterRunner(filter)
        
    while 1:
        stuff = list(rf('dummy'))
        if not rf.server:
            print "no server"
            break

# this is similar to the above, but is actually using the
# ifilter_filter on a pdf.  obviously it will only run on windows.
# Interestingly it will run for quite a while. Memory does seem to
# creep up slowly, suggesting that there is a small problem somewhere.
# Sometimes (after hours of running) An com error 0x80004005 gets
# raised, which is an "unspecified error" accoding to
# http://msdn2.microsoft.com/en-us/library/aa705941.aspx.  The
# interesting thing about that is that it's not data dependent,
# because we're using the same file each time.
import w32com_ifilter
def repeat_file_filter():    
    fname = os.path.join(os.path.realpath('sampledocs'), 'ukpga_20060041_en.pdf')
    while 1:
        stuff = list(w32com_ifilter.remote_ifilter(fname))
        if not w32com_ifilter.remote_ifilter.server:
            print "no server"
            break


# This one is similar to the above, but runs the filter in-process.
# Memory use also creeps up with this, suggesting that the problem is
# specifically to do with the ifilter_filter, and not the interprocess
# stuff.

def in_process_repeat_file_filter():
    fname = os.path.join(os.path.realpath('sampledocs'), 'ukpga_20060041_en.pdf')
    while 1:
        stuff = list(w32com_ifilter.ifilter_filter(fname))


# This just repeatedly binds the IFilter, without actually using it.
# Interestingly memory use goes up much faster with this than the
# examples above.
def repeat_bind_ifilter():
    fname = os.path.join(os.path.realpath('sampledocs'), 'ukpga_20060041_en.pdf')
    while 1:
        f, s = w32com_ifilter.get_ifilter_for_file(fname)

# A pdf isn't structured storage, so this is a simplified version of
# the above, and indeed shows the same growing memory use.
def repeat_bind_ifilter2():
    fname = os.path.join(os.path.realpath('sampledocs'), 'ukpga_20060041_en.pdf')
    while 1:
        f = w32com_ifilter.load_ifilter(fname)

# Perhaps it's a problem specifically with the pdf filtering thing?
# This is the same as the above but we use an html file.  Memory use
# for this does not seem to increase - maybe it's all Adobe's fault?
# :/
def repeat_bind_ifilter3():
    fname = os.path.join(os.path.realpath('sampledocs'), 'Ukpga_19880002_en_1.htm')
    while 1:
        f = w32com_ifilter.load_ifilter(fname)

