"""Connect's options from 1.1: protocol, credentials, websockets, TLS,
MQTT 5 sessions, reconnecting and the last will."""

import io
import ssl
import textwrap
import types

import paho.mqtt.client as mqtt
import pytest
import robot
from conftest import FakeClient, keywords, reason
from paho.mqtt.packettypes import PacketTypes
from robot.api import ExecutionResult

# Protocol


@pytest.mark.parametrize(
    "given, expected",
    [
        ("MQTTv31", mqtt.MQTTv31),
        ("mqttv311", mqtt.MQTTv311),
        (4, mqtt.MQTTv311),
        ("MQTTv5", mqtt.MQTTv5),
        (5, mqtt.MQTTv5),
    ],
)
def test_protocol_reaches_the_client(lib, fake, given, expected):
    lib.connect("broker.test", protocol=given)
    assert fake.instances[-1].kwargs["protocol"] is expected
    assert lib.get_connection_info()["protocol"] == expected.name


def test_mqtt5_leaves_clean_session_to_paho(lib, fake):
    lib.connect("broker.test", protocol="MQTTv5")
    client = fake.instances[-1]
    assert client.kwargs["clean_session"] is None
    assert client.connect_options == {}


def test_mqtt5_with_clean_session_false_points_to_clean_start(lib, fake):
    with pytest.raises(RuntimeError, match=r"^clean_session applies to MQTT 3\.1"):
        lib.connect("broker.test", client_id="me", clean_session=False, protocol=5)
    assert fake.instances == []


@pytest.mark.parametrize("option", [{"clean_start": False}, {"session_expiry": 60}])
def test_mqtt5_session_options_need_mqtt5(lib, fake, option):
    with pytest.raises(
        RuntimeError, match=r"^clean_start and session_expiry need protocol=MQTTv5\.$"
    ):
        lib.connect("broker.test", **option)


def test_clean_start_and_session_expiry_reach_connect(lib, fake):
    lib.connect(
        "broker.test", "me", protocol="MQTTv5", clean_start=False, session_expiry=300
    )
    options = fake.instances[-1].connect_options
    assert options["clean_start"] is False
    assert options["properties"].packetType == PacketTypes.CONNECT
    assert options["properties"].SessionExpiryInterval == 300


@pytest.mark.parametrize("value", [-1, 2**32])
def test_session_expiry_is_range_checked(lib, fake, value):
    with pytest.raises(
        RuntimeError, match="^session_expiry must be between 0 and 4294967295"
    ):
        lib.connect("broker.test", "me", protocol="MQTTv5", session_expiry=value)
    assert fake.instances == []


def test_largest_session_expiry(lib, fake):
    lib.connect("broker.test", "me", protocol="MQTTv5", session_expiry=2**32 - 1)
    options = fake.instances[-1].connect_options
    assert options["properties"].SessionExpiryInterval == 2**32 - 1


def test_unknown_protocol_fails_connect(lib, fake):
    with pytest.raises(RuntimeError, match="^Unknown MQTT protocol version: MQTTv6"):
        lib.connect("broker.test", protocol="MQTTv6")


# Credentials


def test_credentials_on_connect(lib, fake):
    lib.connect("broker.test", username="user", password="secret")
    assert fake.instances[-1].credentials == ("user", "secret")


def test_connect_credentials_take_precedence(lib, fake):
    lib.set_username_and_password("old", "old-secret")
    lib.connect("broker.test", username="new")
    assert fake.instances[-1].credentials == ("new", None)


@pytest.mark.parametrize("username", [None, ""])
def test_password_needs_a_username(lib, fake, username):
    lib.set_username_and_password("old", "old-secret")
    with pytest.raises(RuntimeError, match=r"^password needs username\.$"):
        lib.connect("broker.test", username=username, password="secret")


def test_empty_username_connects_without_credentials(lib, fake):
    lib.set_username_and_password("old", "old-secret")
    lib.connect("broker.test", username="")
    assert fake.instances[-1].credentials is None


