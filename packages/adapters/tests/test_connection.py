"""Connection configuration — IDI-195 D2 and D3.

The two tests carrying the decisions are
:func:`test_one_tool_one_tenant_two_products_two_credentials` (D3, the whole point) and
:func:`test_there_is_no_tool_level_credential_to_fall_back_to` (D3, the failure mode —
QUILL silently acquiring AXO's permissions).
"""

from __future__ import annotations

import json

import pytest

from pil_adapters import (
    Access,
    ConnectionNotConfiguredError,
    ConnectionProvider,
    CredentialHandle,
    FileConnectionProvider,
    SecretStore,
    StaticConnectionProvider,
    ToolConnection,
)

AXO_FLEET = {
    "tool": "fleet",
    "tenant_id": "tenant-acme",
    "product": "axo",
    "endpoint": "https://fleet.example.com",
    "credential": {"store": "vault", "name": "axo/fleet/acme", "access": "read_write"},
    "options": {"per_page": 100},
}

QUILL_FLEET = {
    "tool": "fleet",
    "tenant_id": "tenant-acme",
    "product": "quill",
    "endpoint": "https://fleet.example.com",
    "credential": {"store": "vault", "name": "quill/fleet/acme", "access": "read_only"},
}


def write_config(tmp_path, *entries):
    path = tmp_path / "connections.json"
    path.write_text(json.dumps({"connections": list(entries)}), encoding="utf-8")
    return path


# ----------------------------------------------------------------------------------
# D3 · Credentials are per product, not per tool
# ----------------------------------------------------------------------------------


def test_one_tool_one_tenant_two_products_two_credentials(tmp_path):
    """The requirement, stated directly.

    "QUILL read-only; AXO with permission to make changes." Same tool, same tenant, same
    endpoint, different credential and different access.
    """
    provider = FileConnectionProvider(write_config(tmp_path, AXO_FLEET, QUILL_FLEET))

    axo = provider.connection_for("fleet", "tenant-acme", "axo")
    quill = provider.connection_for("fleet", "tenant-acme", "quill")

    assert axo.credential.name != quill.credential.name
    assert axo.credential.access is Access.READ_WRITE
    assert quill.credential.access is Access.READ_ONLY
    assert axo.credential.can_write
    assert not quill.credential.can_write
    assert quill.read_only


def test_there_is_no_tool_level_credential_to_fall_back_to(tmp_path):
    """The failure D3 exists to prevent.

    If a lookup for an unconfigured product fell back to a tool-level credential, QUILL
    would silently acquire AXO's write access — nothing would break, and nobody would
    notice. So a missing product entry is an error, not an inheritance.
    """
    provider = FileConnectionProvider(write_config(tmp_path, AXO_FLEET))

    with pytest.raises(ConnectionNotConfiguredError, match="per product, not per tool"):
        provider.connection_for("fleet", "tenant-acme", "quill")


def test_product_is_a_required_argument():
    """Making it optional would immediately produce a per-tool lookup.

    Asserted on the interface rather than an implementation, because the interface is what
    a future provider has to satisfy.
    """
    import inspect

    parameters = inspect.signature(ConnectionProvider.connection_for).parameters
    assert set(parameters) == {"self", "tool", "tenant_id", "product"}
    for name in ("tool", "tenant_id", "product"):
        assert parameters[name].default is inspect.Parameter.empty


def test_the_error_says_what_is_configured_for_that_tool(tmp_path):
    """The common mistake is the right tool and tenant under the wrong product name."""
    provider = FileConnectionProvider(write_config(tmp_path, AXO_FLEET))

    with pytest.raises(ConnectionNotConfiguredError) as caught:
        provider.connection_for("fleet", "tenant-acme", "vigil")

    message = str(caught.value)
    assert "vigil" in message
    assert "axo" in message, "should list what exists for this tool"


# ----------------------------------------------------------------------------------
# D2 · Obtained through an interface, never from a product
# ----------------------------------------------------------------------------------


def test_a_connection_carries_no_product_object():
    """The property D2 protects.

    An adapter handed a ToolConnection cannot reach back into a product even by accident:
    there is no session, no database handle, no config object on it. Asserted on the field
    set so that adding one is a deliberate, visible act.
    """
    fields = set(ToolConnection.__dataclass_fields__)
    assert fields == {"tool", "tenant_id", "product", "endpoint", "credential", "options"}

    forbidden = {"session", "db", "database", "config", "app", "engine", "client"}
    assert not fields & forbidden


def test_the_provider_is_an_interface_not_a_concrete_reader():
    """D2 asks for an interface. A single concrete class would not be one."""
    import inspect

    assert inspect.isabstract(ConnectionProvider)
    with pytest.raises(TypeError):
        ConnectionProvider()  # type: ignore[abstract]


def test_static_provider_satisfies_the_interface():
    """Ships with PIL so AXO and QUILL do not each write their own fake and drift."""
    connection = ToolConnection(
        tool="fleet",
        tenant_id="tenant-acme",
        product="axo",
        endpoint="https://fleet.example.com",
        credential=CredentialHandle(SecretStore.ENVIRONMENT, "FLEET_KEY"),
    )
    provider = StaticConnectionProvider({("fleet", "tenant-acme", "axo"): connection})

    assert isinstance(provider, ConnectionProvider)
    assert provider.connection_for("fleet", "tenant-acme", "axo") is connection
    assert provider.has_connection("fleet", "tenant-acme", "axo")
    assert not provider.has_connection("fleet", "tenant-acme", "quill")


