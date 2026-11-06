"""Message objects, decode, Get Messages, Clear Messages, max_queue and the
mid from Publish (1.1)."""

import threading
import time

import pytest
from conftest import FakeClient, Library, connection, reason
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties

from MQTTLibrary.connection import Message

# Message objects


def test_get_messages_returns_message_objects(lib, client):
    lib.subscribe("a/#", 1, timeout=0)
    before = time.time()
    client.fire_message("a/1", "one", qos=1, retain=True)
    [message] = lib.get_messages("a/#")
    assert message.topic == "a/1"
    assert message.payload == "one"
    assert message.qos == 1
    assert message.retain is True
    assert message.properties == {}
    assert before <= message.timestamp <= time.time()


def test_message_repr_shows_every_field(lib, client):
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", "one")
    text = repr(lib.get_messages("a")[0])
    for field in ("topic=", "payload=", "qos=", "retain=", "properties=", "timestamp="):
        assert field in text


def test_messages_are_frozen(lib, client):
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", "one")
    message = lib.get_messages("a")[0]
    with pytest.raises(AttributeError):
        message.payload = "changed"


def test_mqtt5_properties_become_a_dict(lib, client):
    properties = Properties(PacketTypes.PUBLISH)
    properties.ContentType = "text/plain"
    properties.UserProperty = ("key", "value")
    properties.CorrelationData = b"\x01\x02"
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", "one", properties=properties)
    assert lib.get_messages("a")[0].properties == {
        "ContentType": "text/plain",
        "UserProperty": [("key", "value")],
        "CorrelationData": b"\x01\x02",
    }


def test_wildcard_messages_carry_their_topic(lib, client):
    # #32
    lib.subscribe("a/#", 1, timeout=0)
    for topic in ("a/1", "a/2/x", "a"):
        client.fire_message(topic, topic)
    assert [m.topic for m in lib.get_messages("a/#")] == ["a/1", "a/2/x", "a"]


# Decoding


def test_listen_returns_bytes_without_decoding(lib, client):
    # #31
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", b"\xff\xfe\x00")
    assert lib.listen("a", timeout=0, decode=False) == [b"\xff\xfe\x00"]


def test_subscribe_returns_bytes_without_decoding(lib, client):
    client.fire_message("a", b"\xff")
    assert lib.subscribe("a", 1, timeout=0.01, decode=False) == [b"\xff"]


def test_get_messages_keeps_bytes_without_decoding(lib, client):
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", b"\xff")
    assert lib.get_messages("a", decode=False)[0].payload == b"\xff"


def test_undecodable_payload_suggests_decode_false(lib, client):
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", b"\xff")
    client.fire_message("a", "fine")
    with pytest.raises(RuntimeError, match=r"Use decode=\$\{False\} to get payloads"):
        lib.get_messages("a")
    assert lib.get_messages("a")[0].payload == "fine"


def test_decoding_does_not_change_the_queued_message(lib, client):
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", "one")
    queued = lib._connections["default"]._filters["a"][0]
    assert lib.get_messages("a")[0].payload == "one"
    assert queued.payload == b"one"


# Get Messages


def test_get_messages_takes_everything_queued(lib, client):
    lib.subscribe("a", 1, timeout=0)
    for payload in ("one", "two", "three"):
        client.fire_message("a", payload)
    assert [m.payload for m in lib.get_messages("a")] == ["one", "two", "three"]
    assert lib.get_messages("a") == []


def test_get_messages_limit_keeps_the_rest(lib, client):
    lib.subscribe("a", 1, timeout=0)
    for payload in ("one", "two", "three"):
        client.fire_message("a", payload)
    assert [m.payload for m in lib.get_messages("a", limit=2)] == ["one", "two"]
    assert lib.listen("a", timeout=0) == ["three"]


def test_get_messages_waits_for_the_limit(lib, client):
    lib.subscribe("a", 1, timeout=0)
    timer = threading.Timer(0.05, client.fire_message, ("a", "late"))
    timer.start()
    messages = lib.get_messages("a", timeout=5, limit=1)
    timer.join()
    assert [m.payload for m in messages] == ["late"]