def test_set_username_and_password_logs_a_deprecation_warning(tmp_path):
    suite = tmp_path / "deprecated.robot"
    suite.write_text(
        textwrap.dedent(
            """\
            *** Settings ***
            Library    MQTTLibrary

            *** Test Cases ***
            Deprecated
                Set Username And Password    user    secret
            """
        )
    )
    output = tmp_path / "output.xml"
    rc = robot.run(
        str(suite), output=str(output), log="NONE", report="NONE", stdout=io.StringIO()
    )
    assert rc == 0
    warnings = [
        message.message
        for message in ExecutionResult(str(output)).errors.messages
        if message.level == "WARN"
    ]
    assert warnings == [
        "Keyword 'MQTTLibrary.Set Username And Password' is deprecated. "
        "Pass username and password to Connect instead."
    ]


# Websockets


def test_websockets_with_the_default_path(lib, fake):
    lib.connect("broker.test", 9001, transport="WebSockets")
    client = fake.instances[-1]
    assert client.kwargs["transport"] == "websockets"
    assert client.ws_options == ("/mqtt", None)


def test_websockets_path_and_headers(lib, fake):
    headers = {"Authorization": "Bearer token"}
    lib.connect(
        "broker.test", transport="websockets", ws_path="/ws", ws_headers=headers
    )
    assert fake.instances[-1].ws_options == ("/ws", headers)


def test_tcp_sets_no_websockets_options(lib, client):
    assert client.ws_options is None


@pytest.mark.parametrize("option", [{"ws_path": "/mqtt"}, {"ws_headers": {}}])
def test_websockets_options_need_websockets(lib, fake, option):
    with pytest.raises(
        RuntimeError, match=r"^ws_path and ws_headers need transport=websockets\.$"
    ):
        lib.connect("broker.test", **option)


def test_unknown_transport_fails(lib, fake):
    with pytest.raises(
        RuntimeError, match=r"^Unknown transport: unix\. Use tcp or websockets\.$"
    ):
        lib.connect("broker.test", transport="unix")


# TLS


class RecordingContext(ssl.SSLContext):
    """An SSL context that records what it loads instead of reading files."""

    def __new__(cls, protocol):
        context = super().__new__(cls, protocol)
        context.loaded = []
        return context

    def load_verify_locations(self, cafile=None, capath=None, cadata=None):
        self.loaded.append(("ca", cafile))

    def load_default_certs(self, purpose=ssl.Purpose.SERVER_AUTH):
        self.loaded.append(("default",))

    def load_cert_chain(self, certfile, keyfile=None, password=None):
        self.loaded.append(("cert", certfile, keyfile, password))


@pytest.fixture
def contexts(monkeypatch):
    # Replaces the keywords module's ssl, not ssl.SSLContext itself: the
    # property setters in ssl.py look SSLContext up in their own module and
    # would recurse into the subclass.
    fake_ssl = types.SimpleNamespace(**vars(ssl))
    fake_ssl.SSLContext = RecordingContext
    monkeypatch.setattr(keywords, "ssl", fake_ssl)


def test_no_tls_by_default(lib, client):
    assert client.tls_context is None


def test_tls_uses_the_system_cas(lib, fake, contexts):
    lib.connect("broker.test", 8883, tls=True)
    context = fake.instances[-1].tls_context
    assert context.loaded == [("default",)]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.maximum_version == ssl.TLSVersion.MAXIMUM_SUPPORTED


def test_ca_certs_replace_the_system_cas(lib, fake, contexts):
    lib.connect("broker.test", 8883, ca_certs="ca.crt")
    assert fake.instances[-1].tls_context.loaded == [("ca", "ca.crt")]


def test_client_certificate(lib, fake, contexts):
    lib.connect(
        "broker.test",
        8884,
        ca_certs="ca.crt",
        certfile="client.crt",
        keyfile="client.key",
        keyfile_password="pass",
    )
    assert fake.instances[-1].tls_context.loaded == [
        ("ca", "ca.crt"),
        ("cert", "client.crt", "client.key", "pass"),
    ]


@pytest.mark.parametrize("option", [{"keyfile": "c.key"}, {"keyfile_password": "x"}])
def test_key_options_need_certfile(lib, fake, option):
    with pytest.raises(
        RuntimeError, match=r"^keyfile and keyfile_password need certfile\.$"
    ):
        lib.connect("broker.test", **option)


