#!/usr/bin/python
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
# Parser and utilities for Legendas.TV website

from __future__ import unicode_literals, absolute_import, division

import os
import re
import dbus
import urllib
import urllib2
import urlparse
import difflib
import zipfile
import operator
import logging
import json
from lxml import html
from datetime import datetime

from . import g
from . import rarfile
from . import opensubtitles

log = logging.getLogger(__name__)


# Languages [and flag names (language "codes")]:
#  1 - Português-BR (Brazilian Portuguese) [brazil]
#  2 - Inglês (English) [usa]
#  3 - Espanhol (Spanish) [es]
#  4 - Francês (French) [fr]
#  5 - Alemão (German) [de]
#  6 - Japonês (Japanese) [japao]
#  7 - Dinamarquês (Danish) [denmark]
#  8 - Norueguês (Norwegian) [norway]
#  9 - Sueco (Swedish) [sweden]
# 10 - Português-PT (Iberian Portuguese) [pt]
# 11 - Árabe (Arabic) [arabian]
# 12 - Checo (Czech) [czech]
# 13 - Chinês (Chinese) [china]
# 14 - Coreano (Corean) [korean]
# 15 - Búlgaro (Bulgarian) [be]
# 16 - Italiano (Italian) [it]
# 17 - Polonês (Polish) [poland]

# Search Type:
# <blank> - All subtitles
# d       - Destaque (Highlighted subtitles only)
# p       - Pack (Subtitle packs only, usually for series seasons)

def notify(body, summary='', icon=''):

    # Fallback for no notifications
    if not g.options['notifications']:
        log.notify("%s - %s", summary, body)
        return

    # Use the same interface object in all calls
    if not g.globals['notifier']:
        _bus_name = 'org.freedesktop.Notifications'
        _bus_path = '/org/freedesktop/Notifications'
        _bus_obj  = dbus.SessionBus().get_object(_bus_name, _bus_path)
        g.globals['notifier'] = dbus.Interface(_bus_obj, _bus_name)

    app_name    = g.globals['apptitle']
    replaces_id = 0
    summary     = summary or app_name
    actions     = []
    hints       = {'x-canonical-append': "" }  # merge if same summary
    timeout     = -1 # server default

    if icon and os.path.exists(icon):
        g.globals['notify_icon'] = icon # save for later
    app_icon    = g.globals['notify_icon']

    g.globals['notifier'].Notify(app_name, replaces_id, app_icon, summary, body,
                                actions, hints, timeout)
    log.notify(body)

def print_debug(text):
    log.debug('\n\t'.join(text.split('\n')))

def fields_to_int(dict, *keys):
    """ Helper function to cast several fields in a dict to int
        usage: int_fields(mydict, 'keyA', 'keyB', 'keyD')
    """
    for key in keys:
        if dict[key] is not None:
            dict[key] = int(dict[key])

def get_similarity(text1, text2, ignorecase=True):
    """ Returns a float in [0,1] range representing the similarity of 2 strings
    """
    if ignorecase:
        text1 = text1.lower()
        text2 = text2.lower()
    return difflib.SequenceMatcher(None, text1, text2).ratio()

def choose_best_string(reference, candidates, ignorecase=True):
    """ Given a reference string and a list of candidate strings, return a dict
        with the candidate most similar to the reference, its index on the list
        and the similarity ratio (a float in [0, 1] range)
    """
    if ignorecase:
        reference_lower  = reference.lower()
        candidates_lower = [c.lower() for c in candidates]
        result = difflib.get_close_matches(reference_lower,
                                           candidates_lower,1, 0)[0]

        index = candidates_lower.index(result)
        best  = candidates[index]
        similarity = get_similarity(reference_lower, result, False)

    else:
        best = difflib.get_close_matches(reference, candidates, 1, 0)[0]
        index = candidates.index(best)
        similarity = get_similarity(reference, best, False)

    return dict(best = best,
                index = index,
                similarity = similarity)

