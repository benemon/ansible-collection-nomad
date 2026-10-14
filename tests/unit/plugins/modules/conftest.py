from unittest import mock

import pytest
from ansible.module_utils import basic
from ansible.module_utils.testing import patch_module_args


class Exit(Exception):
    pass


class Fail(Exception):
    pass


@pytest.fixture
def run():
    """run(module, args, client) executes the module's main against a mocked client and returns the exit_json result; fail_json raises Fail."""
    def _run(module, args, client, check_mode=False):
        def exit_json(*a, **kw):
            raise Exit(kw)

        def fail_json(*a, **kw):
            raise Fail(kw)

        with patch_module_args(dict(args, _ansible_check_mode=check_mode)), \
                mock.patch.object(basic.AnsibleModule, "exit_json", exit_json), \
                mock.patch.object(basic.AnsibleModule, "fail_json", fail_json), \
                mock.patch.object(module, "nomad_client", return_value=client):
            with pytest.raises(Exit) as e:
                module.main()
        return e.value.args[0]
    return _run
