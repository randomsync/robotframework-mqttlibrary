"""The assertion keywords (1.1): Wait Until Message Received, Message Count
Should Be, Payload Should Match, Should Be Connected and Should Not Be
Connected, and Subscribe And Validate on top of the same wait."""

import threading
from datetime import timedelta

import pytest
from conftest import FakeClient, Library, reason
from paho.mqtt.packettypes import PacketTypes

LOST = reason(PacketTypes.DISCONNECT, "Keep alive timeout")

# Wait Until Message Received


def test_wait_returns_the_matching_message(lib, client):
    lib.subscribe("a/#", 1, timeout=0)
    client.fire_message("a/1", "status: running", qos=1)
    message = lib.wait_until_message_received("a/#", "running", timeout=0)
    assert (message.topic, message.payload, message.qos) == (
        "a/1",
        "status: running",
        1,
    )


def test_wait_without_a_pattern_takes_the_first_message(lib, client):
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", "first")
    client.fire_message("a", "second")
    assert lib.wait_until_message_received("a", timeout=0).payload == "first"
    assert lib.listen("a", timeout=0) == ["second"]


def test_wait_searches_the_whole_payload(lib, client):
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", "say yes")
    client.fire_message("a", "yes")
    assert lib.wait_until_message_received("a", "yes", timeout=0).payload == "say yes"
    assert lib.wait_until_message_received("a", "^yes$", timeout=0).payload == "yes"


def test_wait_takes_earlier_messages_and_keeps_later_ones(lib, client):
    lib.subscribe("a", 1, timeout=0)
    for payload in ("no", "yes", "after"):
        client.fire_message("a", payload)
    lib.wait_until_message_received("a", "yes", timeout=0)
    assert lib.listen("a", timeout=0, limit=0) == ["after"]


def test_wait_waits_for_a_late_message(lib, client):
    lib.subscribe("a", 1, timeout=0)
    timer = threading.Timer(0.05, client.fire_message, ("a", "late"))
    timer.start()
    message = lib.wait_until_message_received("a", "late", timeout=timedelta(seconds=5))
    timer.join()
    assert message.payload == "late"


def test_wait_skips_undecodable_messages(lib, client):
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", b"\xff")
    client.fire_message("a", "text")
    assert lib.wait_until_message_received("a", timeout=0).payload == "text"


def test_wait_matches_bytes_without_decoding(lib, client):
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", b"\x01\x02")
    client.fire_message("a", b"\xff\x00")
    message = lib.wait_until_message_received(
        "a", r"^\xff\x00$", timeout=0, decode=False
    )
    assert message.payload == b"\xff\x00"


def test_wait_failure_names_the_topic_pattern_and_timeout(lib, client):
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", "no")
    with pytest.raises(
        AssertionError,
        match=r"^Did not receive a message matching 'yes' on a within 50 milliseconds$",
    ):
        lib.wait_until_message_received("a", "yes", timeout="0.05 s")


def test_wait_failure_without_a_pattern(lib, client):
    lib.subscribe("a", 1, timeout=0)
    with pytest.raises(
        AssertionError, match=r"^Did not receive a message on a within 0 seconds$"
    ):
        lib.wait_until_message_received("a", timeout=0)


def test_wait_fails_at_once_when_the_connection_drops(lib, client):
    lib.subscribe("a", 1, timeout=0)
    timer = threading.Timer(0.05, client.fire_disconnect, (LOST,))
    timer.start()
    with pytest.raises(
        AssertionError,
        match=r"within 5 seconds \(connection lost: Keep alive timeout\)$",
    ):
        lib.wait_until_message_received("a", timeout="5 s")
    timer.join()


def test_wait_continues_through_a_reconnect(lib, fake):
    lib.connect("broker.test", reconnect_on_failure=True)
    client = fake.instances[-1]
    lib.subscribe("a", 1, timeout=0)
    client.fire_disconnect(LOST)

    def come_back():
        client.fire_connect(reason(PacketTypes.CONNACK, "Success"))
        client.fire_message("a", "after")

    timer = threading.Timer(0.05, come_back)
    timer.start()
    assert lib.wait_until_message_received("a", timeout="5 s").payload == "after"
    timer.join()


def test_wait_fails_on_a_subscription_refused_after_a_reconnect(lib, fake):
    lib.connect("broker.test", reconnect_on_failure=True)
    client = fake.instances[-1]
    lib.subscribe("a", 1, timeout=0)
    client.suback = [reason(PacketTypes.SUBACK, "Not authorized")]
    client.fire_disconnect(LOST)
    client.fire_connect(reason(PacketTypes.CONNACK, "Success"))
    with pytest.raises(
        AssertionError,
        match=r"\(the broker refused the subscription after a reconnect: "
        r"Not authorized\)$",
    ):
        lib.wait_until_message_received("a", timeout="5 s")


def test_wait_without_subscribe_fails(lib, client):
    with pytest.raises(
        RuntimeError, match=r"^Not subscribed to a on connection 'default'\. Use"
    ):
        lib.wait_until_message_received("a", timeout=0)


