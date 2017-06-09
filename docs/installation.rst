============
Installation
============

pip_
============

For a traditional Python installation of Ephemeris, first set up a virtualenv
for ``ephemeris`` (this example creates a new one in ``.venv``) and then
install with ``pip``.

::

    $ virtualenv .venv; . .venv/bin/activate
    $ pip install ephemeris

When installed this way, ephemeris can be upgraded as follows:

::

    $ . .venv/bin/activate
    $ pip install -U ephemeris

To install or update to the latest development branch of Ephemeris with ``pip``, 
use the  following ``pip install`` idiom instead:

::

    $ pip install -U git+git://github.com/galaxyproject/ephemeris.git


Conda_
============

Another approach for installing Ephemeris is to use Conda_
(most easily obtained via the
`Miniconda Python distribution <http://conda.pydata.org/miniconda.html>`__).
Afterwards run the following commands.

::

    $ conda config --add channels bioconda
    $ conda install ephemeris

.. _pip: https://pip.pypa.io/
.. _Conda: http://conda.pydata.org/docs/
