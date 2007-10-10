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
"""File specification - how to define a set of files.

"""
__docformat__ = "restructuredtext en"

import os
import stat
import datetime
import fnmatch
import util

class FileSpec(object):
    """Filespec: define a set of files and then do things with them.

    Paths - a set of absolute paths. If a path is a directory then in
    stands for all the files (recursively) contained within it.

    formats - filetypes to be included.

    oldest:timedelta - a duration, when an operation is performed
    anything modified more than this amount of time ago is excluded.

    """

    strptime_format = "%d/%m/%y %H:%M:%S"

    def update(self, paths=None,  oldest=None, formats = [], **kwargs):
        if paths == None:
            paths = []
        self.paths = [paths] if isinstance(paths, str) else paths
        self.oldest = oldest
        self.formats = [formats] if isinstance(formats, str) else formats

    def files(self):
        """Returns an iterator over the files defined by this FileSpec."""
        for p in self.paths:
            for root, dirs, files in os.walk(p):
                # Perhaps we want to warn here if any dirs are
                # symlinks. os.walk will not traverse them. Don't do
                # anything right now because we're targetting windows
                # initially and therefore won't be hitting symlinks.
                # Note that a symlink to a file will be included
                # (assuming the file passes the other criteria for
                # inclusion.)
                for f in files:
                    fname = os.path.join(root, f)
                    if self.included(fname):
                        yield fname

    def _get_oldest(self):
        return self._oldest

    def _set_oldest(self, val):
        self._oldest = self._process_timedelta(val)

    oldest = property(fget = _get_oldest, fset = _set_oldest)

    def _process_timedelta(self, val):
        if not val:
            return None
        elif isinstance(val, str):
            # possibly we need to catch exceptions here - need to see
            # what gets raised
            return util.parse_timedelta(val)
        elif isinstance(val, datetime.timedelta):
            return val
        else:
            raise ValueError("Value must be None, a string or a datetime.timedelta")

    def included(self, f):
        """ is the file name by f included in this spec? """

        # is this file one of the permitted formats?
        if not any ((fnmatch.fnmatch(f, '*.'+e) for e in self.formats)):
            return False

        # format is ok, are we with the permitted range of dates.
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(f))

        age = datetime.datetime.now() - mtime
        return self.oldest < age if self.oldest else True
