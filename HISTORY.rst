.. :changelog:

History
-------

.. to_doc

---------------------
0.10.10 (2024-02-01)
---------------------

* Use None default value where items are optional (thanks to `@mvdbeek`_).
  `Pull Request 212`_

---------------------
0.10.9 (2024-01-31)
---------------------

* Fix CI tests (thanks to `@mvdbeek`_). `Pull Request 208`_
* Add black, ruff, isort and mypy (thanks to `@mvdbeek`_). `Pull Request 209`_
* Add now mandatory readthedocs config file (thanks to `@nsoranzo`_). `Pull
  Request 210`_
* Enhancements to the IDC scripts (thanks to `@jmchilton`_). `Pull Request
  201`_

---------------------
0.10.8 (2023-04-18)
---------------------

* Prefer dashes instead of underscores in flags (thanks to `@natefoo`_). `Pull
  Request 191`_
* Remove folder id from get_folders function call in setup-data-libraries
  (thanks to `@sanjaysrikakulam`_). `Pull Request 196`_
* Standardize CLI commands on - instead of _ (thanks to `@hexylena`_). `Pull
  Request 195`_
* Add partial type annotations (thanks to `@mvdbeek`_). `Pull Request 193`_
* Rename configuration option removed in tox 4.0 (thanks to `@nsoranzo`_).
  `Pull Request 190`_
* Set Library Permissions (thanks to `@mira-miracoli`_). `Pull Request 187`_
* delete the extra random sleep lines from sleep.py (thanks to `@cat-bro`_).
  `Pull Request 171`_

---------------------
0.10.7 (2021-06-08)
---------------------

* Add option to `shed-tools test` for specifying a history name (thanks to
  `@natefoo`_). `Pull Request 173`_
* workflow-to-tools: get tools from subworkflows (thanks to `@cat-bro`_).
  `Pull Request 170`_
* Add pysam and continue if test fetching errors (thanks to `@mvdbeek`_).
  `Pull Request 128`_
* Various updates to testing and CI infrastructure (thanks to `@jmchilton`_).
  `Pull Request 165`_
* Handle terminal states in wait for install (thanks to `@mvdbeek`_).
  `Pull Request 161`_
* Get all tools when searching for tool ids for testing
  (thanks to `@cat-bro`_). `Pull Request 159`_

---------------------
0.10.6 (2020-05-04)
---------------------

* Wait for the correct repository (thanks to `@mvdbeek`_). `Pull
  Request 158`_
* Update dependencies

---------------------
0.10.5 (2020-02-29)
---------------------

* Fix `shed-tools test -t workflow_tools.yml` (thanks to `@nsoranzo`_). `Pull
  Request 155`_
* Fix installing tool dependencies from yaml list (thanks to `@mvdbeek`_).
  `Pull Request 154`_
* Cast exceptions to string using unicodify (thanks to `@mvdbeek`_). `Pull
  Request 150`_
* Add description when creating folders with setup_data_libraries (thanks to
  `@abretaud`_). `Pull Request 149`_

---------------------
0.10.4 (2019-10-05)
---------------------

* When polling for repo install status, ensure the correct revision is being
  checked (thanks to `@natefoo`_). `Pull Request 146`_
* Add install_tool_deps command (thanks to `@innovate-invent`_). `Pull Request
  145`_

---------------------
0.10.3 (2019-07-18)
---------------------

* Add install-tool-deps command that will install tool dependencies
  (thanks to `@innovate-invent`_). `Pull Request 130`_
* Require galaxy-tool-util instead of galaxy-lib (thanks to `@nsoranzo`_).
  `Pull Request 143`_
* Release to PyPI on tag (thanks to `@mvdbeek`_). `Pull Request 142`_
* Make Data library creation more robust
  (thanks to `@erasche`_). `Pull Request 138`_
* Make tool testing more robust (thanks to
  `@mvdbeek`_). `Pull Request 137`_, `Pull Request 136`_

---------------------
0.10.2 (2019-06-04)
---------------------

* Fix default message check (thanks to `@mvdbeek`_). `Pull Request 135`_

---------------------
0.10.1 (2019-06-04)
---------------------

* Fix timeout handling when installing repositories
  (thanks to `@mvdbeek`_). `Pull Request 134`_

---------------------
0.10.0 (2019-05-29)
---------------------

* fix doc building and regenerate (thanks to `@martenson`_). `Pull Request
  129`_
