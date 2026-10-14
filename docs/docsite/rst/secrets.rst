.. _ansible_collections.benemon.nomad.docsite.secrets:

Secrets
=======

Two resources carry secret material: the items of a
`Nomad variable <https://developer.hashicorp.com/nomad/docs/concepts/variables>`_
and the secret of an `ACL token <https://developer.hashicorp.com/nomad/docs/secure/acl>`_.
This page states where each one appears in a play's output.

Variables
---------

:ansopt:`benemon.nomad.nomad_variable#module:items` is marked ``no_log``, so a
value supplied through it is shown as ``VALUE_SPECIFIED_IN_NO_LOG_PARAMETER``
wherever it appears in the task's output, including inside the returned
:ansretval:`benemon.nomad.nomad_variable#module:variable`. The registered
result holds the placeholder, so a value written by one task is read back
through the lookup or the ``_info`` module.

The diff never carries a value. Each item in ``before`` and ``after`` is
replaced by ``sha256:`` and the first twelve hex digits of the SHA-256 of the
value, so ``--diff`` shows which items were added, removed or changed without
showing what they hold.

.. code-block:: text

   --- before
   +++ after
   @@ -2,5 +2,5 @@
      "Items": {
   -    "password": "sha256:2bb80d537b1d",
   +    "password": "sha256:5e884898da28",
        "username": "sha256:8d969eef6eca"
      },

:ansplugin:`benemon.nomad.nomad_variable_info#module` returns the items of one
variable when :ansopt:`benemon.nomad.nomad_variable_info#module:path` is set,
and metadata stubs without items when listing. A registered result of a read by
path holds the values and is not masked, so treat such a task as it would be
treated with any other secret in a registered variable.

The lookup
----------

:ansplugin:`benemon.nomad.nomad_variable#lookup` reads a variable inline, at
the point of use, without a registered result or a fact that holds the value
afterwards.

.. code-block:: yaml

   - name: Read every item of a variable
     ansible.builtin.debug:
       msg: "{{ lookup('benemon.nomad.nomad_variable', 'db/credentials', namespace='web') }}"

   - name: Read one item
     ansible.builtin.template:
       src: app.env.j2
       dest: /etc/app.env
     vars:
       db_password: "{{ lookup('benemon.nomad.nomad_variable', 'db/credentials', key='password', namespace='web') }}"

A variable that does not exist is an error, as is a
:ansopt:`benemon.nomad.nomad_variable#lookup:key` the variable does not hold.
The lookup takes the same connection options as the modules as keyword
arguments and falls back to the same environment variables; it does not see
``module_defaults``.

ACL tokens
----------

The Nomad API returns a token's ``SecretID`` in every full token document.
:ansplugin:`benemon.nomad.nomad_acl_token#module` returns it once: the
:ansretval:`benemon.nomad.nomad_acl_token#module:token` of the task that creates
a token carries ``SecretID``, and every other result, including an unchanged
run against the same token and every result of
:ansplugin:`benemon.nomad.nomad_acl_token_info#module`, leaves it out.

Register the creating task and set ``no_log`` on it to capture the secret
without printing it:

.. code-block:: yaml

   - name: Create a client token and keep its secret out of the log
     benemon.nomad.nomad_acl_token:
       name: ci-reader
       type: client
       policies: [read-default]
       expiration_ttl: 24h
     register: token
     no_log: true

   - name: Store the secret where the consumer reads it
     benemon.nomad.nomad_variable:
       path: ci/reader-token
       items:
         secret: "{{ token.token.SecretID }}"
     when: token is changed

On a later run the token already exists, the task reports no change and
``token.token`` has no ``SecretID``; the ``when`` above keeps the second task
from writing an undefined value.
