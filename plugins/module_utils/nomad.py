from __future__ import annotations

import contextlib
import dataclasses
import traceback
import types
import typing
import urllib.error

from ansible.module_utils.basic import missing_required_lib

try:
    import nomadpy
    from nomadpy import UnexpectedResponseError
    from nomadpy.models import Model
except ImportError:
    HAS_NOMADPY = False
    NOMADPY_IMPORT_ERROR = traceback.format_exc()
else:
    HAS_NOMADPY = True
    NOMADPY_IMPORT_ERROR = None

NOMAD_ARGUMENT_SPEC = dict(
    address=dict(type="str"),
    token=dict(type="str", no_log=True),
    region=dict(type="str"),
    ca_cert=dict(type="path"),
    ca_path=dict(type="path"),
    client_cert=dict(type="path"),
    client_key=dict(type="path"),
    tls_server_name=dict(type="str"),
    skip_verify=dict(type="bool"),
)

NOMAD_NAMESPACE_ARGUMENT_SPEC = dict(
    namespace=dict(type="str"),
)


def nomad_client(module):
    if not HAS_NOMADPY:
        module.fail_json(msg=missing_required_lib("nomadpy"), exception=NOMADPY_IMPORT_ERROR)
    return client_from_options(module.params)


def client_from_options(options):
    """client_from_options builds a client from the NOMAD_* environment with the set connection options laid over it."""
    config = nomadpy.default_config()
    if options.get("address"):
        config.address = options["address"]
    if options.get("token"):
        config.secret_id = options["token"]
    if options.get("region"):
        config.region = options["region"]
    if options.get("namespace"):
        config.namespace = options["namespace"]
    tls = config.tls_config
    for name in ("ca_cert", "ca_path", "client_cert", "client_key", "tls_server_name"):
        if options.get(name):
            setattr(tls, name, options[name])
    if options.get("skip_verify") is not None:
        tls.insecure = options["skip_verify"]
    return nomadpy.Client(config)


@contextlib.contextmanager
def nomad_errors(module):
    """nomad_errors turns a failed request into fail_json."""
    try:
        yield
    except UnexpectedResponseError as e:
        module.fail_json(msg=str(e), status_code=e.status_code)
    except urllib.error.URLError as e:
        module.fail_json(msg="cannot reach Nomad: %s" % e.reason)
    except ValueError as e:
        module.fail_json(msg=str(e))


def read_or_none(call):
    """read_or_none returns the result of a nomadpy info call, or None when the server answers 404."""
    try:
        return call()[0]
    except UnexpectedResponseError as e:
        if e.status_code == 404:
            return None
        raise


def _model_from_options(cls, options):
    """_model_from_options builds a nomadpy model from snake_case options; None options keep the model default."""
    hints = typing.get_type_hints(cls)
    kwargs = {}
    for f in dataclasses.fields(cls):
        value = options.get(f.name)
        if value is not None:
            kwargs[f.name] = _convert(hints[f.name], value)
    return cls(**kwargs)


def _convert(hint, value):
    origin = typing.get_origin(hint)
    if origin in (typing.Union, types.UnionType):
        return _convert(next(a for a in typing.get_args(hint) if a is not types.NoneType), value)
    if origin is list:
        return [_convert(typing.get_args(hint)[0], v) for v in value]
    if isinstance(hint, type) and issubclass(hint, Model) and isinstance(value, dict):
        return _model_from_options(hint, value)
    return value


def apply_options(current, cls, options):
    """apply_options returns current with every option that was set laid over it, or a new model when current is None."""
    desired = _model_from_options(cls, options)
    if current is None:
        return desired
    return dataclasses.replace(current, **{k: getattr(desired, k) for k, v in options.items() if v is not None})


def differs(current, wanted):
    """differs compares two models as Nomad stores them: an unset field and an empty one are the same thing."""
    return _trim(current.to_json()) != _trim(wanted.to_json())


def _trim(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            v = _trim(v)
            if v not in (None, "", {}, []):
                out[k] = v
        return out
    if isinstance(value, list):
        return [_trim(v) for v in value]
    return value