* fix default for 'parallel_tests' typo (thanks to `@martenson`_). `Pull
  Request 127`_
* Include some additional stats for xunit reporting (thanks to `@mvdbeek`_).
  `Pull Request 126`_
* Handle timeout gracefully for UWSGI connection (thanks to `@pcm32`_). `Pull
  Request 123`_
* Update Docs for User Name (Should be Email) (thanks to `@rdvelazquez`_).
  `Pull Request 122`_
* remove the python invocation from usage examples (thanks to `@martenson`_).
  `Pull Request 121`_
* Fix crash when too_with_panel is empty (thanks to `@jvanbraekel`_). `Pull
  Request 120`_
* Test tools in parallel, with regular user permissions, without a shared
  filesystem (thanks to `@mvdbeek`_). `Pull Request 118`_
* use latest documentation dependencies to fix documentation build issue
  (thanks to `@rhpvorderman`_). `Pull Request 114`_
* Refactor shed tool functionality. Removed deprecated options from 
  shed-tools CLI. 
  shed-tools update now also accepts tool list, so tools in galaxy can 
  be selectively updated. Improved algorithm leads to much faster 
  skipping of already installed tools, which makes the installation 
  of tools much faster on an already populated galaxy.
  (thanks to `@rhpvorderman`_).
  `Pull Request 104`_
* Add ``pytest``, enable coverage testing (thanks to `@rhpvorderman`_).
  `Pull Request 105`_
* Make ``setup_data_libraries.py`` check for existence before recreation of
  libraries.
  (thanks to `@Slugger70`_).
  `Pull Request 103`_
* Catch failures on requests to the installed repo list when doing post-
  timeout spinning on installation in ``shed-tools`` (thanks to `@natefoo`_).
  `Pull Request 97`_
* Fix coverage reporting on codacy (thanks to `@rhpvorderman`_).
  `Pull Request 106`_
* Run-data-managers now outputs stderr of failed jobs (thanks to `@rhpvorderman`_).
  `Pull Request 110`_

---------------------
0.9.0 (2018-05-23)
---------------------

* Update data managers when updating tools (thanks to `@rhpvorderman`_).
  `Pull Request 78`_, `Issue 69`_
* Run data managers aggressive parallelization and refactoring (thanks to
  `@rhpvorderman`_).
  `Pull Request 79`_
* Makes publishing of imported workflows available (thanks to `@pcm32`_).
  `Pull Request 74`_
* Add option to test tools on update/install for Galaxy 18.05 (thanks to `@jmchilton`_).
  `Pull Request 81`_
* Upload 2.0 support for data library creation (thanks to `@jmchilton`_).
  `Pull Request 89`_
* Fixes to revision parsing in tools.yaml (thanks to `@bgruening`_).
  `Pull Request 70`_
* Add Codacy monitoring and badge (thanks to `@jmchilton`_).
  `Pull Request 73`_
* Fix typo in project organization document (thanks to `@blankenberg`_).
  `Pull Request 86`_
* Fix hardcoded log paths (thanks to `@rhpvorderman`_).
  `Pull Request 85`_
* Fix ``shed-tools`` update argparse handling (thanks to `@rhpvorderman`_).
  `Pull Request 88`_
* Fix a few lint issues (thanks to `@jmchilton`_).
  `Pull Request 90`_

---------------------
0.8.0 (2017-12-29)
---------------------

* Many new documentation enhancements (thanks to @rhpvorderman, and others)
* rename of shed-install to shed-tools and add a new --latest and --revision argument (thanks to @rhpvorderman)
* many fixes and new tests by (thanks to @mvdbeek)
* Parallelization of run-data-managers (thanks to @rhpvorderman)
* run-data-managers now uses more advanced templating for less repetitive input yamls (thanks to @rhpvorderman)
* run-data-managers now checks if a genome index is already present before running the data manager (thanks to @rhpvorderman)
* ephemeris will now use https by default instead of http (thanks to @bgruening)

---------------------
0.7.0 (2017-06-27)
---------------------

* Many new documentation enhancements (thanks to @rhpvorderman, @erasche, and others) -
  docs are now published to https://readthedocs.org/projects/ephemeris/.
* Fix problem with empty list options related to running data managers (thanks to @rhpvorderman).
* Enable data managers to run with API keys (thanks to @rhpvorderman).
* Add sleep command to wait for a Galaxy API to become available (thanks to @erasche).
* Preserve readable order of keys while processing tool lists (thanks to @drosofff).

