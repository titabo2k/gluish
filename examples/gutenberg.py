# coding: utf-8

"""
Example of a small pipeline that downloads a Project Gutenberg dump,
extracts the index terms and builds a top list of those terms.

    $ cd gluish
    $ python ./examples/gutenberg.py GutenbergTopIndexTerms --local-scheduler

There is no quick way to see, where the files have gone, since we use
`tempfile.gettempdir()`, which varies from system to sytem. Workaround is to
use a python shell:

    $ cd examples
    $ python
    >>> import gutenberg
    >>> gutenberg.GutenbergTopIndexTerms().output().path
    u'/tmp/gutenberg/GutenbergTopIndexTerms/date-2014-03-17.tsv'

The file should look like this:

    $ head -10 /tmp/gutenberg/GutenbergTopIndexTerms/date-2014-03-17.tsv
    17419 Fiction
    6892 Juvenile fiction
    4511 History
    2526 Periodicals
    2404 United States
    2040 19th century
    1902 Great Britain
    1810 Drama
    1649 Biography
    1616 Social life and customs
"""

from gluish.common import Executable
from gluish.intervals import weekly
from gluish.shell import shellout
from gluish.task import BaseTask
from gluish.format import TSV
import tempfile
import luigi


class GutenbergTask(BaseTask):
    BASE = tempfile.gettempdir()
    TAG = 'gutenberg'


class GutenbergDump(GutenbergTask):
    """
    Download dump.

    Updated usually every four days. These lists include the basic information
    about each eBook.
    """
    date = luigi.DateParameter(default=weekly())

    def requires(self):
        return [Executable(name='wget'), Executable(name='bunzip2')]

    def run(self):
        url = "http://gutenberg.readingroo.ms/cache/generated/feeds/catalog.marc.bz2"
        output = shellout('wget -q "{url}" -O {output}', url=url)
        output = shellout('bunzip2 {input} -c > {output}', input=output)
        luigi.File(output).move(self.output().path)

    def output(self):
        return luigi.LocalTarget(path=self.path(ext='mrc'))


class GutenbergIndexTerms(GutenbergTask):
    """ Extract all 653 a index terms. """
    date = luigi.DateParameter(default=weekly())
    
    def requires(self):
        return {'dump': GutenbergDump(date=self.date),
                'apps': Executable(name='marctotsv',
                                   message='https://github.com/miku/gomarckit')}

    def run(self):
        output = shellout('marctotsv -k -s "|" {input} 001 653.a > {output}',
                 input=self.input().get('dump').path)
        with luigi.File(output, format=TSV).open() as handle:
            with self.output().open('w') as output:
                for row in handle.iter_tsv(cols=('id', 'terms')):
                    for subfield in row.terms.split('|'):
                        for term in subfield.split('--'):
                            term = term.strip()
                            output.write_tsv(row.id, term)

    def output(self):
        return luigi.LocalTarget(path=self.path(), format=TSV)


class GutenbergTopIndexTerms(GutenbergTask):
    """ Sort and count top index terms. """
    date = luigi.DateParameter(default=weekly())

    def requires(self):
        return GutenbergIndexTerms(date=self.date)

    def run(self):
        output = shellout("cut -f 2- {input}| sort | uniq -c | sort -nr > {output}",
                          input=self.input().path)
        luigi.File(output).move(self.output().path)

    def output(self):
        return luigi.LocalTarget(path=self.path(), format=TSV)


if __name__ == '__main__':
    luigi.run()
