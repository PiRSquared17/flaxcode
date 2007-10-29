#!/usr/bin/env python
#
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
r"""memutils.py: Memory handling utilities.

"""
__docformat__ = "restructuredtext en"

import os

def _get_physical_mem_sysconf():
    """Try getting a value for the physical memory using os.sysconf().

    Returns None if no value can be obtained - otherwise, returns a value in
    bytes.

    """
    if getattr(os, 'sysconf', None) is None:
        return None

    try:
        pagesize = os.sysconf('SC_PAGESIZE')
    except ValueError:
        try:
            pagesize = os.sysconf('SC_PAGE_SIZE')
        except ValueError:
            return None

    try:
        pagecount = os.sysconf('SC_PHYS_PAGES')
    except ValueError:
        return None

    return pagesize * pagecount

def _get_physical_mem_win32():
    """
    """
    try:
        from ctypes import *
        from ctypes.wintypes import *
    except ValueError:
        return None

    
    class MEMORYSTATUS(Structure):
        _fields_ = [
            ('dwLength', DWORD),
            ('dwMemoryLoad', DWORD),
            ('dwTotalPhys', DWORD),
            ('dwAvailPhys', DWORD),
            ('dwTotalPageFile', DWORD),
            ('dwAvailPageFile', DWORD),
            ('dwTotalVirtual', DWORD),
            ('dwAvailVirtual', DWORD),
        ]

    m = MEMORYSTATUS()
    windll.kernel32.GlobalMemoryStatus(byref(m))
    return m.dwTotalPhys

def get_physical_memory():
    """Get the amount of physical memory in the system, in bytes.

    If this can't be obtained, returns None.

    """
    result = _get_physical_mem_sysconf()
    if result is not None:
        return result
    return _get_physical_mem_win32()
    