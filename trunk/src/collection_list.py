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
"""Manage the list of all collections known to flax.

"""
__docformat__ = "restructuredtext en"

import logging
import doc_collection
import search

log = logging.getLogger("collection")

class CollectionList(object):
    """A list of collections.

    """

    def __init__(self, db_dir):
        self._collections = {}
        self.db_dir = db_dir
        self._formats = ["txt", "html", "doc"]

    def new_collection(self, name, **kwargs):
        if type(name) == str and not self._collections.has_key(name):
            log.info("Creating new collection: %s" % name)
            col = doc_collection.DocCollection(name, self.db_dir)
            self._collections[name] = col
            col.update(**kwargs)
            return col
        else:
            log.error("Failed attempt to create collection: %s" % name)

    def remove_collection(self, name):
        if type(name) == str and self._collections.has_key(name):
            log.info("Deleting collection %s" % name)
            del self._collections[name]
        else:
            log.error("Failed attempt to delete collection %s" % name)

    def search(self, query=None, col_id=None, doc_id=None, cols=None, tophit=0, maxhits=10):
        """Perform a search.
        
        Either query or (col_id and doc_id) should be passed, the latter
        idicates a similarity search for the document identified by col_id and
        doc_id.
        
        """
        if cols is None:
            cols = self._collections.keys()
        dbs_to_search = [self._collections[col].dbname() for col in cols]
        if doc_id and col_id:
            return search.sim_query(self._collections, dbs_to_search, col_id, doc_id, tophit, maxhits)
        elif query:
            return search.search(dbs_to_search, query, tophit, maxhits)
        else:
            return []

    @property
    def collection_names (self):
        return self._collections.keys()

    def __getitem__(self, key):
        return self._collections.__getitem__(key)

    def __setitem__(self, key, val):
        self._collections.__setitem__(key, val)

    def __contains__(self, key):
        return self._collections.__contains__(key)

    def __iter__(self):
        return self._collections.__iter__()

    def iterkeys(self):
        return self._collections.iterkeys()

    def iteritems(self):
        return self._collections.iteritems()

    def itervalues(self):
        return self._collections.itervalues()