@pytest.mark.parametrize(
    "given, expected",
    [("TLSv1.2", ssl.TLSVersion.TLSv1_2), (" tlsv1.3 ", ssl.TLSVersion.TLSv1_3)],
)
def test_tls_version_allows_only_that_version(lib, fake, contexts, given, expected):
    lib.connect("broker.test", tls_version=given)
    context = fake.instances[-1].tls_context
    assert context.minimum_version == context.maximum_version == expected


def test_unknown_tls_version_fails(lib, fake):
    with pytest.raises(
        RuntimeError, match=r"^Unknown TLS version: TLSv1\.1\. Use TLSv1\.2 or"
    ):
        lib.connect("broker.test", tls_version="TLSv1.1")


def test_ciphers(lib, fake, contexts):
    lib.connect("broker.test", ciphers="ECDHE+AESGCM")
    names = {cipher["name"] for cipher in fake.instances[-1].tls_context.get_ciphers()}
    assert names
    assert all("ECDHE" in name for name in names if "TLS_" not in name)


def test_unknown_ciphers_fail(lib, fake, contexts):
    with pytest.raises(RuntimeError, match="^Cannot load ciphers no-such-cipher: "):
        lib.connect("broker.test", ciphers="no-such-cipher")


def test_insecure_skips_verification(lib, fake, contexts):
    lib.connect("broker.test", certfile="client.crt", insecure=True)
    context = fake.instances[-1].tls_context
    assert context.verify_mode == ssl.CERT_NONE
    assert context.check_hostname is False
    assert context.loaded == [("cert", "client.crt", None, None)]


def test_insecure_with_ca_certs_fails(lib, fake):
    with pytest.raises(RuntimeError, match="^insecure skips verifying the broker"):
        lib.connect("broker.test", ca_certs="ca.crt", insecure=True)


def test_insecure_alone_loads_no_cas(lib, fake, contexts):
    lib.connect("broker.test", insecure=True)
    assert fake.instances[-1].tls_context.loaded == []


@pytest.mark.parametrize(
    "option, named",
    [
        ({"ca_certs": "missing-ca.crt"}, "ca_certs missing-ca.crt"),
        ({"certfile": "missing.crt"}, "certfile missing.crt"),
        (
            {"certfile": "missing.crt", "keyfile": "missing.key"},
            "certfile missing.crt with keyfile missing.key",
        ),
    ],
)
def test_missing_tls_files_name_the_argument(lib, fake, tmp_path, option, named):
    option = {key: str(tmp_path / value) for key, value in option.items()}
    named = named.replace("missing", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="^Cannot load %s: " % named):
        lib.connect("broker.test", **option)
    assert fake.instances == []


# Last will


def test_last_will_applies_to_the_next_connect_only(lib, fake):
    lib.set_last_will("status", "offline", 1, True)
    lib.connect("broker.test", alias="first")
    lib.connect("broker.test", alias="second")
    assert fake.instances[0].will == ("status", "offline", 1, True)
    assert fake.instances[1].will is None


def test_last_will_defaults(lib, fake):
    lib.set_last_will("status")
    lib.connect("broker.test")
    assert fake.instances[-1].will == ("status", None, 0, False)


def test_last_will_survives_a_failed_connect(lib, fake):
    lib.set_last_will("status", "offline")
    fake.connect_error = None
    original = FakeClient.connect

    def refuse_once(self, *args, **options):
        FakeClient.connect = original
        raise OSError("refused")

    FakeClient.connect = refuse_once
    try:
        with pytest.raises(RuntimeError, match="refused"):
            lib.connect("broker.test")
    finally:
        FakeClient.connect = original
    lib.connect("broker.test")
    assert fake.instances[-1].will == ("status", "offline", 0, False)


def test_last_will_can_be_cleared(lib, fake):
    lib.set_last_will("status", "offline")
    lib.set_last_will(None)
    lib.connect("broker.test")
    assert fake.instances[-1].will is None


@pytest.mark.parametrize("topic", ["", "a/+", "a/#"])
def test_last_will_topic_cannot_have_wildcards(lib, topic):
    with pytest.raises(
        RuntimeError, match="^The last will topic must be a topic name without"
    ):
        lib.set_last_will(topic, "offline")


@pytest.mark.parametrize("payload", [["a"], {"a": 1}])
def test_last_will_payload_type_is_checked(lib, fake, payload):
    with pytest.raises(
        RuntimeError, match="^The last will payload must be a string, bytes, a"
    ):
        lib.set_last_will("status", payload)
    lib.connect("broker.test")
    assert fake.instances[-1].will is None


