============
Contributing
============

Please note that this project is released with a `Contributor Code of Conduct
<https://ephemeris.readthedocs.org/en/latest/conduct.html>`__. By participating
in this project you agree to abide by its terms.

Contributions are welcome, and they are greatly appreciated! Every
little bit helps, and credit will always be given.

You can contribute in many ways:

Types of Contributions
----------------------

Report Bugs
~~~~~~~~~~~

Report bugs at https://github.com/galaxyproject/ephemeris/issues.

If you are reporting a bug, please include:

* Your operating system name and version, versions of other relevant software
  such as Galaxy.
* Any details about your local setup that might be helpful in troubleshooting.
* Detailed steps to reproduce the bug.

Fix Bugs
~~~~~~~~

Look through the GitHub issues for bugs. Anything tagged with "bug"
is open to whoever wants to implement it.

Implement Features
~~~~~~~~~~~~~~~~~~

Look through the GitHub issues for features. Anything tagged with
"enhancement" is open to whoever wants to implement it.

Write Documentation
~~~~~~~~~~~~~~~~~~~

Ephemeris could always use more documentation, whether as part of the
official Ephemeris docs, in docstrings, or even on the web in blog posts,
articles, and such.

User documentation
+++++++++++++++++++
User documentation is (partly) automated to contain the first docstring in a
module and the usage based on the parser object.

If you want to contribute to the user documentation you can edit the docstring or the parser module
or write more information in the commands .rst file. (See galaxy-wait for an example.)

When you add a new command line tool in ephemeris you can add documentation as follows:

1. Go to the source file and:

  * Add a docstring that gives general information about the module. (Examples in shed-install and run-data-managers)
  * Create a new _parser() method that returns the argument parser.

2. Create a new rst file using shed-install.rst or run-data-managers.rst as a template.
3. Reference the new rst file in commands.rst

To build your documentation to check out how it works before submitting the pull request:
1. Install sphinx in a virtual environment by running `pip install -r docs/requirements.txt` from ephemeris root
2. go to the docs directory and run `make html`

Submit Feedback
~~~~~~~~~~~~~~~

The best way to send feedback is to file an issue at https://github.com/galaxyproject/ephemeris/issues.

If you are proposing a feature:

* Explain in detail how it would work.
* Keep the scope as narrow as possible, to make it easier to implement.
* This will hopefully become a community-driven project and contributions
  are welcome :)

Get Started!
------------

Ready to contribute? Here's how to set up `ephemeris` for local development.

1. Fork the `ephemeris` repo on GitHub.
2. Clone your fork locally::

    $ git clone git@github.com:your_name_here/ephemeris.git

3. Install your local copy into a virtualenv. Assuming you have virtualenvwrapper installed, this is how you set up your fork for local development::

    $ make setup-venv

4. Create a branch for local development::

    $ git checkout -b name-of-your-bugfix-or-feature

   Now you can make your changes locally.

5. When you're done making changes, check that your changes pass ``flake8``
   and the tests

   ::

       $ make lint

6. Commit your changes and push your branch to GitHub::

    $ git add .
    $ git commit -m "Your detailed description of your changes."
    $ git push origin name-of-your-bugfix-or-feature

7. Submit a pull request through the GitHub website.

Pull Request Guidelines
-----------------------

Before you submit a pull request, check that it meets these guidelines:

1. If the pull request adds functionality, the docs should be updated. Put
   your new functionality into a function with a docstring.
2. The pull request should work for Python 2.7. Check
   https://travis-ci.org/galaxyproject/ephemeris/pull_requests
   and make sure that the tests pass for all supported Python versions.

.. _Tox: https://tox.readthedocs.org/en/latest/
.. _nose: https://nose.readthedocs.org/en/latest/
