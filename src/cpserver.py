#$Id:$

# Copyright (C) 2007 Lemur Consulting Ltd

# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.
"""
Flax web server.
"""
import os
import cherrypy
import routes

import flax
import templates
import util
util.setup_psyco()

class FlaxResource(object):
    "Abstract class supporting common error handling across all Flax web pages"

    def _only_post(self, message='Only "POST" supported'):
        "utility for raising 405 when we're expecting a post but get something else"
        if cherrypy.request.method != "POST":
            cherrypy.response.headers['Allow'] = "POST"
            raise cherrypy.HTTPError(405, message)

    def _bad_request(self, message="Bad request"):
        "method to signal that data we receive cannot be used"
        raise cherrypy.HTTPError(400, message) 
        
    

class Collections(FlaxResource):
    """
    Controller for web pages dealing with document collections.
    """

    def _bad_collection_name(self, name):
        self._bad_request("%s does not name a collection." % name if name else "No collection name supplied")

    def __init__(self, flax_data, list_template, detail_template):
        """
        Collections constructor.
        
        :Parameters:
            - `collections`: The set of document collections.
            - `list_template`: A template for rendering the set of document collections.
            - `detail_template`: A template for rendering a single collection.
        """
        self._flax_data = flax_data
        self._list_template = list_template
        self._detail_template = detail_template

    def _redirect_to_view(self, col):
        raise cherrypy.HTTPRedirect('/admin/collections/' + col + '/view' )

    def do_indexing(self, col=None, **kwargs):
        """
        (Re)-index a document collection.
        
        :Parameters:
            - `col`: Names the document collection to be indexed.

        This method forces an immediate indexing of the document
        collection named by the parameter `col`.

        The HTTP method should be POST

        A 400 is returned if either:
        
        - `col` is ommited; or
        - `col` is present by does not name a collection;
        """
        
        self._only_post()

        if col and col in self._flax_data.collections:
            self._flax_data.collections[col].do_indexing(self._flax_data.filter_settings)
            self._redirect_to_view(col)
        else:
            self._bad_collection_name(col)
         
    def update(self, col=None, **kwargs):
        """
        Update the attributes of a document collection.

        :Parameters:
            - `col`: The name of the document collection to be updated.

        Updates the document collection named by `col` with the
        remaining keyword arguments by POSTing. 

        Only POST should be used, 405 is returned otherwise.

        If `col` is not supplied or does not name a collection then
        400 is returned.

        """

        self._only_post()

        if col and col in self._flax_data.collections:
            self._flax_data.collections[col].update(**kwargs)
            self._redirect_to_view(col)
        else:
            raise self._bad_collection_name(col)
     
    def add(self, col = None, **kwargs):
        """
        Create a new document collection.

        :Parameters:
            - `col`: The name for the new collection.

        Creates a new collection named `col`. The remaining keywords
        args are used to update the new collection.

        Only POST should be used, 405 is returned otherwise.

        If col is not provided or there is already a collection named
        `col` then a 400 is returned.
        """
        self._only_post('New collections must be created with "POST"' )

        if col and not col in self._flax_data.collections:
            self._flax_data.collections.new_collection(col, **kwargs)
            self._redirect_to_view(col)
        else:
            self._bad_request("Attempt to create a document collection that already exists or that has an invalid name.")


    def view(self, col=None, **kwargs):
        """
        View a document collection.

        :Parameters:
            - `col`: The name of the collection to be viewed.

        Shows the detail for the document collection named by `col`,
        if it exists; otherwise return 404.
        """
        if col:
            if col in self._flax_data.collections:
                return self._detail_template.render(self._flax_data.collections[col],
                                                    self._flax_data.formats,
                                                    self._flax_data.languages)
            else:
                raise cherrypy.NotFound()
        else:
            return self._list_template.render(self._flax_data.collections.itervalues(),
                                              routes.url_for('/admin/collections'))

class SearchForm(object):
    """
    A controller for searching document collections and rendering
    the results.
    """

    def __init__(self, collections, search_template, result_template):
        """
        :Parameters:
            - `collections`: the set of document collections to be searched.
            - `search_template`: A template for redering the search form.
            - `result_template`: A template for rendering search results.
        """
        self._collections = collections
        self._template = search_template
        self._result_template = result_template

    def search(self, query = None, col = None, advanced = False):
        """
        Search document collections.

        :Parameters:
            - `query`: the search query
            - `col`: the (list of) collection(s) to be searched.
            - `advanced`: the style of search form.

        If `col` and `query` are provided then use `query` to search
        all the document collections named by `col` and return the
        results. (In this case the value of `advanced` is ignored.)

        Otherwise render a page containing a form to initiate a new
        search. If `advanced` tests true then the form will have more
        structure.
        """
        if query:
            cols = [col] if isinstance(col, str) else col                  
            results = self._collections.search(query, cols)
            return self._result_template.render(query, cols, results)
        else:
            return self._template.render(self._collections, advanced, self._collections._formats)



