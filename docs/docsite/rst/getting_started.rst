.. _ansible_collections.benemon.nomad.docsite.getting_started:

Getting started
===============

The :anscollection:`benemon.nomad` collection manages HashiCorp Nomad and Nomad
Enterprise over the HTTP API, through the `nomadpy <https://pypi.org/project/nomadpy/>`_
client. Every plugin runs on the controller or a delegated host that can reach
the API; nothing runs on the Nomad servers themselves.

Install
-------

The collection requires ansible-core 2.19 or newer, Python 3.11 or newer and
nomadpy 0.2.0 or newer with its ``exec`` extra on the host that runs the
plugins.

.. code-block:: console

   ansible-galaxy collection install benemon.nomad
   pip install -r ~/.ansible/collections/ansible_collections/benemon/nomad/requirements.txt

Connection options
------------------

Every plugin takes the same connection options. Each one falls back to the
environment variable the `Nomad CLI <https://developer.hashicorp.com/nomad/docs/commands#environment-variables>`_
reads, with the same meaning.

.. list-table::
   :header-rows: 1

   * - Option
     - Environment variable
     - Default
   * - ``address``
     - :ansenvvar:`NOMAD_ADDR`
     - ``http://127.0.0.1:4646``
   * - ``token``
     - :ansenvvar:`NOMAD_TOKEN`
     -
   * - ``namespace``
     - :ansenvvar:`NOMAD_NAMESPACE`
     - ``default``
   * - ``region``
     - :ansenvvar:`NOMAD_REGION`
     - the region of the server answering
   * - ``ca_cert``
     - :ansenvvar:`NOMAD_CACERT`
     -
   * - ``ca_path``
     - :ansenvvar:`NOMAD_CAPATH`
     -
   * - ``client_cert``
     - :ansenvvar:`NOMAD_CLIENT_CERT`
     -
   * - ``client_key``
     - :ansenvvar:`NOMAD_CLIENT_KEY`
     -
   * - ``tls_server_name``
     - :ansenvvar:`NOMAD_TLS_SERVER_NAME`
     -
   * - ``skip_verify``
     - :ansenvvar:`NOMAD_SKIP_VERIFY`
     - ``false``

``namespace`` is present only on plugins whose resource lives in a namespace:
jobs and variables. ACL resources, namespaces, node pools, nodes, quotas and
Sentinel policies are cluster-wide.

The modules form the ``benemon.nomad.nomad`` action group, so a play can set the
connection once with ``module_defaults``:

.. code-block:: yaml

   - hosts: localhost
     module_defaults:
       group/benemon.nomad.nomad:
         address: https://nomad.example.com:4646
         token: "{{ nomad_token }}"
     tasks:
       - benemon.nomad.nomad_namespace:
           name: web
           description: Web tier

The :ansplugin:`benemon.nomad.nomad_variable#lookup` lookup, the
:ansplugin:`benemon.nomad.nomad#inventory` inventory plugin and the
:ansplugin:`benemon.nomad.nomad_exec#connection` connection plugin are outside
the action group and do not see ``module_defaults``. Pass their connection
options as keyword arguments, inventory file options or ``ansible_nomad_*``
host variables, or set the environment variables.

How the modules behave
----------------------

A state module reads the resource first and reports ``changed`` only when the
server's state differs from the options that were set. An option left out keeps
its current value on the server. A dict option that is set replaces the whole
nested structure. Check mode and diff mode are supported throughout.

Returned resources are the Nomad API documents with the API's field names, so
``result.namespace.Name`` and ``result.job.TaskGroups`` read as the
`API documentation <https://developer.hashicorp.com/nomad/api-docs>`_ describes
them.

A request the server refuses fails the task with the server's message in ``msg``
and the HTTP status in ``status_code``. See
:ref:`ansible_collections.benemon.nomad.docsite.enterprise` for the responses a
Community server gives to Enterprise requests.
