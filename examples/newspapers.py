# coding: utf-8
# pylint: disable=F0401,E1101
#
#  Copyright 2015 by Leipzig University Library, http://ub.uni-leipzig.de
#                 by The Finc Authors, http://finc.info
#                 by Martin Czygan, <martin.czygan@uni-leipzig.de>
#
# This file is part of some open source application.
#
# Some open source application is free software: you can redistribute
# it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
#
# Some open source application is distributed in the hope that it will
# be useful, but WITHOUT ANY WARRANTY; without even the implied warranty
# of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Foobar.  If not, see <http://www.gnu.org/licenses/>.
#
# @license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
#

"""
Example of a small pipeline that downloads a couple of newspaper frontpages,
creates a newline delimited json and indexes it into elasticsearch (version 1.0+).
"""

import hashlib
import json
import tempfile

import elasticsearch
import luigi
from gluish import BaseTask, Executable, daily, random_string, shellout

NEWSPAPERS = (
    'http://bild.de/',
    'http://faz.net/',
    'http://spiegel.de/',
    'http://sueddeutsche.de/',
    'http://www.fr-online.de/',
    'http://www.lvz-online.de/',
    'http://www.nzz.ch/',
)


class FrontpageTask(BaseTask):
    """ Just a base class for out newspaper example. """
    BASE = tempfile.gettempdir()
    TAG = 'frontpage'


class DownloadPage(FrontpageTask):
    """
    Download a frontpage.
    """
    date = luigi.DateParameter(default=daily())
    url = luigi.Parameter()

    def requires(self):
        """ Outsource the download. """
        return Executable(name='wget')

    def run(self):
        """ Just run wget quietly. """
        output = shellout('wget -q "{url}" -O {output}', url=self.url)
        luigi.LocalTarget(output).move(self.output().path)

    def output(self):
        """ Use the digest version, since URL can be ugly. """
        return luigi.LocalTarget(path=self.path(digest=True, ext='html'))


class JsonPage(FrontpageTask):
    """ Convert the page to Json, adding some metadata. """
    date = luigi.DateParameter(default=daily())
    url = luigi.Parameter()

    def requires(self):
        """ Page needs to be already there. """
        return DownloadPage(date=self.date, url=self.url)

    def run(self):
        """ Construct the document id from the date and the url. """
        document = {}
        document['_id'] = hashlib.sha1('%s:%s' % (
                                       self.date, self.url)).hexdigest()
        with self.input().open() as handle:
            document['content'] = handle.read().decode('utf-8', 'ignore')
        document['url'] = self.url
        document['date'] = unicode(self.date)
        with self.output().open('w') as output:
            output.write(json.dumps(document))

    def output(self):
        """ Output a file with a single Json doc. """
        return luigi.LocalTarget(path=self.path(digest=True, ext='json'))


class IndexPage(FrontpageTask):
    """ Index the Json document into an ES index. """
    date = luigi.DateParameter(default=daily())
    url = luigi.Parameter()

    doc_type = 'page'
    index = 'frontpage'

    def requires(self):
        """ We need the Json. """
        return JsonPage(date=self.date, url=self.url)

    def run(self):
        """ Index the document. Since ids are predictable,
            we won't index anything twice. """
        with self.input().open() as handle:
            body = json.loads(handle.read())
        es = elasticsearch.Elasticsearch()
        id = body.get('_id')
        es.index(index='frontpage', doc_type='html', id=id, body=body)

    def complete(self):
        """ Check, if out hashed date:url id is already in the index. """
        id = hashlib.sha1('%s:%s' % (self.date, self.url)).hexdigest()
        es = elasticsearch.Elasticsearch()
        try:
            es.get(index='frontpage', doc_type='html', id=id)
        except elasticsearch.NotFoundError:
            return False
        return True

# Wrapper tasks
# =============

class DailyDownload(FrontpageTask, luigi.WrapperTask):
    """ Wraps a couple of downloads, so they can be parallelized. """
    date = luigi.DateParameter(default=daily())

    def requires(self):
        """ Download all pages. """
        for url in NEWSPAPERS:
            yield DownloadPage(url=url)

    def output(self):
        """ This is just a wrapper task. """
        return self.input()


class DailyIndex(FrontpageTask, luigi.WrapperTask):
    """ Wraps a couple of downloads, so they can be parallelized. """
    date = luigi.DateParameter(default=daily())
    indicator = luigi.Parameter(default=random_string())

    def requires(self):
        """ Index all pages. """
        for url in NEWSPAPERS:
            yield IndexPage(url=url, date=self.date)

    def output(self):
        """ This is just a wrapper task. """
        return self.input()


if __name__ == '__main__':
    luigi.run()
