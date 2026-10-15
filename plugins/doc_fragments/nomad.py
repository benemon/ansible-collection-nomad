from __future__ import annotations


class ModuleDocFragment(object):
    DOCUMENTATION = r"""
options:
  address:
    description:
      - Address of the Nomad HTTP API, including the scheme.
      - Falls back to E(NOMAD_ADDR), then V(http://127.0.0.1:4646).
    type: str
  token:
    description:
      - ACL token secret sent with every request.
      - Falls back to E(NOMAD_TOKEN).
    type: str
  region:
    description:
      - Region to send requests to.
      - Falls back to E(NOMAD_REGION), then the region of the server answering.
    type: str
  ca_cert:
    description:
      - Path to a CA certificate file to verify the server against.
      - Falls back to E(NOMAD_CACERT).
    type: path
  ca_path:
    description:
      - Path to a directory of CA certificates to verify the server against.
      - Falls back to E(NOMAD_CAPATH).
    type: path
  client_cert:
    description:
      - Path to the client certificate for TLS authentication.
      - Falls back to E(NOMAD_CLIENT_CERT).
    type: path
  client_key:
    description:
      - Path to the private key of O(client_cert).
      - Falls back to E(NOMAD_CLIENT_KEY).
    type: path
  tls_server_name:
    description:
      - Server name to verify the certificate against instead of the host in O(address).
      - Falls back to E(NOMAD_TLS_SERVER_NAME).
    type: str
  skip_verify:
    description:
      - Do not verify the server certificate.
      - Falls back to E(NOMAD_SKIP_VERIFY).
    type: bool
requirements:
  - nomadpy >= 0.2.0
notes:
  - Connection options fall back to the environment variables the Nomad CLI reads, with the same meaning.
  - Enterprise features are not checked client-side. On a Community server the request fails with the server's own error.
"""

    NAMESPACE = r"""
options:
  namespace:
    description:
      - Namespace the resource lives in.
      - Falls back to E(NOMAD_NAMESPACE), then V(default).
    type: str
"""