class Top(FlaxResource):
    """
    A contoller for the default (end-user) web pages.
    """
    def __init__(self, flax_data, search_template, search_result_template):
        """
        Constructor.

        :Parameters:
            - `collections`: collections to be processed.
            - `search_template`: template for the search forms.
            - `search_result_template`: template for rendering search results.
        """

        self._flax_data = flax_data
        self._search = SearchForm(flax_data.collections, search_template, search_result_template)

    def search(self, **kwargs):
        """
        Do a basic (i.e. advanced = False) search. See `SearchForm.search`.
        """
        return self._search.search(advanced=False, **kwargs )

    def advanced_search(self, **kwargs):
        """
        Do an advanced (i.e. advanced = True) search. See `SearchForm.search`.
        """
        return self._search.search(advanced=True, **kwargs )


    def source(self, col, file_id):
        """
        Serve the source file for the document in document collection
        named by col with file_id id.
        """
        # Quite possibly this is a security hole allowing any
        # documents to be accessed. Need to think carefully about how
        # we actually ensure that we're just serving from the document
        # collections. In any case I guess it makes sense for the
        # process running the web server to have limited read access.
        print "col: %s, file_id: %s" % (col, file_id)
        if col in self._flax_data.collections:
            filename = self._flax_data.collections[col].source_file_from_id(file_id)
            if filename:
                return cherrypy.lib.static.serve_file(filename)
        # fall through we can't find either the collection or the file named by file_id
        raise cherrypy.NotFound()



         
class Admin(Top):
    """
    A controller for the administration pages.
    """

    def __init__(self, flax_data, search_template, search_result_template, options_template, index_template):
        """
        Constructor.

        :Parameters:
            - `collections`: collections to be processed.
            - `search_template`: template for the search forms.
            - `search_result_template`: template for rendering search results.
            - `options_template`: template for the global options page.
            - `index_template`: template for the index page.
        """
        self._options_template = options_template
        self._index_template = index_template
        super(Admin, self).__init__(flax_data, search_template, search_result_template)

    def options(self, **kwargs):
        """
        Render the options template.
        """
        if cherrypy.request.method == "POST":

            for arg in ("db_dir", "flax_dir"):
                if arg in kwargs:
                    setattr(self._flax_data, arg, kwargs[arg])

            for log_event in self._flax_data.log_events:
                if log_event in kwargs:
                    self._flax_data.log_settings[log_event] = kwargs[log_event]

            for format in self._flax_data.formats:
                if format in kwargs:
                    self._flax_data.filter_settings[format] = kwargs[format]

        return self._options_template.render(self._flax_data)

    def index(self):
        """
        Render the index template.
        """
        return self._index_template.render()


def setup_routes(top_controller, admin_contoller, collections_controller):
    """
    Define the mapping from urls to objects/methods for the CherryPy routes dispatcher.
    """


    d = cherrypy.dispatch.RoutesDispatcher()
    d.connect('top', '/', controller = top_controller, action='search')
    d.connect('user_search', '/search', controller = top_controller, action='search')
    d.connect('source_file', '/source', controller = top_controller, action='source')

    d.connect('collections_add', 'admin/collections/add', controller = collections_controller, action='add' )
    d.connect('collections', '/admin/collections/:col/:action', controller = collections_controller, action='view')
    d.connect('collections_default', '/admin/collections/', controller = collections_controller, action='view')

    d.connect('admin', '/admin/:action', action='index', controller=admin_contoller )

    return d


def start_web_server(flax_data):
    """
    Run Flax web server.
    """
    flax_data = flax.options

    top = Top(flax_data, templates.user_search_template, templates.user_search_result_template)

    admin = Admin(flax_data,
                  templates.admin_search_template,
                  templates.admin_search_result_template,
                  templates.options_template,
                  templates.index_template)
    
    collections = Collections(flax_data,
                              templates.collection_list_template,
                              templates.collection_detail_template)

    d = setup_routes(top, admin, collections)
    
    cherrypy.config.update('cp.conf')
    cherrypy.quickstart(None, config = { '/': { 'request.dispatch': d},
                                         '/static': {'tools.staticdir.on': True,
                                                     'tools.staticdir.root': os.path.dirname(os.path.abspath(__file__)),
                                                     'tools.staticdir.dir': 'static'}})

def startup():
    import persist
    import optparse
    op = optparse.OptionParser()
    op.add_option('-i', '--input-file', dest='input_file', help = "Flax input data file (default is flax.flx)", default = 'flax.flx')
    op.add_option('-o', '--output-file', dest='output_file', help= "Flax output data file (default is flax.flx)", default = 'flax.flx')
    (options, args) = op.parse_args()
    flax.options = persist.read_flax(options.input_file)
    try:
        start_web_server(flax.options)
    finally:
        persist.store_flax(options.output_file, flax.options)


if __name__ == "__main__":
    startup()


