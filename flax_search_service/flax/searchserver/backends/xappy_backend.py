# Copyright (c) 2009 Lemur Consulting Ltd
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
r"""Backend based on xappy.

"""
__docformat__ = "restructuredtext en"

# Local modules
from base_backend import BaseBackend, BaseDbReader, BaseDbWriter
from flax.searchserver import schema, utils

# Global modules
import xapian
import xappy
import Queue

# The metadata key used to hold schemas.
SCHEMA_KEY = "_flax_schema"

class Backend(BaseBackend):
    """The xappy backend for flax search server.

    Settings for this backend can be specified in the settings.py module by
    adding a 'xappy' entry to the 'backend_settings' dict.  They will be
    available in self.settings.

    """            
    def version_info(self):
        """Get version information about the backend.

        """
        return 'xappy %s, xapian %s' % (
            xappy.__version__,
            xapian.version_string(),
        )

    def create_db(self, db_path):
        """Create a xappy database at db_path.

        """
        db = xappy.IndexerConnection(db_path)
        db.close()

    def delete_db(self, db_path):
        """Delete a xappy database at db_path.

        """
        pass

    def get_db_reader(self, base_uri, db_path):
        """Get a DbReader object for a database at a specific path.

        We allow multiple DbReaders so that searches can be concurrent.
        
        """
        return DbReader(base_uri, db_path)

    def get_db_writer(self, base_uri, db_path):
        """Get a DbWriter object for a database at a specific path.

        There should only be one of these in existence at any one time (per DB).
        
        """
        return DbWriter(base_uri, db_path)
        

class DbReader(BaseDbReader):
    def __init__(self, base_uri, db_path):
        """Create a database object for the specified path.

        """
        BaseDbReader.__init__(self)
        self.base_uri = base_uri
        self.db_path = db_path
        self._sconn = None          # search connection

    def __del__(self):
        """Close any open database connection.

        """
        if self._sconn is not None:
            self._sconn.close()

    @property
    def searchconn(self):
        """Open a search connection if there isn't one already open.

        """
        if self._sconn is None:
            self._sconn = xappy.SearchConnection(self.db_path)
        return self._sconn
        
    def get_info(self):
        """Get information about the database.

        """
        return {
            'backend': 'xappy',
            'doccount': self.searchconn.get_doccount(),
        }

    def get_schema(self):
        """Get the schema for the database.

        """
        data = self.searchconn.get_metadata(SCHEMA_KEY)
        if len(data) > 0:
            return schema.Schema(utils.json.loads(data))
        else:
            return schema.Schema()

    def get_document(self, doc_id):
        """Get a document from the database.

        """
        return self.searchconn.get_document(doc_id).data
            
    def search_simple(self, query, start_rank, end_rank):
        """Perform a simple search, for a user-specified query string.

        Returns a set of search results.

        """
        queryobj = self.searchconn.query_parse(query)
        return self._search(queryobj, start_rank, end_rank)
        
    def search_structured(self, query_all, query_any, query_none, query_phrase, 
                          filters, start_rank, end_rank):

        """Perform a structured search.
        
        FIXME: document            
        
        """

        def combine_queries(q1, q2):
            return q1 & q2 if q1 else q2
                
        query = None
        if query_all:
            query = self.searchconn.query_parse(query_all, default_op=self.searchconn.OP_AND)

        if query_any:
            query = combine_queries(query, self.searchconn.query_parse(
                query_any, default_op=self.searchconn.OP_OR))

        if query_none:
            if query is None:
                query = self.searchconn.query_all()            
            query = query.and_not(self.searchconn.query_parse(query_none, 
                                  default_op=self.searchconn.OP_OR))
        
        if query_phrase:   # FIXME - support in Xappy?
            raise NotImplementedError

        # we want filters to be ORd within fields, ANDed between fields
        if filters:
            filterdict = {}
            for f in filters:
                p = f.index(':')
                filterdict.setdefault(f[:p], []).append(
                    self.searchconn.query_field(f[:p], f[p+1:]))
            
            filterquery = self.searchconn.query_composite(self.searchconn.OP_AND, 
                [self.searchconn.query_composite(self.searchconn.OP_OR, x)
                for x in filterdict.itervalues()])
                
            query = query.filter(filterquery) if query else filterquery

        return self._search(query, start_rank, end_rank)
    
    def _search(self, queryobj, start_rank, end_rank):
        
        print '-- queryobj:', queryobj
        
        if queryobj is None:
            return {
                'matches_estimated': 0,
                'matches_lower_bound': 0,
                'matches_upper_bound': 0,
                'matches_human_readable_estimate': '',
                'estimate_is_exact': True,
                'more_matches': False,
                'start_rank': 0,
                'end_rank': 0,
                'results': [],
            }
            
        results = queryobj.search(start_rank, end_rank)        
        print '-- matches_estimated:', results.matches_estimated
        
        resultlist = [
            {
                "docid": result.id,
                "rank": result.rank,
                "db": self.base_uri,
                "weight": result.weight,
                "data": result.data,
            } for result in results
        ]
        
        return {
            'matches_estimated': results.matches_estimated,
            'matches_lower_bound': results.matches_lower_bound,
            'matches_upper_bound': results.matches_upper_bound,
            'matches_human_readable_estimate': results.matches_human_readable_estimate,
            'estimate_is_exact': results.estimate_is_exact,
            'more_matches': results.more_matches,
            'start_rank': results.startrank,
            'end_rank': results.endrank,
            'results': resultlist,
        }
        