def choose_best_by_key(reference, dictlist, key, ignorecase=True):
    """ Given a reference string and a list of dictionaries, compares each
        dict key value against the reference, and return a dict with keys:
        'best' = the dict whose key value was the most similar to reference
        'index' = the position of the chosen dict in dictlist
        'similarity' = the similarity ratio between reference and dict[key]
    """
    if ignorecase:
        best = choose_best_string(reference.lower(),
                                  [d[key].lower() for d in dictlist],
                                  ignorecase = False)
    else:
        best = choose_best_string(reference, [d[key] for d in dictlist], False)


    result = dict(best = dictlist[best['index']],
                  similarity = best['similarity'])
    print_debug("Chosen best for '%s' in '%s': %s" % (reference, key, result))
    return result

def clean_string(text):
    text = re.sub(r"^\[.+?]"   ,"",text)
    text = re.sub(r"[][}{)(.,:_-]"," ",text)
    text = re.sub(r" +"       ," ",text).strip()
    return text

def guess_movie_info(text):

    text = text.strip()

    # If 2+ years found, pick the last one and pray for a sane naming scheme
    year = re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", text)
    year = year[-1] if year else ""

    release = clean_string(text)

    if year:
        title = release.split(year,1)[1 if release.startswith(year) else 0]
    else:
        title = release

    # Remove some common "tags"
    tags = ['1080p','720p','480p','hdtv','h264','x264','h65','dts','aac','ac3',
            'bluray','bdrip','brrip','dvd','dvdrip','xvid','mp4','itunes',
            'web dl','blu ray']
    for s in tags:
        title = re.sub(s, "", title, 0, re.IGNORECASE)
    title = re.sub(" +", " ", title).strip()

    result = dict(year=year, title=title, release=release)
    print_debug("Guessed title info: '%s' -> %s" % (text, result))
    return result

def filter_dict(dict, keys=[], whitelist=True):
    """ Filter a dict, returning a copy with only the selected keys
        (or all *but* the selected keys, if not whitelist)
    """
    if keys:
        if whitelist:
            return dict([(k, v) for (k, v) in dict.items() if k in keys])
        else:
            return dict([(k, v) for (k, v) in dict.items() if k not in keys])
    else:
        return dict

def print_dictlist(dictlist, keys=None, whitelist=True):
    """ Prints a list, an item per line """
    return "\n".join([repr(filter_dict(d, keys, whitelist))
                      for d in dictlist])

def extract_archive(archive, dir="", extlist=[], keep=False):
    """ Extract files from a zip or rar archive whose filename extension
        (including the ".") is in extlist, or all files if extlist is empty.
        If keep is False, also delete the archive afterwards
        - archive is the archive filename (with path)
        - dir is the extraction folder, same folder as archive if empty
        return: a list with the filenames (with path) of extracted files
    """

    # Clean up arguments
    archive = os.path.expanduser(archive)
    dir     = os.path.expanduser(dir)

    # Convert string to a single-item list
    if extlist and isinstance(extlist, basestring):
        extlist = extlist.split()

    if not os.path.isdir(dir):
        dir = os.path.dirname(archive)

    files = []

    af = ArchiveFile(archive)

    log.debug("%d files in archive '%s': %r",
              len(af.namelist()), os.path.basename(archive), af.namelist())

    for f in [f for f in af.namelist()
                if af.getinfo(f).file_size > 0 and # to exclude dirs
                    (not extlist or
                     os.path.splitext(f)[1].lower() in extlist)]:

        outfile = os.path.join(dir, os.path.basename(f))

        with open(outfile, 'wb') as output:
            output.write(af.read(f))
            files.append(outfile)

    af.close()

    try:
        if not keep: os.remove(archive)
    except IOError as e:
        log.error(e)

    log.info("%d extracted files in '%s', filtered by %s\n\t%s",
             len(files), archive, extlist, print_dictlist(files))
    return files

