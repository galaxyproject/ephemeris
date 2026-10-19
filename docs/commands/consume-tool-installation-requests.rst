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
are both enabled. ``consume-tool-installation-requests run`` runs a script that
comes with ephemeris, shown below. It checks for new requests, opens an issue
or a pull request (a merge request on GitLab) for each of them in your tool
list repository, and tells the requester where it is handled. It works with
any Galaxy server, on GitHub and GitLab, from any CI system or cron job that
runs it in a clean checkout of the repository, on the branch that pull
requests go to. The script's first lines list what it needs and the
environment variables it reads.

What pull requests change depends on how your repository lists its tools:

- Without ``TOOLS_FILE`` and ``APPLY_COMMAND``, every request becomes an issue.
- With ``TOOLS_FILE``, pull requests add the requested tools to that tool list
  with ``render-yaml``.
- With ``APPLY_COMMAND``, pull requests hold what that shell command changes.
  It runs in the checkout, on a new branch, with ``$ITEM`` naming a JSON file
  that holds the work item from ``emit``: ``notification_id``, ``action``,
  ``title``, ``body``, and ``tools``, whose tool list entries have ``name``,
  ``owner``, ``tool_shed_url``, ``tool_panel_section_label`` and
  ``revisions``. For example, a repository with a tool list per section and
  lock files could add each tool to the tool list of its section, and its
  revisions to the lock file.

If the command changes nothing, because the repository has the tools already,
the request becomes an issue.

On GitHub:

- copy the workflow below to ``.github/workflows/``,
- set ``EPHEMERIS_GALAXY`` to your Galaxy server, and ``TOOLS_FILE`` or
  ``APPLY_COMMAND`` as above,
- add the API key of an admin account as the ``GALAXY_ADMIN_API_KEY``
  repository secret,
- enable "Allow GitHub Actions to create and approve pull requests" in the
  repository's Actions settings. Otherwise requests become issues.

Workflows on pull requests opened with the default ``GITHUB_TOKEN`` only run
once someone approves them. To run your tool installation tests without that,
put a GitHub App or personal access token in ``FORGE_TOKEN`` instead. GitHub
turns off scheduled workflows in public repositories after 60 days without
activity, so turn it on again in the Actions tab if your server gets few
requests.

On GitLab:

- add the jobs below to ``.gitlab-ci.yml``,
- set ``EPHEMERIS_GALAXY``, and ``TOOLS_FILE`` or ``APPLY_COMMAND``. GitLab
  expands variables in ``variables:``, so write ``$ITEM`` as ``$$ITEM`` there,
- add the API key of an admin account as the masked ``EPHEMERIS_API_KEY``
  CI/CD variable, and a token with the ``api`` and ``write_repository`` scopes
  as the masked ``FORGE_TOKEN`` variable, since the CI job token cannot push
  branches or open issues. That is a project access token with at least the
  Developer role, or, on gitlab.com's Free tier, which has none, the personal
  access token of an account made for this,
- create a pipeline schedule, for example every hour, or every few hours on
  gitlab.com's Free tier, whose compute minutes would not last a month of
  hourly runs.

The script labels the issues and pull requests it opens with ``REQUEST_LABEL``
and finds those of earlier runs by that label, so a run that stops halfway,
for example because Galaxy limits how many notifications an account may send
per minute (``send_notification_rate_limit``), is picked up by the next one
without opening duplicates. The requester may be told twice, though: if a run
tells them but then fails to mark their request as seen, the next run tells
them again, rather than risk not telling them at all.

``EPHEMERIS_API_KEY`` must belong to an account in Galaxy's ``admin_users``
that keeps tool installation requests turned on in its notification
preferences, since Galaxy sends requests to those accounts only. To make the
script skip a request, delete it there before the script handles it.

Admins can read and mark requests in Galaxy as they like. ``emit`` picks up
unseen requests, and also requests marked as seen that arrived after the
script's first issue or pull request and have none yet, once they have been
seen for five minutes, since GitHub and GitLab list new issues with a delay.
So the script can use the account of the only admin of a small Galaxy. It
leaves alone requests read before its first issue or pull request; to handle
those too, add ``--seen-since`` with the time to start from to
``EMIT_OPTIONS``. The script marks the requests it handled as seen, and GitHub
and GitLab do not tell you about issues opened with your own token. So if the
script uses both your Galaxy account and your own token, use an account made
for this on the forge, or watch the repository's issues, to hear about new
requests. In GitHub Actions, the default ``GITHUB_TOKEN`` opens them as
``github-actions``.

Once an issue or pull request is closed, the script asks Galaxy whether it has
the requested tools in the requested versions now, and tells the requester
that they are installed, or that the request was closed without installing
them. It then adds ``ANSWERED_LABEL``. It waits for the tools of a merged pull
request to be installed, by an install job like the one below or by hand, and
gives up on those closed more than 30 days ago, without telling the requester.
For merged pull requests it gives up on, it prints a warning on every run
until you add ``ANSWERED_LABEL`` to them. So close an issue once its tools are
installed, not before.