class DbWriter(BaseDbWriter):
    def __init__(self, base_uri, db_path):
        """Create a database object for the specified path.

        """
        
        BaseDbWriter.__init__(self)
        self.base_uri = base_uri
        self.db_path = db_path
        self.queue = Queue.Queue(10000)
        self.iconn = xappy.IndexerConnection(self.db_path)

    def close(self):
        """Close any open database connections.

        """
        raise NotImplementedError

    def set_schema(self, schema):
        """Set the schema for this database.
        
        This will be done asynchronously in the write thread.
        
        """
        self.queue.put(DbWriter.SetSchemaAction(self, schema))

    def add_document(self, doc, docid=None):
        """Add a document to the database.
        
        This will be done asynchronously in the write thread.

        """
        self.queue.put(DbWriter.AddDocumentAction(self, doc, docid))

    def commit_changes(self):
         """Commit changes to the database.
         
         This will be done asynchronously in the write thread.
         
         """
         self.queue.put(DbWriter.CommitAction(self))
        

    class SetSchemaAction(object):
        """Action to set the schema for a Xappy database.
        
        """
        def __init__(self, db_writer, schema):
            self.db_writer = db_writer
            self.schema = schema
    
        def perform(self):
            self.db_writer.iconn.set_metadata(SCHEMA_KEY, utils.json.dumps(self.schema.as_dict()))
            self.schema.set_xappy_field_actions(self.db_writer.iconn)
        
        def __str__(self):
            return 'SetSchemaAction(%s)' % self.db_writer.db_path
    
    
    class AddDocumentAction(object):
        """Action to add a document to a Xappy database.
        
        """
        def __init__(self, db_writer, doc, docid=None):
            self.db_writer = db_writer
            self.doc = doc
            self.docid = docid
            
        def perform(self):
            updoc = xappy.UnprocessedDocument()
            for k, v in self.doc.iteritems():
                if isinstance(v, list):
                    for v2 in v:
                        updoc.append(k, v2)
                else:
                    updoc.append(k, v)
            
            if self.docid is not None:
                updoc.id = self.docid
                self.db_writer.iconn.replace(updoc)            
            else:
                self.db_writer.iconn.add(updoc)
    
        def __str__(self):
            return 'AddDocumentAction(%s)' % self.db_writer.db_path
    
    class CommitAction(object):
        """Action to flush changes to the database so they can be searched.
        
        """
        def __init__(self, db_writer):
            self.db_writer = db_writer
    
        def perform(self):
            self.db_writer.iconn.flush()

        def __str__(self):
            return 'CommitAction(%s)' % self.db_writer.db_path