def ArchiveFile(filename):
    """ Pseudo class (hence the Case) to wrap both rar and zip handling,
        since they both share almost identical API
        usage:  myarchive = ArchiveFile(filename)
        return: a RarFile or ZipFile instance (or None), depending on
                <filename> content
    """
    if   rarfile.is_rarfile(filename):
        return rarfile.RarFile(filename, mode='r')

    elif zipfile.is_zipfile(filename):
        return zipfile.ZipFile(filename, mode='r')

    else:
        return None

class HttpBot(object):
    """ Base class for other handling basic http tasks like requesting a page,
        download a file and cache content. Not to be used directly
    """
    def __init__(self, base_url=""):
        self._opener = urllib2.build_opener(urllib2.HTTPCookieProcessor())
        scheme, netloc, path, q, f  = urlparse.urlsplit(base_url, "http")
        if not netloc:
            netloc, _, path = path.partition('/')
        self.base_url = urlparse.urlunsplit((scheme, netloc, path, q, f))

    def get(self, url, postdata=None):
        """ Send an HTTP request, either GET (if no postdata) or POST
            Keeps session and other cookies.
            postdata is a dict with name/value pairs
            url can be absolute or relative to base_url
        """
        url = urlparse.urljoin(self.base_url, url)
        if postdata:
            return self._opener.open(url, urllib.urlencode(postdata))
        else:
            return self._opener.open(url)

    def download(self, url, dir, filename=""):
        download = self.get(url)

        # If save name is not set, use the downloaded file name
        if not filename:
            filename = download.geturl()

        # Handle dir
        dir = os.path.expanduser(dir)
        if not os.path.isdir(dir):
            os.makedirs(dir)

        # Combine dir to convert filename to a full path
        filename = os.path.join(dir, os.path.basename(filename))

        with open(filename,'wb') as f:
            f.write(download.read())

        return filename

    def cache(self, url):
        filename = os.path.join(g.globals['cache_dir'], os.path.basename(url))
        if os.path.exists(filename):
            return True
        else:
            return (self.download(url, g.globals['cache_dir']))

    def quote(self, text):
        """ Quote a text for URL usage, similar to urllib.quote_plus.
            Handles unicode and also encodes "/"
        """
        if isinstance(text, unicode):
            text = text.encode('utf-8')
        return urllib.quote_plus(text, safe=b'')

    def parse(self, url, postdata=None):
        """ Parse an URL and return an etree ElementRoot.
            Assumes UTF-8 encoding
        """
        return html.parse(self.get(url, postdata),
                          parser=html.HTMLParser(encoding='utf-8'))

