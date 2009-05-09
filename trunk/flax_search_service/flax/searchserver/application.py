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
r"""WSGI application for FlaxSearchServer.

"""
__docformat__ = "restructuredtext en"

# Local modules
import backends
import controller
import schema
import utils

# Global modules
import os
import wsgiwapi
import xapian

# Parameter descriptions
dbname_param = ('dbname', '^[A-Za-z0-9._%]+$')
fieldname_param = ('fieldname', '^[A-Za-z0-9._%]+$')
docid_param = ('docid', '^[A-Za-z0-9._%]+$')

class SearchServer(object):
    """An instance of the search server.

    There will generally only be one of these per process.  An instance of the
    server will be wrapped in an WSGIWAPI application.

    """

    def __init__(self, settings):
        """Initialise an instance of the search server.

        `settings` should be a dictionary containing the following items:

         - `data_path`: The path of a directory under which all the databases
           and other data will be placed.
         - `server_bind_address`: The address for the server to bind to.  This
           should by a tuple containing two items - first the address to bind
           to (for example, '0.0.0.0' to bind to any IPv4 address), second
           the port number to bind to.

        `settings` may also contain the following optional items:

         - `backend_settings`: A dictionary of backend-specific settings, keyed
           by backend name.  These will be passed directly to the backend in
           use.

        For example:

        >>> s = SearchServer({'data_path': '/tmp/flax/',
        ...                   'server_bind_address': ('0.0.0.0', 8080),
        ...                  })

        The directory pointed to by data_path will be created if it doesn't
        already exist.

        """
        self.data_path = os.path.realpath(settings['data_path'])
        if not os.path.exists(self.data_path):
            os.makedirs(self.data_path)

        self.dbs_path = os.path.join(self.data_path, 'ss_dbs')
        if not os.path.exists(self.dbs_path):
            os.makedirs(self.dbs_path)

        # Open a writer on the settings database, which ensures that only one
        # search server is running at a time.  Also used to hold settings which
        # are set at runtime.
        self.settings_path = os.path.join(self.data_path, 'ss_settings')
        self.settings_db = xapian.WritableDatabase(self.settings_path,
                                                   xapian.DB_CREATE_OR_OPEN)

        self.backend_settings = settings.get('backend_settings', {})
        backends.check_backend_settings(self.backend_settings)

        self.controller = controller.Controller(settings['base_uri'],
                                                self.dbs_path,
                                                self.backend_settings,
                                                self.settings_db,
                                               )

    @wsgiwapi.allow_GETHEAD
    @wsgiwapi.noparams
    @wsgiwapi.jsonreturning
    def flax_status(self, request):
        """Get the status of the flax server.

        """
        import version
        backend_list = backends.get_backends()
        backend_versions = dict((name, backend.version_info())
                                for name, backend in backend_list)
        return {
            'versions': {
                'SERVER': version.SERVER_VERSION,
                'PROTOCOL': version.PROTOCOL_VERSION,
            },
            'backends': backend_versions,
        }

    #### DB methods ####

    @wsgiwapi.allow_GETHEAD
    @wsgiwapi.noparams
    @wsgiwapi.jsonreturning
    def dbnames(self, request):
        """Get a list of available databases.

        """
        return self.controller.db_names()

    @wsgiwapi.allow_GETHEAD
    @wsgiwapi.pathinfo(dbname_param)
    @wsgiwapi.noparams
    @wsgiwapi.jsonreturning
    def db_info(self, request):
        """Get information about the database.

        """
        dbname = request.pathinfo['dbname']
        db = self.controller.get_db_reader(dbname)
        return db.get_info()

    @wsgiwapi.allow_POST
    @wsgiwapi.pathinfo(dbname_param)
    @wsgiwapi.param('overwrite', 1, 1, '^[01]$', [0],
                    "If 1, overwrite an existing database.  If 0 or omitted, "
                    "give an error if the database already exists.")
    @wsgiwapi.param('reopen', 1, 1, '^[01]$', [0],
                    "If 1, and database exists, do nothing.  If 0 or omitted, "
                    "give an error if the database already exists.")
    @wsgiwapi.param('backend', 1, 1, '^[a-z][a-z0-9]*$', ['xappy'],
                    "The database backend to use. Defaults to xappy.")
    @wsgiwapi.jsonreturning
    def db_create(self, request):
        """Create a new database.

        """
        dbname = request.pathinfo['dbname']
        overwrite = bool(int(request.params['overwrite'][0]))
        reopen = bool(int(request.params['reopen'][0]))
        if overwrite and reopen:
            raise ValidationError('"overwrite" and "reopen" must not '
                                  'both be specified')
        self.controller.create_db(request.params['backend'][0],
                                  dbname, overwrite, reopen)
        return True

    @wsgiwapi.allow_DELETE
    @wsgiwapi.pathinfo(dbname_param)
    @wsgiwapi.param('allow_missing', 1, 1, '^[01]$', [0],
                    "If 1, and the database doesn't exist, do nothing.  If "
                    "0 or omitted, give an error if database doesn't exist.")
    @wsgiwapi.jsonreturning
    def db_delete(self, request):
        """Delete a database.

        """
        dbname = request.pathinfo['dbname']
        allow_missing = bool(int(request.params['allow_missing'][0]))
        self.controller.delete_db(dbname, allow_missing)
        return True

    @wsgiwapi.allow_POST
    @wsgiwapi.pathinfo(dbname_param)
    @wsgiwapi.jsonreturning
    def db_flush(self, request):
        """Flush changes to the database.
        
        FIXME: this is a hack!
        (we also need to support automatic flushing).
        """
        dbname = request.pathinfo['dbname']
        self.controller.flush(dbname)
        return True

    #### schema methods ####

    @wsgiwapi.allow_GETHEAD
    @wsgiwapi.noparams
    @wsgiwapi.pathinfo(dbname_param)
    @wsgiwapi.jsonreturning
    def schema_info(self, request):
        dbname = request.pathinfo['dbname']
        db = self.controller.get_db_reader(dbname)
        scm = db.get_schema()
        return scm.as_dict()

    @wsgiwapi.allow_GETHEAD
    @wsgiwapi.noparams
    @wsgiwapi.pathinfo(dbname_param)
    @wsgiwapi.jsonreturning
    def schema_get_language(self, request):
        dbname = request.pathinfo['dbname']
        db = self.controller.get_db_reader(dbname)
        scm = db.get_schema()
        return scm.language

    @wsgiwapi.allow_POST
    @wsgiwapi.param('language', 1, 1, '^\w+$', ['none'],
                    """The default language to use for this database.

                    Specify 'none' to do no language-specific processing.

                    Defaults to 'none'.
                    """)
    @wsgiwapi.pathinfo(dbname_param)
    @wsgiwapi.jsonreturning
    def schema_set_language(self, request):
        """Set the default language for language for the database.

        """
        dbname = request.pathinfo['dbname']
        language = request.pathinfo['language']

        dbr = self.controller.get_db_reader(dbname)
        dbw = self.controller.get_db_writer(dbname)
        scm = dbr.get_schema()
        scm.language = language
        dbw.set_schema(scm)
        # FIXME - should we flush this immediately?

        return True

    #### schema/field methods ####

    @wsgiwapi.allow_POST
    @wsgiwapi.allow_PUT
    @wsgiwapi.pathinfo(dbname_param, fieldname_param)
    @wsgiwapi.jsonreturning
    def field_set(self, request):
        """Set the configuration for a field.

        """
        dbname = request.pathinfo['dbname']
        fieldname = request.pathinfo['fieldname']
        dbr = self.controller.get_db_reader(dbname)
        scm = dbr.get_schema()

