import Pyro
import logconf
import logchangepublish
import sys
sys.path.append('..')
import util

def init():
    filename = 'flaxlog.conf'

    lcp = logchangepublish.LogConfPub(filename)

    svr = logconf.LogConf(filename)
    util.run_server("logconf", svr, lcp.stop)
    

if __name__ == "__main__":
    init()