# ----------------------------------------------------------------------------------
# I-8 · Secrets are handles, never values
# ----------------------------------------------------------------------------------


def test_a_credential_value_in_configuration_is_rejected(tmp_path):
    """Configuration holds a reference. A value there is the defect I-8 names."""
    bad = {**AXO_FLEET, "credential": {"store": "vault", "name": "x", "value": "hunter2"}}
    with pytest.raises(ValueError, match="handles, never values"):
        FileConnectionProvider(write_config(tmp_path, bad))


@pytest.mark.parametrize(
    "name",
    [
        "-----BEGIN RSA PRIVATE KEY-----",
        "x" * 257,
        "line-one\nline-two",
    ],
)
def test_a_handle_that_looks_like_a_value_is_rejected(name):
    """Not foolproof, and not meant to be.

    But everything downstream treats a handle as safe to log, so a PEM body or a long
    token in this field is worth failing loudly on.
    """
    with pytest.raises(ValueError, match="looks like a secret value"):
        CredentialHandle(SecretStore.VAULT, name)


def test_a_handle_is_safe_to_log():
    """The repr must make it obvious nothing sensitive is present.

    Handles end up in log lines by design — that is the point of I-8 — so the repr is part
    of the contract rather than a convenience.
    """
    handle = CredentialHandle(SecretStore.VAULT, "axo/fleet/acme", Access.READ_WRITE)
    rendered = repr(handle)
    assert "axo/fleet/acme" in rendered
    assert "vault" in rendered
    assert "read_write" in rendered


def test_a_blank_handle_name_is_rejected():
    with pytest.raises(ValueError, match="name is required"):
        CredentialHandle(SecretStore.VAULT, "  ")


def test_access_defaults_to_read_only():
    """The safe default. A credential that can change things should have to say so."""
    assert CredentialHandle(SecretStore.VAULT, "x").access is Access.READ_ONLY
    assert not CredentialHandle(SecretStore.VAULT, "x").can_write


# ----------------------------------------------------------------------------------
# The file implementation
# ----------------------------------------------------------------------------------


def test_options_are_carried_through(tmp_path):
    provider = FileConnectionProvider(write_config(tmp_path, AXO_FLEET))
    assert provider.connection_for("fleet", "tenant-acme", "axo").options == {"per_page": 100}


def test_a_duplicate_key_is_rejected(tmp_path):
    """Keeping the last silently would let a duplicated block replace read-only with
    read-write, and which won would depend on file order."""
    with pytest.raises(ValueError, match="duplicate connection"):
        FileConnectionProvider(write_config(tmp_path, AXO_FLEET, AXO_FLEET))


def test_a_missing_file_says_what_to_do(tmp_path):
    with pytest.raises(FileNotFoundError, match="StaticConnectionProvider in tests"):
        FileConnectionProvider(tmp_path / "absent.json")


def test_invalid_json_is_reported_with_the_path(tmp_path):
    path = tmp_path / "connections.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        FileConnectionProvider(path)


def test_an_unknown_secret_store_is_rejected(tmp_path):
    """I-6: adding a store is an ADR, because a handle is only resolvable if the resolver
    knows which store to ask."""
    bad = {**AXO_FLEET, "credential": {"store": "post-it-note", "name": "x"}}
    with pytest.raises(ValueError, match="unknown secret store"):
        FileConnectionProvider(write_config(tmp_path, bad))


@pytest.mark.parametrize("product", ["AXO", "axo!", "", "1axo", "axo axo"])
def test_a_malformed_product_name_is_rejected(tmp_path, product):
    """Product names reach secret paths and log lines, so they stay boring."""
    with pytest.raises(ValueError, match="must be lowercase alphanumeric"):
        FileConnectionProvider(write_config(tmp_path, {**AXO_FLEET, "product": product}))


@pytest.mark.parametrize("missing", ["tool", "tenant_id", "endpoint"])
def test_required_fields_are_required(tmp_path, missing):
    with pytest.raises(ValueError, match=f"{missing} is required"):
        FileConnectionProvider(write_config(tmp_path, {**AXO_FLEET, missing: ""}))


def test_connections_must_be_an_array(tmp_path):
    path = tmp_path / "connections.json"
    path.write_text(json.dumps({"connections": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="'connections' array"):
        FileConnectionProvider(path)


# ----------------------------------------------------------------------------------
# Phase A scope
# ----------------------------------------------------------------------------------


def test_nothing_here_resolves_a_secret_value():
    """Phase A translates and nothing more, so no code path needs the value yet.

    A resolver arriving in this module would mean PIL had grown a connect surface without
    an ADR, which is on CLAUDE.md's stop-and-ask list.
    """
    from pil_adapters import connection

    for name in dir(connection):
        assert "resolve_secret" not in name
        assert "fetch_secret" not in name
