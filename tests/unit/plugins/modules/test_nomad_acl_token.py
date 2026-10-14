from unittest import mock

import pytest
from nomadpy import ACLToken, ACLTokenListStub, ACLTokenRoleLink, QueryMeta, UnexpectedResponseError, WriteMeta

from ansible_collections.benemon.nomad.plugins.modules import nomad_acl_token, nomad_acl_token_info

from .conftest import Fail

HOUR = 3600 * 10**9
READERS = ACLTokenRoleLink(id="r-1", name="readers")
READER = ACLToken(accessor_id="a-1", secret_id="s-1", name="ci-reader", type="client", policies=["read-default"], roles=[READERS],
                  create_time="2026-10-14T16:07:21Z", expiration_time="2026-10-14T17:07:21Z", expiration_ttl=HOUR, create_index=5, modify_index=5)
BOOTSTRAP = ACLTokenListStub(accessor_id="a-0", name="Bootstrap Token", type="management", global_=True, create_index=1, modify_index=1)
READER_STUB = ACLTokenListStub(accessor_id="a-1", name="ci-reader", type="client", policies=["read-default"], roles=[ACLTokenRoleLink(id="r-1")],
                               create_index=5, modify_index=5)


def client(existing=None):
    c = mock.MagicMock()
    c.acl_tokens.list.return_value = ([BOOTSTRAP] + ([READER_STUB] if existing else []), QueryMeta())
    if existing is None:
        c.acl_tokens.info.side_effect = UnexpectedResponseError(404, body="ACL token not found")
    else:
        c.acl_tokens.info.return_value = (existing, QueryMeta())
    c.acl_tokens.create.return_value = (READER, WriteMeta())
    c.acl_tokens.update.return_value = (READER, WriteMeta())
    return c


def test_create(run):
    c = client()
    args = dict(name="ci-reader", type="client", policies=["read-default"], roles=["readers"], expiration_ttl="1h")
    args["global"] = True
    result = run(nomad_acl_token, args, c)
    assert result["changed"] is True
    sent = c.acl_tokens.create.call_args.args[0]
    assert sent == ACLToken(name="ci-reader", type="client", policies=["read-default"], roles=[ACLTokenRoleLink(name="readers")], global_=True,
                            expiration_ttl=HOUR)
    assert result["token"]["SecretID"] == "s-1" and result["token"]["CreateIndex"] == 5
    assert result["diff"]["before"] == {} and "SecretID" not in result["diff"]["after"]


def test_unchanged_when_set_options_match(run):
    c = client(READER)
    result = run(nomad_acl_token, dict(name="ci-reader", type="client", policies=["read-default"], roles=["readers"], expiration_ttl="1h"), c)
    assert result["changed"] is False
    c.acl_tokens.info.assert_called_once_with("a-1")
    c.acl_tokens.create.assert_not_called()
    c.acl_tokens.update.assert_not_called()
    assert "SecretID" not in result["token"]


def test_update_keeps_unset_fields(run):
    c = client(READER)
    result = run(nomad_acl_token, dict(accessor_id="a-1", policies=["read-default", "read-nodes"]), c)
    assert result["changed"] is True
    sent = c.acl_tokens.update.call_args.args[0]
    assert sent.accessor_id == "a-1" and sent.policies == ["read-default", "read-nodes"] and sent.roles == [READERS] and sent.name == "ci-reader"
    c.acl_tokens.create.assert_not_called()
    assert "SecretID" not in result["token"] and "SecretID" not in result["diff"]["before"]


def test_check_mode_writes_nothing(run):
    c = client(READER)
    result = run(nomad_acl_token, dict(name="ci-reader", policies=[]), c, check_mode=True)
    assert result["changed"] is True and result["token"]["Policies"] == []
    c.acl_tokens.update.assert_not_called()


def test_absent(run):
    c = client(READER)
    assert run(nomad_acl_token, dict(name="ci-reader", state="absent"), c)["changed"] is True
    c.acl_tokens.delete.assert_called_once_with("a-1")
    assert run(nomad_acl_token, dict(name="ci-reader", state="absent"), client())["changed"] is False
    assert run(nomad_acl_token, dict(accessor_id="a-1", state="absent"), client())["changed"] is False


def test_ambiguous_name_fails(run):
    c = client(READER)
    c.acl_tokens.list.return_value = ([READER_STUB, READER_STUB], QueryMeta())
    with pytest.raises(Fail) as e:
        run(nomad_acl_token, dict(name="ci-reader", state="absent"), c)
    assert "2 tokens are named ci-reader" in e.value.args[0]["msg"]


def test_missing_accessor_cannot_be_created(run):
    with pytest.raises(Fail) as e:
        run(nomad_acl_token, dict(accessor_id="a-9", type="client"), client())
    assert "a-9" in e.value.args[0]["msg"]


def test_server_error_fails_with_status(run):
    c = client()
    c.acl_tokens.create.side_effect = UnexpectedResponseError(400, body="ACL policy not found")
    with pytest.raises(Fail) as e:
        run(nomad_acl_token, dict(name="ci-reader", type="client", policies=["missing"]), c)
    assert e.value.args[0]["status_code"] == 400 and "ACL policy not found" in e.value.args[0]["msg"]


def test_info(run):
    c = client(READER)
    assert run(nomad_acl_token_info, dict(name="ci-reader"), c)["tokens"] == [READER_STUB.to_json()]
    assert run(nomad_acl_token_info, dict(accessor_id="a-1"), c)["tokens"] == [READER_STUB.to_json()]
    assert run(nomad_acl_token_info, dict(name="ci-reader"), client())["tokens"] == []
    assert run(nomad_acl_token_info, dict(), c)["tokens"] == [BOOTSTRAP.to_json(), READER_STUB.to_json()]
    c.acl_tokens.info.assert_not_called()
