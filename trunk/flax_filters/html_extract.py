# Copyright (C) 2009, 2010 Lemur Consulting Ltd
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

# htmltotext is available as part of Flax Basic
import htmltotext

def html_filter_from_stream(stream):
    """
    Uses htmltotext to extract content from the supplied stream
    """
    p = htmltotext.extract(stream)
    yield "title", p.title
    yield "textcontent", p.content
    yield "description", p.description
    kw = p.keywords.strip()
    if len(kw) != 0:
        for keyword in kw.split(','):
            yield "keyword", p.keywords
        yield "invalid", "he he"
    

def html_filter(filename):
    with open(filename) as f:
        return html_filter_from_stream(f.read())