@pytest.mark.parametrize("payload", [b"\xff", bytearray(b"x"), 1, 2.5, True])
def test_last_will_accepts_paho_payloads(lib, fake, payload):
    lib.set_last_will("status", payload)
    lib.connect("broker.test")
    assert fake.instances[-1].will[1] == payload


def test_last_will_qos_is_checked(lib):
    with pytest.raises(RuntimeError, match=r"^The last will qos must be 0, 1 or 2"):
        lib.set_last_will("status", "offline", 3)


# Reconnecting


def test_reconnecting_is_off_by_default(lib, client):
    assert client.kwargs["reconnect_on_failure"] is False
    assert client._reconnect_on_failure is False
    assert client.reconnect_delays is None


def test_reconnecting_sets_the_delays(lib, fake):
    lib.connect(
        "broker.test",
        reconnect_on_failure=True,
        reconnect_delay_min=2,
        reconnect_delay_max=30,
    )
    client = fake.instances[-1]
    # On only after the first successful CONNACK, so paho cannot answer a
    # refused one by falling back to MQTT 3.1 or a random client id.
    assert client.kwargs["reconnect_on_failure"] is False
    assert client._reconnect_on_failure is True
    assert client.reconnect_delays == (2, 30)


@pytest.mark.parametrize("delays", [(0, 120), (-1, 120), (10, 5)])
def test_reconnect_delays_are_checked(lib, fake, delays):
    with pytest.raises(
        RuntimeError, match="^reconnect_delay_min must be at least 1 and no more"
    ):
        lib.connect(
            "broker.test",
            reconnect_on_failure=True,
            reconnect_delay_min=delays[0],
            reconnect_delay_max=delays[1],
        )


def _drop_and_reconnect(client, session_present=False):
    client.fire_disconnect(reason(PacketTypes.DISCONNECT, "Unspecified error"))
    client.fire_connect(reason(PacketTypes.CONNACK, "Success"), session_present)


def test_reconnect_marks_the_connection_connected(lib, fake):
    lib.connect("broker.test", reconnect_on_failure=True)
    client = fake.instances[-1]
    client.fire_disconnect(reason(PacketTypes.DISCONNECT, "Unspecified error"))
    assert lib.get_connection_info()["connected"] is False
    client.fire_connect(reason(PacketTypes.CONNACK, "Success"))
    assert lib.get_connection_info()["connected"] is True


def test_reconnect_subscribes_again_without_a_session(lib, fake):
    lib.connect("broker.test", reconnect_on_failure=True)
    client = fake.instances[-1]
    lib.subscribe("a", 1, timeout=0)
    lib.subscribe("b/#", 2, timeout=0)
    lib.subscribe("gone", 0, timeout=0)
    lib.unsubscribe("gone")
    _drop_and_reconnect(client)
    assert client.subscriptions[-1] == ([("a", 1), ("b/#", 2)], 0)
    # The SUBACK of the renewed subscriptions answers nobody.
    assert client._mid not in lib._connections["default"]._acks
    client.fire_message("b/1", "after")
    assert lib.listen("b/#", timeout=0) == ["after"]


def test_reconnect_keeps_a_session_the_broker_kept(lib, fake):
    lib.connect("broker.test", "me", False, reconnect_on_failure=True)
    client = fake.instances[-1]
    lib.subscribe("a", 1, timeout=0)
    count = len(client.subscriptions)
    _drop_and_reconnect(client, session_present=True)
    assert len(client.subscriptions) == count


def test_reconnect_without_subscriptions_subscribes_nothing(lib, fake):
    lib.connect("broker.test", reconnect_on_failure=True)
    client = fake.instances[-1]
    _drop_and_reconnect(client)
    assert client.subscriptions == []


def test_failed_resubscribe_is_not_waited_for(lib, fake):
    lib.connect("broker.test", reconnect_on_failure=True)
    client = fake.instances[-1]
    lib.subscribe("a", 1, timeout=0)
    client.subscribe_rc = mqtt.MQTT_ERR_NO_CONN
    _drop_and_reconnect(client)
    assert lib._connections["default"]._abandoned == {}