def test_wait_with_an_invalid_pattern_fails(lib, client):
    lib.subscribe("a", 1, timeout=0)
    with pytest.raises(ValueError, match=r"^Invalid regular expression '\(': "):
        lib.wait_until_message_received("a", "(", timeout=0)


# Subscribe And Validate keeps 1.0's matching


def test_subscribe_and_validate_still_matches_from_the_start(lib, client):
    client.fire_message("a", "say yes")
    with pytest.raises(
        AssertionError, match="^The expected payload didn't arrive in the topic$"
    ):
        lib.subscribe_and_validate("a", 1, "yes", timeout=0)


def test_subscribe_and_validate_reports_a_refused_subscription(lib, fake):
    lib.connect("broker.test", reconnect_on_failure=True)
    client = fake.instances[-1]
    lib.subscribe("a", 1, timeout=0)
    client.suback = [reason(PacketTypes.SUBACK, "Not authorized")]
    client.fire_disconnect(LOST)
    client.fire_connect(reason(PacketTypes.CONNACK, "Success"))
    client.suback = [reason(PacketTypes.SUBACK, "Granted QoS 1")]
    # Subscribing again clears the refusal, so this waits out its timeout.
    with pytest.raises(AssertionError, match=r"in the topic$"):
        lib.subscribe_and_validate("a", 1, "x", timeout=0.01)


def test_subscribe_and_validate_with_an_invalid_pattern_fails(lib, client):
    with pytest.raises(ValueError, match="^Invalid regular expression"):
        lib.subscribe_and_validate("a", 1, "(", timeout=0)


# Message Count Should Be


def test_message_count_should_be(lib, client):
    lib.subscribe("a", 1, timeout=0)
    lib.message_count_should_be("a", 0)
    client.fire_message("a", "one")
    client.fire_message("a", "two")
    lib.message_count_should_be("a", 2)
    assert lib.listen("a", timeout=0, limit=0) == ["one", "two"]


def test_message_count_failure_names_the_topic(lib, client):
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", "one")
    with pytest.raises(
        AssertionError, match=r"^Expected 2 queued messages on a, but found 1\.$"
    ):
        lib.message_count_should_be("a", 2)


def test_message_count_without_subscribe_fails(lib, client):
    with pytest.raises(RuntimeError, match="^Not subscribed to a on connection"):
        lib.message_count_should_be("a", 0)


def test_message_count_reports_dropped_messages(fake, log):
    lib = Library(loop_timeout="0.05 seconds", max_queue=1)
    lib.connect("broker.test")
    client = FakeClient.instances[-1]
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", "one")
    client.fire_message("a", "two")
    lib.message_count_should_be("a", 1)
    assert log.warnings == [
        "1 messages on a were dropped because more than 1 were queued"
    ]


# Payload Should Match


def test_payload_should_match_a_message(lib, client):
    lib.subscribe("a", 1, timeout=0)
    client.fire_message("a", "21.5")
    lib.payload_should_match(lib.get_messages("a")[0], r"^\d+(\.\d+)?$")


def test_payload_should_match_a_payload(lib):
    lib.payload_should_match("hello world", "world")
    lib.payload_should_match(b"\x00\xff", r"\xff$")


def test_payload_should_match_failure_names_the_topic_and_pattern(lib, client):
    lib.subscribe("a/#", 1, timeout=0)
    client.fire_message("a/1", "hello")
    message = lib.get_messages("a/#")[0]
    with pytest.raises(
        AssertionError,
        match=r"^Payload of the message on a/1 'hello' does not match '\^bye'\.$",
    ):
        lib.payload_should_match(message, "^bye")


def test_payload_should_match_failure_for_a_bytes_payload(lib):
    with pytest.raises(
        AssertionError, match=r"^Payload b'\\x00' does not match 'x'\.$"
    ):
        lib.payload_should_match(b"\x00", "x")


def test_payload_should_match_needs_a_message_or_payload(lib):
    with pytest.raises(ValueError, match="^Expected a message or a payload, not int"):
        lib.payload_should_match(5, "5")


# Should Be Connected and Should Not Be Connected


def test_should_be_connected(lib, client):
    lib.should_be_connected()
    lib.should_be_connected("default")
    with pytest.raises(AssertionError, match="is connected"):
        lib.should_not_be_connected()


def test_should_be_connected_after_a_drop_fails_with_the_reason(lib, client):
    client.fire_disconnect(LOST)
    with pytest.raises(
        AssertionError,
        match=r"^Connection 'default' to broker\.test:1883 is not connected "
        r"\(connection lost: Keep alive timeout\)\.$",
    ):
        lib.should_be_connected()
    lib.should_not_be_connected()


def test_should_be_connected_without_a_connection_fails(lib):
    with pytest.raises(RuntimeError, match="^No connection with alias 'gone'"):
        lib.should_be_connected("gone")


def test_should_not_be_connected_without_a_connection_passes(lib, client):
    lib.should_not_be_connected("never")
    lib.disconnect()
    lib.should_not_be_connected()


def test_should_not_be_connected_names_the_alias(lib, fake):
    lib.connect("broker.test", 1884, alias="sub")
    with pytest.raises(
        AssertionError, match=r"^Connection 'sub' to broker\.test:1884 is connected\.$"
    ):
        lib.should_not_be_connected("sub")