---------------------
0.6.1 (2017-04-17)
---------------------

* Add Python 2 and 3 testing for all scripts against galaxy-docker-stable along with various
  refactoring to reduce code duplication and Python 3 fixes. `#36
  <https://github.com/galaxyproject/ephemeris/pull/36>`__

---------------------
0.6.0 (2017-04-10)
---------------------

* Add new connection options for setting up data libraries.

---------------------
0.5.1 (2017-04-07)
---------------------

* Fix new ``run-data-managers`` CLI entrypoint.

---------------------
0.5.0 (2017-04-06)
---------------------

* Add ``run-data-managers`` tool to trigger DM with multiple values and in order. `#30 <https://github.com/galaxyproject/ephemeris/pull/30>`_
* The workflow install tool now supports a directory of workflows. `#27 <https://github.com/galaxyproject/ephemeris/pull/27>`_
* enable global options in a tool yaml files, like `install_resolver_dependencies: true` `#26 <https://github.com/galaxyproject/ephemeris/pull/26>`_
* Mention mimum required galaxy versions. `#23 <https://github.com/galaxyproject/ephemeris/pull/23>`_ (thanks to @mvdbeek)
    

---------------------
0.4.0 (2016-09-07)
---------------------

* Be more generic in determining a server time-out (thanks to @afgane).
* Get tool list entrypoint and improvements (thanks to @mvdbeek).
* Rename ``tool_panel_section_name`` to ``tool_panel_section_label`` like
  ansible-galaxy-tools (thanks to @nturaga).
* Add missing file ``tool_list.yaml.sample`` (thanks to @nturaga).

---------------------
0.3.0 (2016-08-26)
---------------------

* More robust shed-install script, install dependencies by default, improve logging
  (thanks to @mvdbeek).

---------------------
0.2.0 (2016-08-15)
---------------------

* Add tool generate a tool list from a Galaxy workflow file
  (thanks to @drosofff).
* Fix various code quality issues including adding beta support
  for Python 3 (thanks in part to @mvdbeek).

---------------------
0.1.0 (2016-06-15)
---------------------

* Setup project, pull in scripts from `ansible-galaxy-tools
  <https://github.com/galaxyproject/ansible-galaxy-tools>`__
  and adapt them for usage as a library.

