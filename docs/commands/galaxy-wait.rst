Galaxy-wait
============

.. automodule :: ephemeris.sleep

Usage
----------

.. argparse::
   :module: ephemeris.sleep
   :func: _parser
   :prog: galaxy-wait


Galaxy URL
----------

Valid galaxy urls look like:

- https://example.com
- http://example.com/galaxy
- http://localhost:8080/gx

Do not include the trailing slash.

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

Timeout
-------

By default, the timeout value is ``0``, allowing the script to sleep
forever for a Galaxy instance to be alive. This may not be desirable
behaviour. In that case you can supply the ``--timeout`` option, and
after waiting that number of seconds, the ``galaxy-sleep`` command will
exit ``1`` if the Galaxy instance could not be contacted.


.. code-block:: shell

    $ galaxy-wait -g https://does-not-exist -v --timeout 3
    [00] Galaxy not up yet... HTTPSConnectionPool(host='does-not-exist', port=443): Max retries exceeded with url: /api/version (C
    [01] Galaxy not up yet... HTTPSConnectionPool(host='does-not-exist', port=443): Max retries exceeded with url: /api/version (C
    [02] Galaxy not up yet... HTTPSConnectionPool(host='does-not-exist', port=443): Max retries exceeded with url: /api/version (C
    [03] Galaxy not up yet... HTTPSConnectionPool(host='does-not-exist', port=443): Max retries exceeded with url: /api/version (C
    Failed to contact Galaxy))))

Notes
-----

If the host returns HTML content, or otherwise non-JSON content, the tool will exit with an error.

.. code-block:: shell

    $ galaxy-wait -g https://example.com -v --timeout 3
    Traceback (most recent call last):
    File "/home/hxr/work-freiburg/ephemeris/.venv/bin/galaxy-wait", line 11, in <module>
        load_entry_point('ephemeris', 'console_scripts', 'galaxy-wait')()
    File "/home/hxr/work-freiburg/ephemeris/ephemeris/sleep.py", line 34, in main
        result = requests.get(options.galaxy + '/api/version').json()
    File "/home/hxr/work-freiburg/ephemeris/.venv/lib/python3.5/site-packages/requests/models.py", line 886, in json
        return complexjson.loads(self.text, **kwargs)
    File "/usr/lib/python3.5/json/__init__.py", line 319, in loads
        return _default_decoder.decode(s)
    File "/usr/lib/python3.5/json/decoder.py", line 339, in decode
        obj, end = self.raw_decode(s, idx=_w(s, 0).end())
    File "/usr/lib/python3.5/json/decoder.py", line 357, in raw_decode
        raise JSONDecodeError("Expecting value", s, err.value) from None
    json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)

If this behaviour presents an issue for you, please `file a bug with ephemeris.
<https://github.com/galaxyproject/ephemeris/issues>`__
