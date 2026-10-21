Consume-tool-installation-requests
==================================

.. automodule :: ephemeris.tool_request_consumer

Usage
----------

.. argparse::
   :module: ephemeris.tool_request_consumer
   :func: _parser
   :prog: consume-tool-installation-requests

Running it on a schedule
------------------------

Galaxy sends tool installation requests to its admins when
``enable_tool_installation_request_form`` and ``enable_notification_system``
are both enabled. Give the job an admin account of its own, in Galaxy's
``admin_users``, with tool installation requests turned on in its notification
preferences. Galaxy tracks what each account has seen, so admins can still
read requests in Galaxy. The account only gets requests sent after it was made
an admin, so handle earlier ones by hand.

A scheduled job in your tool list repository can open a pull request with the
requests that pin their tools, and tell those requesters where it is. For
example, in GitHub Actions, with ``EPHEMERIS_GALAXY``, ``EPHEMERIS_API_KEY``
and ``GH_TOKEN`` set::

    consume-tool-installation-requests emit --pin-latest > requests.json
    git switch -c "tool-requests-$(date +%s)"
    added=$(consume-tool-installation-requests render-yaml --tools-file requested_tools.yaml -o requested_tools.yaml < requests.json)
    if [ -n "$added" ]; then
        git add requested_tools.yaml
        git commit -m "Install requested tools"
        git push origin HEAD
        url=$(gh pr create --fill)
        consume-tool-installation-requests mark-seen $added
        consume-tool-installation-requests reply --url "$url" $added
    fi
    others=$(jq -r '.[].notification_id' requests.json | grep -vxF "$added" || true)
    [ -z "$others" ] || consume-tool-installation-requests mark-seen $others

``--pin-latest`` pins tools requested without a version to their newest
installable revision, so that those requests get a pull request too. A typed
tool name can match a repository other than the one the user meant, so check
the repositories in each pull request before merging it.

``render-yaml -o`` prints the requests whose tools it added. They get the pull
request, and one notification tells all their requesters. The job marks the
other requests seen too, so that it does not look them up again; admins find
them in their own notifications, which they can also get by email in their
notification preferences. If the reply fails, the requesters are not
told about the pull request, but the job does not open it twice.

The job needs the ``contents: write`` and ``pull-requests: write``
permissions, a git user name and email, and "Allow GitHub Actions to create
and approve pull requests" in the repository's settings. Pull requests opened
with the default ``GITHUB_TOKEN`` do not start other workflows, and GitHub
turns off scheduled workflows in public repositories after 60 days without
activity.

Once the tools are installed, for example by ``shed-tools install --tools-file
requested_tools.yaml`` after the merge, ``installed`` prints the requests whose
tools Galaxy has loaded, in the requested versions. Keep ``requests.json`` for
this, for example as a workflow artifact, and tell those requesters once::

    consume-tool-installation-requests installed < requests.json | xargs -r consume-tool-installation-requests reply --state installed

``render-yaml`` leaves a tool list that gains nothing as it is, and rewrites
one that gains tools without its comments. A tool list it starts asks
``shed-tools`` to install the tools' dependencies, which it otherwise does
not; add ``install_repository_dependencies: true`` and
``install_resolver_dependencies: true`` to an existing one.

Tools are only looked up on the Tool Shed given with ``--tool-shed-url``, so a
workflow that needs tools from another Tool Shed becomes an issue item. While
the Tool Shed fails, ``emit`` leaves requests for the next run. Work items
leave out the requester's email address.