class LegendasTV(HttpBot):

    def __init__(self, login=None, password=None):
        super(LegendasTV, self).__init__("http://legendas.tv/")

        self.login    = login    or g.options['login']
        self.password = password or g.options['password']

        if not (self.login and self.password):
            return

        url = "/login"
        log.info("Logging into %s as %s", self.base_url + url, self.login)

        self.get(url, {'data[User][username]': self.login,
                       'data[User][password]': self.password})

    def _searchdata(self, text, type=None, lang=None):
        """ Helper for the website's search form. Return a dict suitable for
            the get() method
        """
        return {'txtLegenda': text,
                'selTipo'   : type or 1, # Release search
                'int_idioma': lang or 1, # Brazilian Portuguese
                'btn_buscar.x': 0,
                'btn_buscar.y': 0,}

    _re_movie_text = re.compile(r"^(?P<title>.+)\ \((?P<year>\d+)\)$")

    def getMovies(self, text):
        """ Given a search text, return a list of dicts with basic movie info:
            id, title, title_br, thumb (relative url for a thumbnail image)
        """
        movies = []

        tree = json.load(self.get("/util/busca_titulo/" + self.quote(text)))

        # [{u'Filme': {u'id_filme':    u'20389',
        #              u'dsc_nome':    u'Wu long tian shi zhao ji gui',
        #              u'dsc_nome_br': u'Kung Fu Zombie',
        #              u'dsc_imagen':  u'tt199148.jpg'}},]
        for e in tree:
            item = e['Filme']
            movie = dict(
                id       = int(item['id_filme']),
                title    = item['dsc_nome'],
                title_br = item['dsc_nome_br'],
                thumb    = item['dsc_imagen'],
            )
            if movie['thumb']:
                movie['thumb'] = "/img/poster/" + movie['thumb']
                if g.options['cache']:
                    self.cache(movie['thumb'])
            movies.append(movie)

        print_debug("Titles found for '%s':\n%s" % (text,
                                                    print_dictlist(movies)))
        return movies

    def getMovieDetails(self, movie):
        return self.getMovieDetailsById(movie['id'])

    def getMovieDetailsById(self, id):
        """ Returns a dict with additional info about a movie than the ones
            provided by getMovies(), such as:
            title_br - movie title in Brazil
            genre - dict with id, genre, genre_br as defined in constants
            synopsis - a (usually lame) synopsis of the movie
        """
        url = "index.php?opcao=buscarlegenda&filme=" + str(id)
        tree = html.parse(self.get(url, self._searchdata("..")))

        #<table width="95%" border="0" cellpadding="0" cellspacing="0" bgcolor="#f2f2f2" class="filmresult">
        #<tr>
        #    <td width="115" rowspan="4" valign="top"><div align="center"><img src="thumbs/1802-87eb3781511594f8ea4123201df05f36.jpg" /></div></td>
        #    <td width="335"><div align="left"><strong>T&iacute;tulo:</strong>
        #      CSI: Miami - 1st Season
        #      <strong>(
        #      2002              )              </strong></div></td>
        #</tr>
        #<tr>
        #    <td><div align="left"><strong>Nacional:</strong>
        #      CSI: Miami - 1&ordf; Temporada            </div></td>
        #</tr>
        #<tr>
        #    <td><strong>G&ecirc;nero:</strong>              Seriado</td>
        #</tr>
        #<tr>
        #    <td><div align="left"><strong>Sinopse:</strong>
        #      Mostra o trabalho da equipe de investigadores do sul da Fl&oacute;rida que soluciona crimes atrav&eacute;s da mistura de m&eacute;todos cient&iacute;ficos, t&eacute;cnicas tradicionais, tecnologia de ponta e instinto apurado para descobrir pistas.(mais)
        #    </div></td>
        #</tr>
        #</table>
        e = tree.xpath(".//table[@class='filmresult']")[-1]
        data = e.xpath(".//text()")
        movie = dict(
            id          = id,
            title       = data[ 2].strip(),
            year        = data[ 3],
            title_br    = data[ 6].strip(),
            genre       = data[ 9].strip(),
            synopsis    = data[12].strip(),
            thumb       = e.xpath(".//img")[0].attrib['src']
        )
        movie['year'] = int(clean_string(movie['year']))

        print_debug("Details for title %s: %s" % (id, movie))
        return movie

    """ Convenience wrappers for the main getSubtitles method """

    def getSubtitlesByMovie(self, movie, type=None, lang=None, allpages=True):
        return self.getSubtitles(movie_id=movie['id'],
                                 lang=lang, allpages=allpages)

    def getSubtitlesByMovieId(self, movie_id, type=None, lang=None, allpages=True):
        return self.getSubtitles(movie_id=movie_id,
                                 lang=lang, allpages=allpages)

    def getSubtitlesByText(self, text, type=None, lang=None, allpages=True):
        return self.getSubtitles(text=text, type=type,
                                 lang=lang, allpages=allpages)

    _re_sub_language = re.compile(r"idioma/\w+_(\w+)\.")
    _re_sub_text = re.compile(r"""gpop\(.*
        #'(?P<title>.*)',
        #'(?P<title_br>.*)',
        '(?P<release>.*)',
        '(?P<cds>.*)',
        '(?P<fps>.*)',
        '(?P<size>\d+)MB',
        '(?P<downloads>.*)',.*
        src=\\'(?P<flag>[^']+)\\'.*,
        '(?P<date>.*)'\)\).*
        abredown\('(?P<hash>\w+)'\).*
        abreinfousuario\((?P<user_id>\d+)\)""",
        re.VERBOSE + re.DOTALL)

    def getSubtitles(self, text="", type=None, lang=None, movie_id=None,
                       allpages=True):
        """ Main method for searching, parsing and retrieving subtitles info.
            Arguments:
            text - the text to search for
            type - The type of search that text refers to. An int as defined
                   in constans representing either Release, Title or User
            lang - The subtitle language to search for. An int as defined
                   in constants
            movie_id - search all subtitles from the specified movie. If used,
                       text and type (but not lang) are ignored
            Either text or movie_id must be provided
            Return a list of dictionaries with the subtitles found. Some info
            is related to the movie, not to that particular subtitle
        """
        subtitles = []

        url = "/util/carrega_legendas_busca"
        if movie_id:  url += "/id_filme:"  + str(movie_id)
        else:         url += "/termo:"     + self.quote(text.strip())
        if type:      url += "/sel_tipo:"  + type
        if lang:      url += "/id_idioma:" + str(lang)

        page = 0
        lastpage = False
        while not lastpage:
            page += 1
            log.debug("loading %s", url)
            tree = self.parse(url)

            # <div class="">
            #     <span class="number number_2">35</span>
            #     <div class="f_left">
            #         <p><a href="/download/c0c4d6418a3474b2fb4e9dae3f797bd4/Gattaca/gattaca_dvdrip_divx61_ac3_sailfish">gattaca_dvdrip_divx61_ac3_(sailfish)</a></p>
            #         <p class="data">1210 downloads, nota 10, enviado por <a href="/usuario/SuperEly">SuperEly</a> em 02/11/2006 - 16:13 </p>
            #     </div>
            #     <img src="/img/idioma/icon_brazil.png" alt="Portugu&#195;&#170;s-BR" title="Portugu&#195;&#170;s-BR">
            # </div>
            for e in tree.xpath(".//article/div"):
                data = e.xpath(".//text()")
                dataurl = e.xpath(".//a")[0].attrib['href'].split('/')
                dataline = data[2].split(' ')
                sub = dict(
                    hash        = dataurl[2],
                    title       = dataurl[3],
                    downloads   = dataline[0],
                    rating      = dataline[3][:-1] or None,
                    date        = data[4].strip()[3:],
                    user_name   = data[3],
                    release     = data[1],
                    pack        = e.attrib['class'] == 'pack',
                    highlight   = e.attrib['class'] == 'destaque',
                    flag        = e.xpath("./img")[0].attrib['src']
                )
                fields_to_int(sub, 'downloads', 'rating')
                sub['language'] = re.search(self._re_sub_language,
                                            sub['flag']).group(1)
                sub['date'] = datetime.strptime(sub['date'], '%d/%m/%Y - %H:%M')
                if sub['release'].startswith("(p)") and sub['pack']:
                    sub['release'] = sub['release'][3:]

                if g.options['cache']: self.cache(sub['flag'])
                subtitles.append(sub)

            # Page control
            if not allpages:
                lastpage = True
            else:
                next = tree.xpath("//a[@class='load_more']")
                if next:
                    url = next[0].attrib['href']
                else:
                    lastpage = True

        print_debug("Subtitles found for %s:\n%s" %
                   ( movie_id or "'%s'" % text, print_dictlist(subtitles)))
        return subtitles

    def getSubtitleDetails(self, hash):
        """ Returns a dict with additional info about a subtitle than the ones
            provided by getSubtitles(), such as:
            imdb_url, description (html), updates (list), votes
            As with getSubtitles(), some info are related to the movie, not to
            that particular subtitle
        """
        sub = {}
        tree = html.parse(self.get('info.php?d=' + hash))

        sub['imdb_url'] = tree.xpath("//a[@class='titulofilme']")
        if len(sub['imdb_url']):
            sub['imdb_url'] = sub['imdb_url'][0].attrib['href']

        sub['synopsis'] = " ".join(
            [t.strip() for t in tree.xpath("//span[@class='sinopse']//text()")])

        sub['description'] = tree.xpath("//div[@id='descricao']")
        if sub['description']:
            sub['description'] = sub['description'][0].text + \
                                 "".join([html.tostring(l)
                                          for l in sub['description'][0]]) + \
                                 sub['description'][0].tail.strip()

        def info_from_list(datalist, text):
            return "".join([d for d in datalist
                            if d.strip().startswith(text)]
                           ).split(text)[-1].strip()

        data = [t.strip() for t in tree.xpath("//table//text()") if t.strip()]
        sub.update(re.search(self._re_movie_text, data[0]).groupdict())
        sub.update(dict(
            title       = data[data.index("Título Original:") + 1],
            title_br    = data[data.index("Título Nacional:") + 1],
            release     = data[data.index("Rls:") + 1],
            language    = data[data.index("Idioma:") + 1],
            fps         = data[data.index("FPS:") + 1],
            cds         = data[data.index("CDs:") + 1],
            size        = data[data.index("Tamanho:") + 1][:-2],
            downloads   = data[data.index("Downloads:") + 1],
            comments    = data[data.index("Comentários:") + 1],
            rating      = info_from_list(data, "Nota:").split("/")[0].strip(),
            votes       = info_from_list(data, "Votos:"),
            user_name   = info_from_list(data, "Enviada por:"),
            date        = info_from_list(data, "Em:"),
            id          = info_from_list(data, "idl =")[:-1],
        ))
        sub['date'] = datetime.strptime(sub['date'], '%d/%m/%Y - %H:%M')

        fields_to_int(sub, 'id', 'year', 'downloads', 'comments', 'cds', 'fps',
                           'size', 'votes')

        print_debug("Details for subtitle '%s': %s" % (hash, sub))
        return sub

    def downloadSubtitle(self, hash, dir, basename=""):
        """ Download a subtitle archive based on subtitle id.
            Saves the archive as dir/basename, using the basename provided or,
            if empty, the one returned from the website.
            Return the filename (with full path) of the downloaded archive
        """
        print_debug("Downloading archive for subtitle '%s'" % hash)
        result = self.download('/downloadarquivo/' + hash, dir, basename)
        print_debug("Archive saved as '%s'" % (result))
        return result

    def rankSubtitles(self, movie, subtitles):
        """ Evaluates each subtitle based on wanted movie and give each a score.
            Return the list sorted by score, greatest first
        """

        def days(d):
            return (datetime.today() - d).days

        oldest = days(min([s['date'] for s in subtitles]))
        newest = days(max([s['date'] for s in subtitles]))

        for sub in subtitles:
            score = 0

            score += 10 * get_similarity(clean_string(movie['title']),
                                         clean_string(sub['title']))
            score +=  3 * 1 if sub['highlight'] else 0
            score +=  5 * get_similarity(movie['release'],
                                         clean_string(sub['release']))
            score +=  1 * (sub['rating']/10 if sub['rating'] is not None else 0.8)
            score +=  1 * (1 - ( (days(sub['date'])-newest)/(oldest-newest)
                                 if oldest != newest
                                 else 0 ))

            sub['score'] = 10 * score / 20

        result = sorted(subtitles, key=operator.itemgetter('score'),
                        reverse=True)
        print_debug("Ranked subtitles for %s:\n%s" % (movie,
                                                      print_dictlist(result)))
        return result

