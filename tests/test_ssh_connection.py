import paramiko
import pytest

from wlc_role_acl_collector.hostkeys import approve_unknown_host_key
from wlc_role_acl_collector.hostkeys import HostKeyObservation, sha256_fingerprint
from wlc_role_acl_collector.ssh_connection import PinnedHostKeyPolicy, build_pinned_ssh_client


def _observation(key, *, host="192.0.2.10", port=22):
    return HostKeyObservation(
        host=host,
        port=port,
        key_type=key.get_name(),
        fingerprint=sha256_fingerprint(key.asbytes()),
        key=key,
    )


def test_pinned_policy_accepts_only_matching_key_material(tmp_path):
    known_hosts = tmp_path / "known_hosts"
    approved = paramiko.RSAKey.generate(1024)
    changed = paramiko.RSAKey.generate(1024)
    approve_unknown_host_key(_observation(approved), known_hosts_path=known_hosts)
    policy = PinnedHostKeyPolicy(known_hosts)

    policy.missing_host_key(paramiko.SSHClient(), "192.0.2.10", approved)
    with pytest.raises(paramiko.SSHException, match="달라"):
        policy.missing_host_key(paramiko.SSHClient(), "192.0.2.10", changed)
    with pytest.raises(paramiko.SSHException, match="미승인"):
        policy.missing_host_key(paramiko.SSHClient(), "192.0.2.11", approved)


def test_pinned_client_does_not_load_rsa_key_into_paramiko_priority_list(tmp_path):
    known_hosts = tmp_path / "known_hosts"
    approved = paramiko.RSAKey.generate(1024)
    approve_unknown_host_key(_observation(approved), known_hosts_path=known_hosts)

    client = build_pinned_ssh_client(known_hosts)

    assert not client.get_host_keys()
    assert isinstance(client._policy, PinnedHostKeyPolicy)
