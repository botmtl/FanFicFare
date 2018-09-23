# -*- coding: utf-8 -*-

# Copyright 2013 Fanficdownloader team, 2017 FanFicFare team
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from __future__ import absolute_import
import time
import logging

logger = logging.getLogger(__name__)
import re
import urllib2
import urlparse
from datetime import datetime
from .. import exceptions as exceptions
from .base_adapter import BaseSiteAdapter

class NiftyOrgAdapter(BaseSiteAdapter):
    def __init__(self, config, url):
        BaseSiteAdapter.__init__(self, config, url)
        self.story.setMetadata('siteabbrev', 'nifty')
        self._setURL(url)
        self.decode = ['Windows-1252', 'utf8', 'iso-8859-1']

    def use_pagecache(self):
        return True
    
    @staticmethod
    def getSiteDomain():
        return 'www.nifty.org'

    @classmethod
    def getAcceptDomains(cls):
        return ['www.nifty.org']

    @classmethod
    def getSiteExampleURLs(cls):
        return 'http://www.nifty.org/nifty/genre/category/multi-part-story/ http://www.nifty.org/nifty/genre/category/story-title'

    def getSiteURLPattern(self):
        return ur'https?:\/\/\www\.nifty.org\/nifty\/(?P<genre>[a-zA-Z0-9_-]+)\/(?P<category>[a-zA-Z0-9_-]+)\/(?P<title>[a-zA-Z0-9_-]+)\/?'

    def extractChapterUrlsAndMetadata(self):
        self.story.setMetadata('genre', self.validateURL().group('genre'))
        self.story.setMetadata('category', self.validateURL().group('category'))
        title = self.validateURL().group('title').replace('-', ' ').replace('.html', '').title()
        self.story.setMetadata('title', title)

        if not (self.is_adult or self.getConfig('is_adult')):
            raise exceptions.AdultCheckRequired(self.url)
        try:
            data1,opened = self._fetchUrlOpened(self.url, usecache=False)
            #Headers contain real last updated date
            self.story.setMetadata('dateUpdated', self.parseLongDate(opened.headers['last-modified']))
        except urllib2.HTTPError as e:
            if e.code == 404:
                raise exceptions.StoryDoesNotExist(self.url)
            else:
                raise e

        #check endswith('/') on opened rather than self.url because opened.url will have been
        #redirected to the proper url (ending in /) if it is a multi-chapter story
        if opened.url.endswith('/'):
            self.getMedatadataForMultipleChapterStory(data1)
        else:
            #SINGLE PAGE STORY
            self.chapterUrls = [(self.story.getMetadata('title'), self.url)]
            self.story.setMetadata('datePublished', self.parseLongDate(opened.headers['last-modified']))
            self.findAuthorInStoryText(data1)

        self.story.setMetadata('numChapters', len(self.chapterUrls))
        logger.debug('Story: <%s>', self.story)
        return

    #90% of the site stories are formatted like an email, and have a FROM: line.
    def findAuthorInStoryText(self, text):
        author = 'Unknown'
        match = re.search(ur'From:(?P<author>.*)', text)
        if match is not None:
            author = match.group('author')
        else:
            soup = self.make_soup(text)
            author = soup.find('meta', {'name':'author'})
            if author is not None:
                author = author['content']
            else:
                author = soup.find('a', email=True)
                if author is not None:
                    author = author['email']
                else:
                    match = re.search(ur'(?P<author>[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)',text)
                    if match:
                        author = match.group('author')
                    else:
                        author = re.search(ur'<a.*?>(?P<author>|.*)</a>',text)
                        if author is not None:
                            author = author.group('author')

        self.story.setMetadata('author', author)
        return

    def getMedatadataForMultipleChapterStory(self, data1):
        soup1 = self.make_soup(data1)
        chapterTable = soup1.select('td > a')
        chapterUrl=None
        for page in  reversed(chapterTable):
            chapterTitle = page.text.replace('-', ' ').replace('.html','').title()
            chapterUrl = urlparse.urljoin(self.url, page['href'])
            # insert at pos 0 to have proper order
            self.add_chapter(title=chapterTitle, url=self.normalize_chapterurl(chapterUrl))

        #self.opener.open(url.replace(' ', '%20'), None, float(self.getConfig('connect_timeout', 30.0)))
        data1, opened = self._fetchUrlOpened(chapterUrl, usecache=False)
        self.story.setMetadata('datePublished', self.parseLongDate(opened.headers['last-modified']))
        self.findAuthorInStoryText(data1)
        return

    def getChapterText(self, url):
        logger.debug('Getting chapter text from: %s' % url)
        try:
            page = self._fetchUrl(url, usecache=True)
            if '</html>' in page:
                storyText = self.make_soup(page).prettify()
            else:
                page = re.sub(r"\r\n|\r|\n", '\n', page, 0, re.DOTALL | re.IGNORECASE)
                page = re.sub(r'^Date\: (.*?)\n\s*From\: (.*)\n\s*Subject\: (.*?)\n', 'Date: $1<br>From: $2<br>Subject: $3<br><br><br>', page, 1, re.DOTALL | re.IGNORECASE)
                page = re.sub(r'\s*\n\s*\n\s*', '<br><br>', page, 0, re.DOTALL | re.IGNORECASE)
                page = re.sub(r'\n\s+', '<br><br>', page, 0, re.DOTALL | re.IGNORECASE)
                page = re.sub(r'\.\n', '.<br><br>', page, 0, re.DOTALL | re.IGNORECASE)
                page = re.sub(r'\n*\s*', '<br><br>', page, 0, re.DOTALL | re.IGNORECASE)
                page = re.sub(r'\n', '<br><br>', page, 0, re.DOTALL | re.IGNORECASE)
                page = re.sub(r'!', '.', page, 0, re.DOTALL | re.IGNORECASE)
                storyText = '<!DOCTYPE html><html><head><title>{0}</title><meta author="{1}"></head><body>{2}</body></html>'.format(self.metadata.title, self.metadata.author, page)

                storyText = self.make_soup(storyText).prettify()
        except:
            from ..exceptions import FailedToDownload
            raise exceptions.FailedToDownload("Error downloading chapter at url {0}! Only html and plain text is supported.".format(url))

        return self.utf8FromSoup(url,storyText)

    #makedate from baseadapter can't handle 'Sat, 06 May 2017 01:14:25 GMT'
    @staticmethod
    def parseLongDate(date):
        from email.utils import parsedate
        preparseddate = parsedate(date)
        return datetime(preparseddate[0], preparseddate[1], preparseddate[2])

def getClass():
    return NiftyOrgAdapter