Request pull requests all start from the same base branch, so merging one can
make others that change the same tool list conflict. Resolve those like any
conflict, or avoid them with a file per request, like Galaxy Australia's tool
list does::

    APPLY_COMMAND='mkdir -p requests && jq -s . "$ITEM" | consume-tool-installation-requests render-yaml -o "requests/$(jq -r .notification_id "$ITEM").yaml"'

Then pull requests never conflict, but also no longer become issues when the
tool list has their tools already. Install every file there, for example with
``for f in requests/*.yaml; do shed-tools install --tools-file "$f"; done``,
which skips the tools Galaxy has already.

``render-yaml`` leaves a tool list that gains nothing as it is, and rewrites
one that gains tools without its comments. A tool list it starts asks
``shed-tools`` to install the tools' dependencies, which it otherwise does
not; add ``install_repository_dependencies: true`` and
``install_resolver_dependencies: true`` to an existing one. Like
``shed-tools``, it reads an entry with neither ``revisions`` nor
``changeset_revision`` as following the latest revision, and leaves that
repository alone.

Users may ask for tools that nobody has wrapped for Galaxy yet. With
``--wrapper-request-url``, the issue for such a tool links to a prefilled
request in a tool development repository, for an admin to check and send. For
example, set ``EMIT_OPTIONS`` to one of::

    --wrapper-request-url 'https://github.com/galaxyproject/tools-iuc/issues/new?title={title}&body={body}&labels=tool%20request'
    --wrapper-request-url 'https://github.com/bgruening/galaxytools/issues/new?template=tool-request.yml&title={title}&tool-name={name}&description={description}&links={url}'

Tools are only looked up on the Tool Shed given to ``emit`` with
``--tool-shed-url``. A workflow that needs tools from another Tool Shed leads
to an issue, so that an admin decides whether to trust that Tool Shed. While
the Tool Shed fails, ``emit`` leaves requests for the next run; after a day,
they become issues anyway.

Issue and pull request bodies show what users typed into the request form as
code, so that it cannot mention people. They do not contain the requester's
email address, but what users typed is public in a public repository, so use a
private one if your users' requests should stay private.

.. literalinclude:: ../../src/ephemeris/tool_installation_requests.sh
   :language: bash

The GitHub Actions workflow:

.. literalinclude:: ../examples/tool-installation-requests.yml
   :language: yaml

The GitLab CI jobs, with the install job described below:

.. literalinclude:: ../examples/tool-installation-requests.gitlab-ci.yml
   :language: yaml

Small and private Galaxy servers
--------------------------------

Most Galaxy servers have no bot that keeps their tools up to date and installs
them. For those:

- ``EMIT_OPTIONS=--pin-latest`` makes requests without a version pull requests
  too, for an admin to review.
- The install job below installs the tool list whenever it changes on the
  default branch, for example when a request's pull request is merged. The
  next run of the script then tells the requester that the tools are installed.
- GitHub's and GitLab's own machines cannot reach a Galaxy server on a private
  network. Run the jobs on a self-hosted runner there instead, or run the script
  from cron on a machine that can reach both Galaxy and the forge, in a
  checkout of your tool list repository. Set it up once::

    python3 -m venv /srv/tool-requests/venv
    /srv/tool-requests/venv/bin/pip install ephemeris
    git clone https://github.com/org/tools /srv/tool-requests/tools

  Put the settings in a file only that user can read,
  ``/srv/tool-requests/settings``, for example::

    PATH=/srv/tool-requests/venv/bin:$PATH
    FORGE=github
    FORGE_PROJECT=org/tools
    FORGE_TOKEN=...
    EPHEMERIS_GALAXY=https://galaxy.example.org
    EPHEMERIS_API_KEY=...
    TOOLS_FILE=requested_tools.yaml
    EMIT_OPTIONS=--pin-latest

  and run it every hour from that user's crontab, on the base branch reset
  before each run, never twice at once, and for at most an hour::

    23 * * * * cd /srv/tool-requests/tools && flock -n ../lock timeout 1h sh -c 'git fetch -q && git checkout -qf -B main origin/main && git clean -qfd && set -a && . ../settings && set +a && consume-tool-installation-requests run'

Without a tool list repository, an admin can handle requests by hand: write
the pull request items to a tool list, review it, install it, and tell the
requesters::

    consume-tool-installation-requests emit --pin-latest > requests.json
    consume-tool-installation-requests render-yaml -o requested_tools.yaml < requests.json
    shed-tools install --tools-file requested_tools.yaml
    consume-tool-installation-requests reply --notification-id ID --state installed
    consume-tool-installation-requests mark-seen ID

The install job for GitHub Actions, which the GitLab example above has too:

.. literalinclude:: ../examples/install-requested-tools.yml
   :language: yaml
