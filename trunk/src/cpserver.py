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
"""Flax web interface, using the cherrypy webserver.

"""
__docformat__ = "restructuredtext en"

import setuppaths
import cherrypy
import templates
import persist
import util

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

    def _signal_data_changed(self):
        persist.data_changed.set()


class Collections(FlaxResource):
    """
    Controller for web pages dealing with document collections.
    """

    def _bad_collection_name(self, name):
        self._bad_request("%s does not name a collection." % name if name else "No collection name supplied")

    def __init__(self, flax_data, list_template, detail_template, index_server):
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
        self._index_server = index_server

    def _redirect_to_view(self, col=None):
        if col:
            raise cherrypy.HTTPRedirect('/admin/collections/' + col + '/view' )
        else:
            raise cherrypy.HTTPRedirect('/admin/collections/')


    @cherrypy.expose
    def default(self, col_id=None, action=None, **kwargs):
        if col_id and action:
            if action == 'toggle_due':
                return self.toggle_due_or_held(col_id, **kwargs)
            elif action == 'delete':
                return self.delete(col_id, **kwargs)
            elif action == 'toggle_held':
                return self.toggle_due_or_held(col_id, held=True, **kwargs)
            elif action == 'update':
                return self.update(col_id, **kwargs)
            elif action == 'view':
                return self.view(col_id, **kwargs)
        elif col_id:
            return self.view(col_id)
        else:
            return self.view()

    def toggle_due_or_held(self, col=None, held=False, **kwargs):
        """
        Set or clears one of the flags controlling collection indexing

        :Parameters:
            - `col`: Names the document collection to be indexed.
            - `held`: If True set the held flag, otherwise the due flag.

        The HTTP method should be POST

        A 400 is returned if either:

        - `col` is omitted; or
        - `col` is present by does not name a collection;
        """

        self._only_post()

        if col and col in self._flax_data.collections:
            self._index_server.toggle_due_or_held(self._flax_data.collections[col], held)
            return self._redirect_to_view()
        else:
            self._bad_collection_name(col)


    def delete(self, col=None, **kwargs):

        self._only_post()

        if col in self._flax_data.collections:
            self._flax_data.collections.remove_collection(col)
            return self.view()

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
            collection = self._flax_data.collections[col]
            collection.update(**kwargs)
            self._signal_data_changed()
            self._index_server.stop_indexing(collection)
            self._index_server.set_due(collection)
            self._redirect_to_view(col)
        else:
            raise self._bad_collection_name(col)

    @cherrypy.expose
    def new(self, col=None, **kwargs):
        if cherrypy.request.method == "POST":
            if col is None:
                self._bad_request("A collection name must be provided for new collections")
            elif col in self._flax_data.collections:
                self._bad_request("The collection name is already in use")
            else:
                self._flax_data.collections.new_collection(col, **kwargs)
                self._signal_data_changed()
                self._redirect_to_view(col)
        else:
            return self._detail_template(None, self._flax_data.formats, self._flax_data.languages)

    @cherrypy.expose
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
                return self._detail_template (self._flax_data.collections[col],
                                              self._flax_data.formats,
                                              self._flax_data.languages)
            else:
                raise cherrypy.NotFound()
        else:
            return self._list_template (self._flax_data.collections.itervalues(),
                                        '/admin/collections',
                                        self._index_server)

class SearchForm(object):
    """
    A controller for searching document collections and rendering
    the results.
    """

    def __init__(self, collections, search_template, advanced_template):
        """
        :Parameters:
            - `collections`: the set of document collections to be searched.
            - `search_template`: A template for redering the search form.
            - `result_template`: A template for rendering search results.
        """
        self._collections = collections
        self._template = search_template
        self._advanced_template = advanced_template

    def search(self, query=None, col=None, col_id=None, doc_id=None, advanced=False,
               exact=None, exclusions=None, tophit=0, maxhits=10):
        """
        Search document collections.

        :Parameters:
            - `query`: the search query
            - `col`: the (list of) collection(s) to be searched.
            - `doc_id`: A document to generate a search query.
            - `advanced`: the style of search form.

        One of `query` or (`col_id` and `doc_id`) should be provided

        If `col` and `query` are provided then use `query` to search
        all the document collections named by `col` and return the
        results. (In this case the value of `advanced` is ignored.)

        Otherwise render a page containing a form to initiate a new
        search. If `advanced` tests true then the form will have more
        structure.
        """

        assert not (query and doc_id)
        template = self._advanced_template if advanced else self._template
        tophit = int (tophit)
        maxhits = int (maxhits)
        if (query or exact or exclusions) or (col_id and doc_id):
            cols = util.listify(col) if col else None
            results = self._collections.search(query, col_id=col_id, doc_id=doc_id, cols=cols,
                                               exact=exact, exclusions=exclusions, tophit=tophit, maxhits=maxhits)
            return template(self._collections, results, cols)
        else:
            return template(self._collections)

class Top(FlaxResource):
    """
    A contoller for the default (end-user) web pages.
    """
    def __init__(self, flax_data, search_template, advanced_template):
        """
        Constructor.

        :Parameters:
            - `collections`: collections to be processed.
            - `search_template`: template for the search forms.
            - `search_result_template`: template for rendering search results.
        """

        self._flax_data = flax_data
        self._search = SearchForm(flax_data.collections, search_template, advanced_template)

    @cherrypy.expose
    def index(self):
        raise cherrypy.HTTPRedirect('search')

    @cherrypy.expose
    def search(self, **kwargs):
        """
        Do a basic (i.e. advanced = False) search. See `SearchForm.search`.
        """
        return self._search.search(advanced=False, **kwargs )

    @cherrypy.expose
    def advanced_search(self, **kwargs):
        """
        Do an advanced (i.e. advanced = True) search. See `SearchForm.search`.
        """
        return self._search.search(advanced=True, **kwargs )

class Admin(Top):
    """
    A controller for the administration pages.
    """

    def __init__(self, flax_data, search_template, advanced_template, options_template, index_template):
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
        super(Admin, self).__init__(flax_data, search_template, advanced_template)

    @cherrypy.expose
    def options(self, **kwargs):
        """
        Render the options template.
        """
        if cherrypy.request.method == "POST":
            self._flax_data.log_settings = kwargs
            # Redirect to prevent reloads redoing the POST.
            raise cherrypy.HTTPRedirect('options')
        return self._options_template (self._flax_data)

    @cherrypy.expose
    def index(self):
        """
        Currently no use for home page, so redirect to collections list.
        """
        raise cherrypy.HTTPRedirect ('collections')


def start_web_server(flax_data, index_server, conf_path, templates_path, blocking=True):
    """Start the web server.

    """
    renderer = templates.Renderer(templates_path)
    collections = Collections(flax_data,
                              renderer.collection_list_render,
                              renderer.collection_detail_render,
                              index_server)

    admin = Admin(flax_data,
                  renderer.admin_search_render,
                  renderer.admin_advanced_search_render,
                  renderer.options_render,
                  renderer.index_render)

    top = Top(flax_data, renderer.user_search_render, renderer.user_advanced_search_render)
    admin.collections = collections
    top.admin = admin
    cherrypy.config.update(conf_path)
    cherrypy.tree.mount(top, '/', config=conf_path)
    cherrypy.server.quickstart()
    cherrypy.engine.start(blocking)

def stop_web_server():
    """Stop the flax web server.

    """
    cherrypy.server.stop()