def test_get_messages_without_subscribe_warns(lib, client, log):
    assert lib.get_messages("nothing") == []
    assert log.warnings == ["Cannot listen when not subscribed to topic: nothing"]


def test_get_messages_after_a_lost_connection_fails_when_empty(lib, client):
    lib.subscribe("a", 1, timeout=0)
    client.fire_disconnect(reason(PacketTypes.DISCONNECT, "Unspecified error"))
    with pytest.raises(RuntimeError, match="^Listen on a failed"):
        lib.get_messages("a")


# Clear Messages


def test_clear_messages_of_one_topic(lib, client):
    lib.subscribe("a", 1, timeout=0)
    lib.subscribe("b", 1, timeout=0)
    client.fire_message("a", "one")
    client.fire_message("b", "two")
    lib.clear_messages("a")
    assert lib.get_messages("a") == []
    assert [m.payload for m in lib.get_messages("b")] == ["two"]
    client.fire_message("a", "after")
    assert lib.listen("a", timeout=0) == ["after"]


def test_clear_messages_of_every_queue(lib, client):
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", "one")
    client.fire_message("unclaimed", "two")
    lib.clear_messages()
    assert lib.get_messages("a") == []
    lib.subscribe("unclaimed", 1, timeout=0)
    assert lib.get_messages("unclaimed") == []


def test_clear_messages_forgets_dropped_messages(monkeypatch, fake, log):
    lib = Library(loop_timeout="0.05 seconds", max_queue=1)
    lib.connect("broker.test")
    client = FakeClient.instances[-1]
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", "one")
    client.fire_message("a", "two")
    lib.clear_messages("a")
    client.fire_message("a", "three")
    assert lib.listen("a", timeout=0) == ["three"]
    assert log.warnings == []


def test_clear_messages_without_subscribe_warns(lib, client, log):
    lib.clear_messages("nothing")
    assert log.warnings == [
        "Cannot clear messages when not subscribed to topic: nothing"
    ]


def test_clear_messages_without_a_connection_fails(lib):
    with pytest.raises(RuntimeError, match="^No connection with alias 'default'"):
        lib.clear_messages()


# max_queue


@pytest.fixture
def small(fake, log):
    lib = Library(loop_timeout="0.05 seconds", max_queue=3)
    lib.connect("broker.test")
    return lib, FakeClient.instances[-1]


def test_max_queue_keeps_the_newest_messages(small, log):
    lib, client = small
    lib.subscribe("a", 1, timeout=0)
    for i in range(4):
        client.fire_message("a", str(i))
    assert lib.listen("a", timeout=0, limit=0) == ["1", "2", "3"]
    assert log.warnings == [
        "1 messages on a were dropped because more than 3 were queued"
    ]


def test_max_queue_bounds_unclaimed_messages(small, log):
    lib, client = small
    for i in range(5):
        client.fire_message("a", str(i))
    lib.subscribe("a", 1, timeout=0)
    assert lib.listen("a", timeout=0, limit=0) == ["2", "3", "4"]


def test_max_queue_bounds_returned_unclaimed_messages(small, monkeypatch):
    lib, client = small
    conn = lib._connections["default"]
    for i in range(2):
        client.fire_message("a", "a%d" % i)
    conn.register("a")
    for i in range(2):
        client.fire_message("b", "b%d" % i)
    conn.unregister("a", keep_messages=True)
    assert [m.payload for m in conn._unclaimed] == [b"a1", b"b0", b"b1"]
    assert conn._unclaimed.dropped == 1


@pytest.mark.parametrize("value", [0, -1])
def test_max_queue_must_be_positive(value):
    with pytest.raises(ValueError, match="^max_queue must be at least 1"):
        Library(max_queue=value)


def test_max_queue_default():
    assert Library()._max_queue == connection.QUEUE_LIMIT == 10000


# Publish


def test_publish_returns_the_mid(lib, client):
    first = lib.publish("a", "one", 1)
    second = lib.publish("a", b"\xff", 1)
    assert isinstance(first, int)
    assert second == first + 1
    assert client.published[-1] == ("a", b"\xff", 1, False)


def test_message_class_is_importable():
    assert Message.__dataclass_fields__.keys() == {
        "topic",
        "payload",
        "qos",
        "retain",
        "properties",
        "timestamp",
    }