def test_listen_waits_through_a_reconnect(lib, fake):
    lib.connect("broker.test", reconnect_on_failure=True)
    client = fake.instances[-1]
    lib.subscribe("a", 1, timeout=0)
    client.fire_disconnect(reason(PacketTypes.DISCONNECT, "Unspecified error"))
    assert lib.listen("a", timeout=0.01) == []


def test_subscribe_and_validate_waits_through_a_reconnect(lib, fake):
    lib.connect("broker.test", reconnect_on_failure=True)
    client = fake.instances[-1]
    client.fire_disconnect(reason(PacketTypes.DISCONNECT, "Unspecified error"))
    lib.subscribe("a", 1, timeout=0)
    with pytest.raises(
        AssertionError, match="^The expected payload didn't arrive in the topic$"
    ):
        lib.subscribe_and_validate("a", 1, "x", timeout=0.01)


def test_refused_connect_with_reconnecting_fails(lib, fake, monkeypatch):
    original = FakeClient.__init__

    def refusing(self, **kwargs):
        original(self, **kwargs)
        self.connack = reason(PacketTypes.CONNACK, "Not authorized")

    monkeypatch.setattr(FakeClient, "__init__", refusing)
    with pytest.raises(RuntimeError, match="Not authorized$"):
        lib.connect("broker.test", reconnect_on_failure=True)
    assert fake.instances[-1].stopped
    assert fake.instances[-1]._reconnect_on_failure is False


def test_refused_resubscription_fails_listen(lib, fake):
    lib.connect("broker.test", reconnect_on_failure=True)
    client = fake.instances[-1]
    lib.subscribe("a", 1, timeout=0)
    lib.subscribe("b", 1, timeout=0)
    client.suback = [
        reason(PacketTypes.SUBACK, "Not authorized"),
        reason(PacketTypes.SUBACK, "Granted QoS 1"),
    ]
    _drop_and_reconnect(client)
    with pytest.raises(
        RuntimeError,
        match="^Listen on a failed: the broker refused the subscription after "
        "a reconnect: Not authorized$",
    ):
        lib.listen("a", timeout=1)
    assert lib.listen("b", timeout=0) == []
    # Only the accepted one is renewed after the next reconnect.
    client.suback = [reason(PacketTypes.SUBACK, "Granted QoS 1")]
    _drop_and_reconnect(client)
    assert client.subscriptions[-1] == ([("b", 1)], 0)


def test_late_resubscribe_suback_is_matched(lib, fake):
    lib.connect("broker.test", reconnect_on_failure=True)
    client = fake.instances[-1]
    lib.subscribe("a", 1, timeout=0)
    client.suback = None
    _drop_and_reconnect(client)
    client.on_subscribe(
        client, None, client._mid, [reason(PacketTypes.SUBACK, "Not authorized")], None
    )
    with pytest.raises(RuntimeError, match="refused the subscription"):
        lib.listen("a", timeout=0)
    # Subscribing again clears the refusal.
    client.suback = [reason(PacketTypes.SUBACK, "Granted QoS 1")]
    lib.subscribe("a", 1, timeout=0)
    assert lib.listen("a", timeout=0) == []


def test_messages_queued_before_a_refused_resubscription_are_returned(lib, fake):
    lib.connect("broker.test", reconnect_on_failure=True)
    client = fake.instances[-1]
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", "before")
    client.suback = [reason(PacketTypes.SUBACK, "Not authorized")]
    _drop_and_reconnect(client)
    assert lib.listen("a", timeout=0) == ["before"]


def test_disconnect_while_reconnecting_stops_without_failing(lib, fake, log):
    lib.connect("broker.test", reconnect_on_failure=True)
    client = fake.instances[-1]
    client.fire_disconnect(reason(PacketTypes.DISCONNECT, "Unspecified error"))
    lib.disconnect()
    assert client.disconnects == 1
    assert client.stopped
    assert log.warnings == []


def test_disconnect_after_a_late_reconnect_says_goodbye(lib, fake):
    lib.connect("broker.test", reconnect_on_failure=True)
    client = fake.instances[-1]
    client.fire_disconnect(reason(PacketTypes.DISCONNECT, "Unspecified error"))
    # The reconnect finishes while the loop stops: the socket is still open.
    client.sock = object()
    lib.disconnect()
    assert client.disconnects == 2
