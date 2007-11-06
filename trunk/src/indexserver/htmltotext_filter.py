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
"""Filter for HTML documents, using the htmltotext module.

This is a reliable, in-process, HTML filter, which copes with badly formed HTML
pages, and strips out javascript, CSS and PHP sections.

"""
from __future__ import with_statement
__docformat__ = "restructuredtext en"

import setuppaths
import htmltotext

def html_filter(filename):
    with open(filename) as f:
        html = f.read()
        p = htmltotext.extract(html)
        yield "title", p.title
        yield "content", p.content
        yield "description", p.description
        kw = p.keywords.strip()
        if len(kw) != 0:
            for keyword in kw.split(','):
                yield "keyword", p.keywords
        yield "invalid", "he he"