def retrieve_subtitle_for_movie(usermovie, login=None, password=None,
                                legendastv=None):
    """ Main function to find, download, extract and match a subtitle for a
        selected file
    """

    # Log in
    if not legendastv:
        notify("Logging in Legendas.TV", icon=g.globals['appicon'])
        legendastv = LegendasTV(login, password)

    usermovie = os.path.abspath(usermovie)
    print_debug("Target: %s" % usermovie)
    savedir = os.path.dirname(usermovie)
    dirname = os.path.basename(savedir)
    filename = os.path.splitext(os.path.basename(usermovie))[0]

    # Which string we use first for searches? Dirname or Filename?
    # If they are similar, take the dir. If not, take the longest
    if (get_similarity(dirname, filename) > g.options['similarity'] or
        len(dirname) > len(filename)):
        search = dirname
    else:
        search = filename

    # Now let's play with that string and try to get some useful info
    movie = guess_movie_info(search)
    movie.update({'episode': '', 'season': '', 'type': '' })

    # Try to tell movie from episode
    _re_season_episode = re.compile(r"S(?P<season>\d\d?)E(?P<episode>\d\d?)",
                                    re.IGNORECASE)
    data_obj = re.search(_re_season_episode, filename) # always use filename
    if data_obj:
        data = data_obj.groupdict()
        movie['type']    = 'episode'
        movie['season']  = data['season']
        movie['episode'] = data['episode']
        movie['title']   = movie['title'][:data_obj.start()]

    # Get more useful info from OpenSubtitles.org
    osdb_movies = []
    try:
        osdb_movies = opensubtitles.videoinfo(usermovie)
    except:
        pass

    print_debug("%d OpenSubtitles found:\n%s" %
                (len(osdb_movies), print_dictlist(osdb_movies)))

    # Filter results
    osdb_movies = [m for m in osdb_movies
                   if m['MovieKind'] != 'tv series' and
                   (not movie['type'] or m['MovieKind']==movie['type'])]

    if len(osdb_movies) > 0:
        for m in osdb_movies:
            m['search'] = "%s %s" % (m['MovieName'], m['MovieYear'])

        osdb_movie = choose_best_by_key("%s %s" % (movie['title'],
                                                   movie['year']),
                                        osdb_movies,
                                        'search')['best']

        # For episodes, extract only the series name
        if (osdb_movie['MovieKind'] == 'episode' and
            osdb_movie['MovieName'].startswith('"')):
            osdb_movie['MovieName'] = osdb_movie['MovieName'].split('"')[1]

        movie['title']   = osdb_movie['MovieName']
        movie['year']    = osdb_movie['MovieYear']
        movie['type']    = movie['type']    or osdb_movie['MovieKind']
        movie['season']  = movie['season']  or osdb_movie['SeriesSeason']
        movie['episode'] = movie['episode'] or osdb_movie['SeriesEpisode']

    def season_to_ord(season):
        season = int(season)
        if   season == 1: tag = "st"
        elif season == 2: tag = "nd"
        elif season == 3: tag = "rd"
        else            : tag = "th"
        return "%d%s" % (season, tag)

    # Remove special chars that LegendasTV diskiles
    movie['title'] = movie['title'].replace("'","")

    if movie['type'] == "episode":
        movie['title'] = "%s %s Season" % (movie['title'],
                                           season_to_ord(movie['season']))

    # Let's begin with a movie search
    if movie['type'] == 'episode':
        notify("Searching for '%s - Episode %d'" % (movie['title'],
                                                    int(movie['episode'])),
               icon=g.globals['appicon'])
    else:
        notify("Searching for '%s'" % movie['title'],
               icon=g.globals['appicon'])

    movies = legendastv.getMovies(movie['title'])

    if len(movies) > 0:
        # Nice! Lets pick the best movie...
        notify("%s titles found" % len(movies))
        for m in movies:
            # Add a helper field: cleaned-up title
            m['search'] = clean_string(m['title'])

        # May the Force be with... the most similar!
        result = choose_best_by_key(clean_string(movie['title']), movies, 'search')

        # But... Is it really similar?
        if result['similarity'] > g.options['similarity']:
            movie.update(result['best'])

            if movie['type'] == 'episode':
                notify("Searching '%s' (%s) - Episode %d" %
                       (result['best']['title'],
                        result['best']['year'],
                        int(movie['episode']),),
                       icon=os.path.join(g.globals['cache_dir'],
                                         os.path.basename(result['best']['thumb'])))
            else:
                notify("Searching title '%s'" % (result['best']['title']),
                       icon=os.path.join(g.globals['cache_dir'],
                                         os.path.basename(result['best']['thumb'])))

            subs = legendastv.getSubtitlesByMovie(movie)

        else:
            # Almost giving up... forget movie matching
            notify("None was similar enough. Trying release...")
            subs = legendastv.getSubtitlesByText("%s %s" %
                                                 (movie['title'],
                                                  movie.get('year',"")))

    else:
        # Ok, let's try by release...
        notify("No titles found. Trying release...")
        subs = legendastv.getSubtitlesByText(movie['release'])

    if len(subs) > 0:

        # Good! Lets choose and download the best subtitle...
        notify("%s subtitles found" % len(subs))

        # For TV Series, exclude the ones that don't match our Episode
        if movie['type'] == 'episode':
            episodes = []
            for sub in subs:
                data_obj = re.search(_re_season_episode, sub['release'])
                if data_obj:
                    data = data_obj.groupdict()
                    if int(data['episode']) == int(movie['episode']):
                        episodes.append(sub)
            subs = episodes
        # FIXME: There may have no sobtitles for this episode, list empty
        # FIXME: Glee 4th Season
        subtitles = legendastv.rankSubtitles(movie, subs)

        # UI suggestion: present the user with a single subtitle, and the
        # following message:
        # "This is the best subtitle match we've found, how about it?"
        # And 3 options:
        # - "Yes, perfect, you nailed it! Download it for me"
        # - "This is nice, but not there yet. Let's see what else you've found"
        #   (show a list of the other subtitles found)
        # - "Eww, not even close! Let's try other search options"
        #   (show the search options used, let user edit them, and retry)

        notify("Downloading '%s' from '%s'" % (subtitles[0]['release'],
                                               subtitles[0]['user_name']))
        archive = legendastv.downloadSubtitle(subtitles[0]['hash'], savedir)
        files = extract_archive(archive, savedir, [".srt"])
        if len(files) > 1:
            # Damn those multi-file archives!
            notify("%s subtitles in archive" % len(files))

            # Build a new list suitable for comparing
            files = [dict(compare=clean_string(os.path.basename(
                                               os.path.splitext(f)[0])),
                          original=f)
                     for f in files]

            # Should we use file or dir as a reference?
            dirname_compare  = clean_string(dirname)
            filename_compare = clean_string(filename)
            if get_similarity(dirname_compare , files[0]['compare']) > \
               get_similarity(filename_compare, files[0]['compare']):
                result = choose_best_by_key(dirname_compare,
                                            files, 'compare')
            else:
                result = choose_best_by_key(filename_compare,
                                            files, 'compare')

            file = result['best']
            files.remove(file) # remove the chosen from list
            [os.remove(f['original']) for f in files] # delete the list
            file = result['best']['original'] # convert back to string
        else:
            file = files[0] # so much easier...

        newname = os.path.join(savedir, filename) + ".srt"
        #notify("Matching '%s'" % os.path.basename(file)) # enough notifications
        os.rename(file, newname)
        notify("DONE! Oba Rê!!")
        return True

    else:
        # Are you *sure* this movie exists? Try our interactive mode
        # and search for yourself. I swear I tried...
        notify("No subtitles found")
        return False
