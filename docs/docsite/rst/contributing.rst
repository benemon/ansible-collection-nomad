.. _ansible_collections.benemon.nomad.docsite.contributing:

Contributing
============

The repository is `benemon/ansible-collection-nomad <https://github.com/benemon/ansible-collection-nomad>`_.
The collection talks to Nomad through nomadpy only; a change that needs a new
API call starts in `nomadpy <https://pypi.org/project/nomadpy/>`_.

Local setup
-----------

Create ``.venv`` at the repository root with ansible-core, nomadpy and pytest on
Python 3.14, and have ``rsync`` on the path. ``ansible-test`` needs the
collection in an ``ansible_collections/benemon/nomad`` directory, so the
``Makefile`` copies the repository to one under ``$TMPDIR`` before each target.

.. code-block:: console

   make sanity
   make units
   make integration

Test lanes
----------

Integration tests start a Nomad dev agent with ACLs enabled from a binary
named explicitly, bootstrap it, and run ``ansible-test integration`` against
it. There are two lanes, and each is selected by its variables. A lane whose
variables are unset is skipped; a run with no lane set fails.

.. list-table::
   :header-rows: 1

   * - Lane
     - Variables
   * - Community
     - :ansenvvar:`NOMADPY_TEST_CE_BIN`, the path of a Community ``nomad`` binary
   * - Enterprise
     - :ansenvvar:`NOMADPY_TEST_ENT_BIN`, the path of an Enterprise ``nomad`` binary,
       and :ansenvvar:`NOMAD_LICENSE_PATH`, the path of its licence file

The targets read ``nomad_enterprise`` from the lane and assert the Community
responses listed in :ref:`ansible_collections.benemon.nomad.docsite.enterprise`
on the Community lane. A target for an Enterprise surface must pass on both.

CI runs sanity, units and integration on the oldest and newest supported
ansible-core. It downloads both editions of Nomad and runs the Enterprise lane
when the ``NOMAD_LICENCE`` repository secret is set, so a fork without the
secret runs the Community lane and stays green.

``.nomad-version`` pins the newest Nomad release for CI; a green ``main`` is
the compatibility claim for that release. The ``compat`` workflow runs daily
against what moves: it builds Nomad from upstream main for the Community lane
and takes the newest Enterprise release, which has no public source, with
nomadpy as PyPI serves it. A failure opens an issue labelled ``compat``, or
comments on the open one for the same versions. When a newer release appears
it opens a PR moving ``.nomad-version``, which needs the ``COMPAT_PR_TOKEN``
repository secret, a fine-grained token with contents and pull-requests write.

Documentation
-------------

The site is built from the ``DOCUMENTATION``, ``EXAMPLES`` and ``RETURN`` blocks
of each plugin and from the pages under ``docs/docsite/rst/``. The build fails
on malformed documentation and on a page that references an option, return
value or plugin that does not exist, so it is run on every push and pull
request. To build it locally:

.. code-block:: console

   pip install antsibull-docs
   make tree
   export ANSIBLE_COLLECTIONS_PATH=${TMPDIR:-/tmp}/benemon-nomad
   antsibull-docs sphinx-init --use-current --fail-on-error --squash-hierarchy --dest-dir /tmp/nomad-docs benemon.nomad
   pip install -r /tmp/nomad-docs/requirements.txt
   /tmp/nomad-docs/build.sh

The result is under ``/tmp/nomad-docs/build/html``.

Changelog
---------

Every user-visible change carries a fragment under ``changelogs/fragments/``,
in the `antsibull-changelog format <https://ansible.readthedocs.io/projects/antsibull-changelog/changelogs/>`_.
A new plugin carries ``version_added`` instead of a fragment and the release
step lists it from that. ``antsibull-changelog lint`` checks the fragments.

Before a release, ``antsibull-changelog release`` folds the fragments into
``changelogs/changelog.yaml`` and regenerates ``CHANGELOG.rst``; the fragments
are removed in the same step. Commit the result, then tag.

Releases
--------

A release is a tag ``v<version>`` matching ``version`` in ``galaxy.yml``. The
release workflow refuses a tag that does not match, requires a green test run
for the tagged commit, builds the collection, publishes it to Ansible Galaxy and
creates the GitHub release.