#        # don't overwrite existing field
#        if request.method == 'POST' and fieldname in scm.get_field_names():
#            return wsgiwapi.JsonResponse(False, 409)
        
        try:
            scm.set_field(fieldname, request.json)
            dbw = self.controller.get_db_writer(dbname)
            dbw.set_schema(scm)
         
            # FIXME - should we flush this immediately?
            return True
        except schema.FieldError, e:
            raise wsgiwapi.HTTPError(400, e.message)

    @wsgiwapi.allow_GETHEAD
    @wsgiwapi.pathinfo(dbname_param, fieldname_param)
    @wsgiwapi.jsonreturning
    def field_get(self, request):
        dbname = request.pathinfo['dbname']
        fieldname = request.pathinfo['fieldname']

        db = self.controller.get_db_reader(dbname)
        scm = db.get_schema()
        try:
            return scm.get_field(fieldname)
        except KeyError:
            raise wsgiwapi.HTTPNotFound()

    @wsgiwapi.allow_DELETE
    @wsgiwapi.pathinfo(dbname_param, fieldname_param)
    @wsgiwapi.jsonreturning
    def field_delete(self, request):
        dbname = request.pathinfo['dbname']
        fieldname = request.pathinfo['fieldname']

        dbr = self.controller.get_db_reader(dbname)
        scm = dbr.get_schema()
        try:
            scm.get_field(fieldname) # check it exists
        except KeyError:
            raise wsgiwapi.HTTPNotFound()

        scm.delete_field(fieldname)
        dbw = self.controller.get_db_writer(dbname)
        dbw.set_schema(scm)
        return True
            
    @wsgiwapi.allow_GETHEAD
    @wsgiwapi.pathinfo(dbname_param)
    @wsgiwapi.jsonreturning
    def fields_list(self, request):
        dbname = request.pathinfo['dbname']
        db = self.controller.get_db_reader(dbname)
        scm = db.get_schema()
        return scm.get_field_names()

    #### document methods ####

    @wsgiwapi.allow_GETHEAD
    @wsgiwapi.pathinfo(dbname_param, docid_param)
    @wsgiwapi.jsonreturning
    def doc_get(self, request):
        dbname = request.pathinfo['dbname']
        doc_id = request.pathinfo['docid']
        db = self.controller.get_db_reader(dbname)
        try:
            return db.get_document(doc_id)
        except KeyError:
            raise wsgiwapi.HTTPNotFound()

    @wsgiwapi.allow_POST
    @wsgiwapi.pathinfo(dbname_param)
    @wsgiwapi.jsonreturning
    def doc_add(self, request):
        """Add document.

        NOTE: strictly speaking, creating a resource should return status 201
        with the resource location in the Location: header. However, this
        causes the PHP HTTP client to redirect, which is not what we want! So
        we'll bend the REST rules and always return 200 for success, with the
        docid (or whatever) in the body.

        NOTE: currently not returning doc ID, since we can't get it from Xappy
        until the doc is (asynchronously) added. A possible solution is to
        set a UUID or similar.
        """
        dbname = request.pathinfo['dbname']
        dbw = self.controller.get_db_writer(dbname)
        dbw.add_document(request.json)
        return True

    @wsgiwapi.allow_POST
    @wsgiwapi.pathinfo(dbname_param, docid_param)
    @wsgiwapi.jsonreturning
    def doc_add2(self, request):
        """Add or replace a document with a specfied ID.

        """
        dbname = request.pathinfo['dbname']
        dbw = self.controller.get_db_writer(dbname)
        dbw.add_document(request.json, docid=request.pathinfo['docid'])
        return True

    @wsgiwapi.allow_POST
    @wsgiwapi.pathinfo(dbname_param)
    @wsgiwapi.jsonreturning
    def doc_delete(self, request):
        raise NotImplementedError

    @wsgiwapi.allow_GET
    @wsgiwapi.pathinfo(dbname_param)
    @wsgiwapi.jsonreturning
    @wsgiwapi.param('query', 0, 1, None, [''],
                    """A user-entered query string.

                    """)
    @wsgiwapi.param('start_rank', 0, 1, '^\d*$', ['0'],
                    """The offset of the first document to return.

                    0-based - ie, 0 returns the top document first.

                    """)
    @wsgiwapi.param('end_rank', 0, 1, '^\d+$', ['10'],
                    """The rank one past the last hit to return.

                    e.g. the defaults return the 10 hits ranked 0-9.
                    Note that the search may return fewer hits than requested.
                    """)
    def search_simple(self, request):
        dbname = request.pathinfo['dbname']
        query = request.params['query'][0]
        start_rank = int(request.params['start_rank'][0])
        end_rank = int(request.params['end_rank'][0])
        db = self.controller.get_db_reader(dbname)
        return db.search_simple(query, start_rank, end_rank)

    @wsgiwapi.allow_GET
    @wsgiwapi.pathinfo(dbname_param)
    @wsgiwapi.jsonreturning
    @wsgiwapi.param('query_all', 0, 1, None, [''],
                    """A user-entered query string matching all terms.

                    """)
    @wsgiwapi.param('query_any', 0, 1, None, [''],
                    """A user-entered query string matching any terms.

                    """)
    @wsgiwapi.param('query_none', 0, 1, None, [''],
                    """A user-entered query string matching no terms.


                    """)
    @wsgiwapi.param('query_phrase', 0, 1, None, [''],
                    """A user-entered query string matching a phrase.

                    """)
    @wsgiwapi.param('filter', 0, 100, None, [],
                    """A filter on a specified field.

                    Format: fieldname:query text
                    """)
    @wsgiwapi.param('start_rank', 0, 1, '^\d*$', ['0'],
                    """The offset of the first document to return.

                    0-based - ie, 0 returns the top document first.

                    """)
    @wsgiwapi.param('end_rank', 0, 1, '^\d+$', ['10'],
                    """The rank one past the last hit to return.

                    e.g. the defaults return the 10 hits ranked 0-9.
                    Note that the search may return fewer hits than requested.
                    """)
    def search_structured(self, request):
        """Search a structured query. 
        
        FIXME - use GET params instead of JSON.
        """
        dbname = request.pathinfo['dbname']
        db = self.controller.get_db_reader(dbname)
        return db.search_structured(request.params['query_all'][0],
                                    request.params['query_any'][0],
                                    request.params['query_none'][0],
                                    request.params['query_phrase'][0],
                                    request.params['filter'],
                                    int(request.params['start_rank'][0]),
                                    int(request.params['end_rank'][0]),)

    #### end of implementations ####

    def get_urls(self):
        return {
            '': self.flax_status,
            'v1/dbs': self.dbnames,
            'v1/dbs/*': wsgiwapi.MethodSwitch(
                get=self.db_info,
                post=self.db_create,
                delete=self.db_delete),
            'v1/dbs/*/flush': self.db_flush,
            'v1/dbs/*/schema': self.schema_info,
            'v1/dbs/*/schema/language': wsgiwapi.MethodSwitch(
                get=self.schema_get_language,
                post=self.schema_set_language),
            'v1/dbs/*/schema/fields': wsgiwapi.MethodSwitch(
                get=self.fields_list,),
            'v1/dbs/*/schema/fields/*': wsgiwapi.MethodSwitch(
                get=self.field_get,
                post=self.field_set,
                put=self.field_set,
                delete=self.field_delete),
            'v1/dbs/*/docs': wsgiwapi.MethodSwitch(
                post=self.doc_add),             
            'v1/dbs/*/docs/*': wsgiwapi.MethodSwitch(
                get=self.doc_get,
                post=self.doc_add2,
                put=self.doc_add2,
                delete=self.doc_delete),
            'v1/dbs/*/search/simple': self.search_simple,
            'v1/dbs/*/search/structured': self.search_structured,
        }

def App(*args, **kwargs):
    server = SearchServer(*args, **kwargs)
    return wsgiwapi.make_application(server.get_urls(), logger=wsgiwapi.VerboseLogger)