.. github_links
.. _Pull Request 212: https://github.com/galaxyproject/ephemeris/pull/212
.. _Pull Request 208: https://github.com/galaxyproject/ephemeris/pull/208
.. _Pull Request 209: https://github.com/galaxyproject/ephemeris/pull/209
.. _Pull Request 210: https://github.com/galaxyproject/ephemeris/pull/210
.. _Pull Request 201: https://github.com/galaxyproject/ephemeris/pull/201
.. _Pull Request 191: https://github.com/galaxyproject/ephemeris/pull/191
.. _Pull Request 196: https://github.com/galaxyproject/ephemeris/pull/196
.. _Pull Request 195: https://github.com/galaxyproject/ephemeris/pull/195
.. _Pull Request 193: https://github.com/galaxyproject/ephemeris/pull/193
.. _Pull Request 190: https://github.com/galaxyproject/ephemeris/pull/190
.. _Pull Request 187: https://github.com/galaxyproject/ephemeris/pull/187
.. _Pull Request 171: https://github.com/galaxyproject/ephemeris/pull/171
.. _Pull Request 173: https://github.com/galaxyproject/ephemeris/pull/173
.. _Pull Request 170: https://github.com/galaxyproject/ephemeris/pull/170
.. _Pull Request 128: https://github.com/galaxyproject/ephemeris/pull/128
.. _Pull Request 165: https://github.com/galaxyproject/ephemeris/pull/165
.. _Pull Request 161: https://github.com/galaxyproject/ephemeris/pull/161
.. _Pull Request 159: https://github.com/galaxyproject/ephemeris/pull/159
.. _Pull Request 158: https://github.com/galaxyproject/ephemeris/pull/158
.. _Pull Request 155: https://github.com/galaxyproject/ephemeris/pull/155
.. _Pull Request 154: https://github.com/galaxyproject/ephemeris/pull/154
.. _Pull Request 150: https://github.com/galaxyproject/ephemeris/pull/150
.. _Pull Request 149: https://github.com/galaxyproject/ephemeris/pull/149
.. _Pull Request 146: https://github.com/galaxyproject/ephemeris/pull/146
.. _Pull Request 145: https://github.com/galaxyproject/ephemeris/pull/145
.. _Pull Request 130: https://github.com/galaxyproject/ephemeris/pull/130
.. _Pull Request 143: https://github.com/galaxyproject/ephemeris/pull/143
.. _Pull Request 142: https://github.com/galaxyproject/ephemeris/pull/142
.. _Pull Request 138: https://github.com/galaxyproject/ephemeris/pull/138
.. _Pull Request 137: https://github.com/galaxyproject/ephemeris/pull/137
.. _Pull Request 136: https://github.com/galaxyproject/ephemeris/pull/136
.. _Pull Request 135: https://github.com/galaxyproject/ephemeris/pull/135
.. _Pull Request 134: https://github.com/galaxyproject/ephemeris/pull/134
.. _Pull Request 129: https://github.com/galaxyproject/ephemeris/pull/129
.. _Pull Request 127: https://github.com/galaxyproject/ephemeris/pull/127
.. _Pull Request 126: https://github.com/galaxyproject/ephemeris/pull/126
.. _Pull Request 123: https://github.com/galaxyproject/ephemeris/pull/123
.. _Pull Request 122: https://github.com/galaxyproject/ephemeris/pull/122
.. _Pull Request 121: https://github.com/galaxyproject/ephemeris/pull/121
.. _Pull Request 120: https://github.com/galaxyproject/ephemeris/pull/120
.. _Pull Request 118: https://github.com/galaxyproject/ephemeris/pull/118
.. _Pull Request 114: https://github.com/galaxyproject/ephemeris/pull/114
.. _Pull Request 97: https://github.com/galaxyproject/ephemeris/pull/97
.. _Pull Request 103: https://github.com/galaxyproject/ephemeris/pull/103
.. _Pull Request 104: https://github.com/galaxyproject/ephemeris/pull/104
.. _Pull Request 105: https://github.com/galaxyproject/ephemeris/pull/105
.. _Pull Request 106: https://github.com/galaxyproject/ephemeris/pull/106
.. _Pull Request 110: https://github.com/galaxyproject/ephemeris/pull/110
.. _Pull Request 74: https://github.com/galaxyproject/ephemeris/pull/74
.. _Issue 69: https://github.com/galaxyproject/ephemeris/issues/69
.. _Pull Request 73: https://github.com/galaxyproject/ephemeris/pull/73
.. _Pull Request 78: https://github.com/galaxyproject/ephemeris/pull/78
.. _Pull Request 70: https://github.com/galaxyproject/ephemeris/pull/70
.. _Pull Request 86: https://github.com/galaxyproject/ephemeris/pull/86
.. _Pull Request 79: https://github.com/galaxyproject/ephemeris/pull/79
.. _Pull Request 85: https://github.com/galaxyproject/ephemeris/pull/85
.. _Pull Request 81: https://github.com/galaxyproject/ephemeris/pull/81
.. _Pull Request 90: https://github.com/galaxyproject/ephemeris/pull/90
.. _Pull Request 89: https://github.com/galaxyproject/ephemeris/pull/89
.. _Pull Request 88: https://github.com/galaxyproject/ephemeris/pull/88
.. _@abretaud: https://github.com/abretaud
.. _@bgruening: https://github.com/bgruening
.. _@blankenberg: https://github.com/blankenberg
.. _@cat-bro: https://github.com/cat-bro
.. _@rhpvorderman: https://github.com/rhpvorderman
.. _@pcm32: https://github.com/pcm32
.. _@jmchilton: https://github.com/jmchilton
.. _@Slugger70: https://github.com/Slugger70
.. _@natefoo: https://github.com/natefoo
.. _@martenson: https://github.com/martenson
.. _@mvdbeek: https://github.com/mvdbeek
.. _@rdvelazquez: https://github.com/rdvelazquez
.. _@jvanbraekel: https://github.com/jvanbraekel
.. _@innovate-invent: https://github.com/innovate-invent
.. _@erasche: https://github.com/erasche
.. _@nsoranzo: https://github.com/nsoranzo
.. _@mira-miracoli: https://github.com/mira-miracoli
.. _@sanjaysrikakulam: https://github.com/sanjaysrikakulam
.. _@hexylena: https://github.com/hexylena

.. _bioblend: https://github.com/galaxyproject/bioblend/
.. _nose: https://nose.readthedocs.org/en/latest/
