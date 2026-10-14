import urllib.error
from unittest import mock

import pytest
from nomadpy import UnexpectedResponseError

from ansible_collections.benemon.nomad.plugins.module_utils import nomad as module_utils


def failing_module():
    module = mock.MagicMock()
    module.fail_json.side_effect = SystemExit
    return module


def test_unexpected_response_fails_with_status_and_body():
    module = failing_module()
    with pytest.raises(SystemExit):
        with module_utils.nomad_errors(module):
            raise UnexpectedResponseError(403, body="Permission denied")
    kwargs = module.fail_json.call_args.kwargs
    assert kwargs["status_code"] == 403 and "Permission denied" in kwargs["msg"]


def test_unreachable_server_names_the_reason_only():
    module = failing_module()
    with pytest.raises(SystemExit):
        with module_utils.nomad_errors(module):
            raise urllib.error.URLError("Connection refused")
    assert module.fail_json.call_args.kwargs["msg"] == "cannot reach Nomad: Connection refused"


def test_value_error_is_the_message():
    module = failing_module()
    with pytest.raises(SystemExit):
        with module_utils.nomad_errors(module):
            raise ValueError("missing policy name")
    assert module.fail_json.call_args.kwargs["msg"] == "missing policy name"


def test_options_lay_over_the_environment(monkeypatch):
    monkeypatch.setenv("NOMAD_ADDR", "http://env:4646")
    monkeypatch.setenv("NOMAD_TOKEN", "env-token")
    with mock.patch.object(module_utils.nomadpy, "Client") as cls:
        module_utils.client_from_options(dict(address="http://option:4646", namespace="web", skip_verify=True, token=None))
    config = cls.call_args.args[0]
    assert config.address == "http://option:4646" and config.secret_id == "env-token" and config.namespace == "web"
    assert config.tls_config.insecure is True
