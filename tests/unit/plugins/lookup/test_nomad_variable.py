from unittest import mock

import pytest
from ansible.errors import AnsibleError
from ansible.plugins.loader import lookup_loader
from nomadpy import QueryMeta, UnexpectedResponseError, Variable

from ansible_collections.benemon.nomad.plugins.module_utils import nomad as module_utils

CREDS = Variable(path="db/credentials", items={"username": "app", "password": "s3cret"})


def run(terms, client, **kwargs):
    with mock.patch.object(module_utils.nomadpy, "Client", return_value=client) as cls:
        result = lookup_loader.get("benemon.nomad.nomad_variable").run(terms, variables={}, **kwargs)
    return result, cls.call_args.args[0]


def test_items_and_key():
    client = mock.MagicMock()
    client.variables.peek.return_value = (CREDS, QueryMeta())
    assert run(["db/credentials"], client)[0] == [CREDS.items]
    assert run(["db/credentials", "db/credentials"], client, key="username")[0] == ["app", "app"]
    client.variables.peek.assert_called_with("db/credentials")


def test_options_build_the_client(monkeypatch):
    monkeypatch.setenv("NOMAD_ADDR", "http://env:4646")
    monkeypatch.setenv("NOMAD_TOKEN", "env-token")
    client = mock.MagicMock()
    client.variables.peek.return_value = (CREDS, QueryMeta())
    config = run(["db/credentials"], client, address="http://option:4646", namespace="web", skip_verify=True)[1]
    assert config.address == "http://option:4646" and config.secret_id == "env-token" and config.namespace == "web"
    assert config.tls_config.insecure is True


def test_missing_variable_is_an_error():
    client = mock.MagicMock()
    client.variables.peek.return_value = (None, QueryMeta())
    with pytest.raises(AnsibleError, match="db/credentials not found"):
        run(["db/credentials"], client)


def test_missing_key_is_an_error():
    client = mock.MagicMock()
    client.variables.peek.return_value = (CREDS, QueryMeta())
    with pytest.raises(AnsibleError, match="no item port"):
        run(["db/credentials"], client, key="port")


def test_server_error_carries_status_and_body():
    client = mock.MagicMock()
    client.variables.peek.side_effect = UnexpectedResponseError(403, body="Permission denied")
    with pytest.raises(AnsibleError, match="403.*Permission denied"):
        run(["db/credentials"], client)
