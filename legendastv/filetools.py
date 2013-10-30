# -*- coding: utf-8 -*-
#
#    Copyright (C) 2012 Rodrigo Silva (MestreLion) <linux@rodrigosilva.com>
#    This file is part of Legendas.TV Subtitle Downloader
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program. See <http://www.gnu.org/licenses/gpl.html>
#
# Miscellaneous file-handling functions

import os.path as osp

import logging
log = logging.getLogger(__name__)
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)


# Most common video file extensions. NOT meant as a comprehensive list!
# Listed here for performance reasons only,  to avoid a perhaps expensive mimetype detection
VIDEO_EXTS = {'avi', 'm4v', 'mkv', 'mp4', 'mpg', 'mpeg', 'ogv', 'rmvb', 'wmv', 'ts'}

# Extensions that are not properly detected as "video/" mimetype
VIDEO_EXTS_EXTRA = {}

try:

    from gi import Repository
    if not Repository.get_default().enumerate_versions('Gio'):
        raise ImportError
    from gi.repository import Gio
    log.debug("using Gio")

    VIDEO_EXTS_EXTRA = {'mpv', 'ts', 'wm', 'wx', 'xvid'}

    def mimetype(path):
        ''' Mimetype of a file, determined by its extension and, in case of
            extensionless files, its initial content (1KB read).
            Return 'application/octet-stream' for unknown types and non-files:
            directories, broken symlinks, path not found, access denied.
        '''
        mime = Gio.content_type_get_mime_type(Gio.content_type_guess(filename=path, data=None)[0])
        if extension(path):
            return mime

        try:
            with open(path, 'rb') as f:
                return Gio.content_type_guess(filename=None, data=f.read(1024))[0]
        except IOError:
            return mime  # most likely access denied or file not found

    # .60d    application/octet-stream
    # .ajp    application/octet-stream
    # .asx    audio/x-ms-asx
    # .avchd    application/octet-stream
    # .bik    application/octet-stream
    # .bin    application/octet-stream
    # .bix    application/octet-stream
    # .box    application/octet-stream
    # .cam    application/octet-stream
    # .cue    application/x-cue
    # .dat    application/octet-stream
    # .dif    application/octet-stream
    # .dl    application/octet-stream
    # .dmf    application/octet-stream
    # .dvr-ms    application/octet-stream
    # .evo    application/octet-stream
    # .flic    application/octet-stream
    # .flx    application/octet-stream
    # .gl    application/octet-stream
    # .gvi    application/octet-stream
    # .gvp    text/x-google-video-pointer
    # .h264    application/octet-stream
    # .lsf    application/octet-stream
    # .lsx    application/octet-stream
    # .m1v    application/octet-stream
    # .m2p    application/octet-stream
    # .m2v    application/octet-stream
    # .m4e    application/octet-stream
    # .mjp    application/octet-stream
    # .mjpeg    application/octet-stream
    # .mjpg    application/octet-stream
    # .movhd    application/octet-stream
    # .movx    application/octet-stream
    # .mpa    application/octet-stream
    # .mpv    application/octet-stream
    # .mpv2    application/octet-stream
    # .mxf    application/mxf
    # .nut    application/octet-stream
    # .ogg    audio/ogg
    # .omf    application/octet-stream
    # .ps    application/postscript
    # .ram    application/ram
    # .rm    application/vnd.rn-realmedia
    # .rmvb    application/vnd.rn-realmedia
    # .swf    application/x-shockwave-flash
    # .ts    text/vnd.trolltech.linguist
    # .vfw    application/octet-stream
    # .vid    application/octet-stream
    # .video    application/octet-stream
    # .vro    application/octet-stream
    # .wm    application/octet-stream
    # .wmx    audio/x-ms-asx
    # .wrap    application/octet-stream
    # .wvx    audio/x-ms-asx
    # .wx    application/octet-stream
    # .x264    application/octet-stream
    # .xvid    application/octet-stream


except ImportError:

    import mimetypes
    log.debug("using Lib/mimetypes")

    mimetypes.init()

    VIDEO_EXTS_EXTRA = {'divx', 'm2ts', 'mpv', 'ogm', 'rmvb', 'ts', 'wm', 'wx', 'xvid'}

    def mimetype(path):
        ''' Mimetype of a file, determined by its extension.
            Return 'application/octet-stream' for unknown types and non-files:
            directories, broken symlinks, path not found, access denied.
        '''
        return mimetypes.guess_type(path, strict=False)[0] or "application/octet-stream"

    # .3g2    None
    # .3gp2    None
    # .3gpp    None
    # .60d    None
    # .ajp    None
    # .avchd    None
    # .bik    None
    # .bin    application/octet-stream
    # .bix    None
    # .box    None
    # .cam    None
    # .cue    None
    # .dat    application/x-ns-proxy-autoconfig
    # .divx    None
    # .dmf    None
    # .dvr-ms    None
    # .evo    None
    # .flc    None
    # .flic    None
    # .flx    None
    # .gvi    None
    # .gvp    None
    # .h264    None
    # .m2p    None
    # .m2ts    None
    # .m2v    None
    # .m4e    None
    # .m4v    None
    # .mjp    None
    # .mjpeg    None
    # .mjpg    None
    # .moov    None
    # .movhd    None
    # .movx    None
    # .mpv2    None
    # .mxf    application/mxf
    # .nsv    None
    # .nut    None
    # .ogg    audio/ogg
    # .ogm    None
    # .omf    None
    # .ps    application/postscript
    # .ram    audio/x-pn-realaudio
    # .rm    audio/x-pn-realaudio
    # .rmvb    None
    # .swf    application/x-shockwave-flash
    # .vfw    None
    # .vid    None
    # .video    None
    # .viv    None
    # .vivo    None
    # .vob    None
    # .vro    None
    # .wrap    None
    # .wx    None
    # .x264    None
    # .xvid    None


def is_video(path):
    ''' Return True if path should be considered a video file, False otherwise.
        Determined by both file extension and its mimetype.
    '''
    ext = extension(path)
    if ext in VIDEO_EXTS or ext in VIDEO_EXTS_EXTRA:
        return True

    mimes = ['x-ms-asx',                                   # MS Windows Media Player - asx, wmx, wvx
             'ram', 'vnd.rn-realmedia', 'x-pn-realaudio',  # RealAudio/Media - ram, rm, rmvb
             'x-shockwave-flash',                          # Adobe Flash Player - swf
             ]
    type, mime = mimetype(path).split('/')
    return type == 'video' or mime in mimes


def extension(path):
    ''' Normalized extension for a filename: lowercase and without leading '.'
        Can be empty. Does not consider POSIX hidden files to be extensions.
        Example: extension('A.JPG') -> 'jpg'
    '''
    return osp.splitext(path)[1][1:].lower()


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        log.critical("Missing argument\nUsage: %s FILE", __file__)
        sys.exit(1)

    for path in sys.argv[1:]:
        if osp.isfile(path):
            print
            print osp.realpath(path)
            print mimetype(path)
            print "%svideo" % ("" if is_video(path) else "NOT ")
