# Copyright (C) 2007 Lemur Consulting Ltd
# Copyright (C) 1994-2001, Mark Hammond
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
#
#
# Portions of this file were derived from an example in the "Python for
# Windows" extensions, to which the following license applies:
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions
#  are met:
#
#  Redistributions of source code must retain the above copyright notice,
#  this list of conditions and the following disclaimer.
#
#  Redistributions in binary form must reproduce the above copyright
#  notice, this list of conditions and the following disclaimer in
#  the documentation and/or other materials provided with the distribution.
#
#  Neither name of Mark Hammond nor the name of contributors may be used
#  to endorse or promote products derived from this software without
#  specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS ``AS
#  IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
#  TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
#  PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE REGENTS OR
#  CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
#  EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
#  PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
#  PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
#  LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
#  NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
#  SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""Filter using the windows-specific ifilter mechanism, over COM.

"""
__docformat__ = "restructuredtext en"

# the code in this file makes com calls. If it's invoked from a thread
# other than the main python thread then a call to
# pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED) should
# be made prior to invoking this code. Such a call should be balanced
# by a call to pythoncom.CoUnInitialize before the thread terminates.

import itertools
import pythoncom
import pywintypes
from win32com.ifilter import ifilter
from win32com.ifilter.ifiltercon import *
from win32com.storagecon import *
import sys
sys.path.append('..')
import util
import logging
log = logging.getLogger("filtering.ifilter")
prop_id_map = { 19 : "content",
                 3 : "HtmlHeading1" }

def prop_id_to_name(prop_id):
    if type(prop_id) is str:
        return prop_id
    elif prop_id in prop_id_map:
        return prop_id_map[prop_id]
    else:
        return prop_id

def text_for_current_chunk(filt):
    def get_text():
        while True:
            yield filt.GetText()

    return(util.gen_until_exception(get_text(),
                                    pythoncom.com_error,
                                    lambda e: e[0] == FILTER_E_NO_MORE_TEXT))

_filter_init_flags = IFILTER_INIT_INDEXING_ONLY | \
                     IFILTER_INIT_CANON_PARAGRAPHS | \
                     IFILTER_INIT_APPLY_INDEX_ATTRIBUTES | \
                     IFILTER_INIT_APPLY_CRAWL_ATTRIBUTES| \
                     IFILTER_INIT_APPLY_OTHER_ATTRIBUTES | \
                     IFILTER_INIT_SEARCH_LINKS

# ensure that the data we pass back is unicode.  It appears to be mbcs
# encoded string data, but the pythonwin docs suggest that it should
# already be unicode. It could be that something to do with the local
# settings affect what we actually get back.
def decode_prop(prop):
    return prop.decode('mbcs') if prop else prop

def ifilter_filter(filename, init_flags = _filter_init_flags, log=log):
    try:
        filt, stg = get_ifilter_for_file(filename, log)
    except pythoncom.com_error, e:
        return e

    init_flags = filt.Init(init_flags)

    def start_fields():
        if init_flags == IFILTER_FLAGS_OLE_PROPERTIES and stg:
           try:
               pss = stg.QueryInterface(pythoncom.IID_IPropertySetStorage)
               ps = pss.Open(PSGUID_SUMMARYINFORMATION)
               props_to_read = (PIDSI_TITLE, PIDSI_SUBJECT, PIDSI_AUTHOR, PIDSI_KEYWORDS, PIDSI_COMMENTS)
               title, subject, author, keywords, comments = map(decode_prop, ps.ReadMultiple(props_to_read))
               if title:
                   yield 'title', title
               if subject:
                   yield 'subject', subject
               if author:
                   yield 'author', author
               if keywords:
                   for k in keywords.split():
                       yield 'keyword', k
               if comments:
                   yield 'comments', comments
           except pythoncom.com_error, e:
               pass

    def do_chunks():
        while True:
            last_chunk = None
            try:
                chunk_id, break_type, flags, locale, (propset_guid, prop_id), chunk_source_id, start, len =  filt.GetChunk()
            except pythoncom.com_error, e:
                error_code = e[0]
                if error_code == FILTER_E_END_OF_CHUNKS:
                    # normal situation when all chunks have been processed
                    break
                elif error_code in (FILTER_E_EMBEDDING_UNAVAILABLE,
                                    FILTER_E_LINK_UNAVAILABLE,
                                    FILTER_E_PASSWORD,
                                    FILTER_E_ACCESS):
                    # these errors mean we can't get hold of the
                    # values in this chunk, but it should be OK to
                    # continue.
                    log.debug("Filtering %s, GetChunk reported error: %s, on or near chunk %d, skipping chunk." %
                              (filename, str(e), chunk_id))
                elif error_code == -2147467259:
                    # this error is a generic com "unspecifed" error
                    # code.  The Adobe ifilter seems to raise it quite
                    # a bit, but apparently it's OK to continue, so we
                    # log and move on. This might be a little risky,
                    # since we don't really know what the error
                    # situation is.
                    log.warning("Filtering %s, GetChunk reported error: %s, skipping chunk and continuing" %
                                (filename, str(e)))
                else:
                    # other exceptions: pass on up
                    log.error("Filtering %s, GetChunk raised unknown error %s, on or near chunk %d, re-raising" %
                              (filename, str(e), chunk_id))
                    raise

            if last_chunk == chunk_id:
                # this shouldn't happen - but it's protection against
                # possible repeated chunks since we might be tring to
                # continue through an "unspecifed" error
                log.error("Filtering %s, in do_chunks, repeated chunk: %d, abadonning document")
                break

            last_chunk = chunk_id
            
            prop_name = prop_id_to_name(prop_id)
            if flags == CHUNK_TEXT:
                for num, txt in enumerate(text_for_current_chunk(filt)):
                    log.debug(u"Block %d of text follows from chunk_id: %d: \n %s \n" % (num,  chunk_id, txt))
                    yield prop_name, txt

    return itertools.chain(start_fields(), do_chunks())

def load_ifilter(filename, log=log):
    try:
        return ifilter.LoadIFilter(filename)
    except pythoncom.com_error, e:
        if e[0] == FILTER_E_UNKNOWNFORMAT:
            log.warning("File %s is not a recognized format" % filename)
        else:
            log.warning("LoadIFilter for file %s, raised error %s, file cannot be processed" % (filename, str(e)))
        raise


def get_ifilter_for_file(filename, log=log):
    """
    Deal with structured storage file if possible.
    See http://msdn2.microsoft.com/en-us/library/aa380369.aspx
    """

    if pythoncom.StgIsStorageFile(filename):
        storage_init_flags = STGM_READ | STGM_SHARE_DENY_WRITE
        stg = pythoncom.StgOpenStorage(filename, None, storage_init_flags)
        try:
            filt = ifilter.BindIFilterFromStorage(stg)
        except pythoncom.com_error, e:
            if e[0] == -2147467262:
                filt = load_ifilter(filename, log=log)
            else:
                raise
    else:
        filt = load_ifilter(filename, log=log)
        stg = None
    return (filt, stg)

# A filter that runs ifilter in a separate process. See remote_filter.
import remote_filter
remote_ifilter = remote_filter.RemoteFilterRunner(ifilter_filter)
