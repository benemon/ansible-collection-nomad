"""Runs ansible-test integration once per lane against a dev agent started from the lane's binary.

Lanes follow nomadpy: NOMADPY_TEST_CE_BIN for Community, NOMADPY_TEST_ENT_BIN plus NOMAD_LICENSE_PATH for
Enterprise. A lane whose variables are unset is skipped.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from nomadpy import Client, Config

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "integration_config.yml")


def free_ports(n):
    socks = [socket.socket() for i in range(n)]
    for s in socks:
        s.bind(("127.0.0.1", 0))
    ports = [s.getsockname()[1] for s in socks]
    for s in socks:
        s.close()
    return ports


def start_agent(binary, env):
    http, rpc, serf = free_ports(3)
    workdir = tempfile.mkdtemp(prefix="nomad-collection-agent-")
    config = os.path.join(workdir, "agent.hcl")
    with open(config, "w") as f:
        f.write("ports { http = %d rpc = %d serf = %d }\nacl { enabled = true }\n" % (http, rpc, serf))
    with open(os.path.join(workdir, "agent.log"), "w") as log:
        proc = subprocess.Popen(
            [binary, "agent", "-dev", "-bind", "127.0.0.1", "-config", config, "-log-level", "ERROR"],
            stdout=log, stderr=subprocess.STDOUT, env={**os.environ, **env},
        )
    address = "http://127.0.0.1:%d" % http
    client = Client(Config(address=address))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and proc.poll() is None:
        try:
            if client.status.leader():
                return proc, address, workdir
        except Exception:
            pass
        time.sleep(0.25)
    stop_agent(proc)
    with open(os.path.join(workdir, "agent.log")) as f:
        raise RuntimeError("nomad agent did not become ready:\n" + f.read()[-2000:])


def stop_agent(proc):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def bootstrap(address):
    """Returns the management token once the keyring exists and the dev client node is ready, so jobs can be placed."""
    client = Client(Config(address=address))
    token = client.acl_tokens.bootstrap()[0]
    client.set_secret_id(token.secret_id)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        keys = client.keyring.list()[0]
        nodes = client.nodes.list()[0]
        if keys and any(n.status == "ready" for n in nodes):
            return token.secret_id
        time.sleep(0.25)
    raise RuntimeError("server keyring or client node never became ready")


def lane(name, binary, env, enterprise, extra_args):
    proc, address, workdir = start_agent(binary, env)
    try:
        token = bootstrap(address)
        with open(CONFIG, "w") as f:
            json.dump({"nomad_address": address, "nomad_token": token, "nomad_enterprise": enterprise}, f)
        print("== %s lane: %s" % (name, address), flush=True)
        # Forked Ansible workers crash on macOS the first time they touch CoreFoundation; urllib's system
        # proxy lookup does, so proxies come from the environment and Objective-C fork checks are off.
        env = {**os.environ, "no_proxy": "*", "OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES"}
        return subprocess.call(["ansible-test", "integration", "--local", *extra_args], cwd=os.path.dirname(os.path.dirname(HERE)), env=env)
    finally:
        stop_agent(proc)
        shutil.rmtree(workdir, ignore_errors=True)
        if os.path.exists(CONFIG):
            os.remove(CONFIG)


def main(argv):
    ce = os.environ.get("NOMADPY_TEST_CE_BIN")
    ent = os.environ.get("NOMADPY_TEST_ENT_BIN")
    licence = os.environ.get("NOMAD_LICENSE_PATH")
    ran = False
    status = 0
    if ce:
        ran = True
        status |= lane("Community", ce, {}, False, argv)
    if ent and licence:
        ran = True
        status |= lane("Enterprise", ent, {"NOMAD_LICENSE_PATH": licence}, True, argv)
    if not ran:
        print("no lane configured: set NOMADPY_TEST_CE_BIN and/or NOMADPY_TEST_ENT_BIN with NOMAD_LICENSE_PATH", file=sys.stderr)
        return 2
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
