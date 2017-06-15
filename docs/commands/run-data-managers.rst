Run-data-managers
=============

.. automodule :: ephemeris.run_data_managers

Usage
----------

.. Tried to autogenerate this with code below
.. #argparse::
   :module: ephemeris.shed_install
   :func: _parse_cli_options
   :prog: shed-install

.. programoutput :: python ephemeris/run_data_managers.py --help

Example Usage
-------------

.. code-block:: shell

    $ galaxy-wait -g https://fqdn/galaxy

A verbose option is offered which prints out logging statements:

.. code-block:: shell

    $ galaxy-wait -g http://localhost:8080 -v
    [00] Galaxy not up yet... HTTPConnectionPool(host='localhost', port=8080): Max retries exceeded with url: /api/version (Caused
    [01] Galaxy not up yet... HTTPConnectionPool(host='localhost', port=8080): Max retries exceeded with url: /api/version (Caused
    [02] Galaxy not up yet... HTTPConnectionPool(host='localhost', port=8080): Max retries exceeded with url: /api/version (Caused
    [03] Galaxy not up yet... HTTPConnectionPool(host='localhost', port=8080): Max retries exceeded with url: /api/version (Caused
    [04] Galaxy not up yet... HTTPConnectionPool(host='localhost', port=8080): Max retries exceeded with url: /api/version (Caused
    [05] Galaxy not up yet... HTTPConnectionPool(host='localhost', port=8080): Max retries exceeded with url: /api/version (Caused
    Galaxy Version: 17.05

When the specified Galaxy instance is up, it exits with a code of zero
indicating success.



Notes
-----

If the host returns HTML content, or otherwise non-JSON content, the tool will exit with an error.
