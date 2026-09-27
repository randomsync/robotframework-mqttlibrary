import threading
import time

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.packettypes import PacketTypes

from MQTTLibrary.connection import QUEUE_LIMIT
from conftest import FakeClient, reason


# Message queues


def test_message_goes_to_its_filter(lib, client):
    lib.subscribe('a/+', 1, timeout=0)
    client.fire_message('a/1', 'one')
    assert lib.listen('a/+', timeout=0) == ['one']


def test_overlapping_filters_each_get_the_message(lib, client):
    lib.subscribe('a/#', 1, timeout=0)
    lib.subscribe('a/1', 1, timeout=0)
    client.fire_message('a/1', 'one')
    assert lib.listen('a/#', timeout=0) == ['one']
    assert lib.listen('a/1', timeout=0) == ['one']


def test_unmatched_messages_wait_for_a_filter(lib, client):
    client.fire_message('a/1', 'early')
    client.fire_message('b/1', 'other')
    lib.subscribe('a/#', 1, timeout=0)
    assert lib.listen('a/#', timeout=0) == ['early']
    lib.subscribe('b/1', 1, timeout=0)
    assert lib.listen('b/1', timeout=0) == ['other']


def test_unclaimed_queue_is_bounded(lib, client, log):
    for i in range(QUEUE_LIMIT + 1):
        client.fire_message('a', str(i))
    lib.subscribe('a', 1, timeout=0)
    messages = lib.listen('a', timeout=0, limit=0)
    assert len(messages) == QUEUE_LIMIT
    assert messages[0] == '1'
    assert log.warnings == ['1 messages that matched no filter were dropped '
                            'because more than %d were queued' % QUEUE_LIMIT]


def test_filter_queue_is_bounded(lib, client, log):
    lib.subscribe('a', 1, timeout=0)
    for i in range(QUEUE_LIMIT + 2):
        client.fire_message('a', str(i))
    messages = lib.listen('a', timeout=0, limit=0)
    assert len(messages) == QUEUE_LIMIT
    assert messages[0] == '2'
    assert log.warnings == ['2 messages on a were dropped because more than '
                            '%d were queued' % QUEUE_LIMIT]
    client.fire_message('a', 'next')
    lib.listen('a', timeout=0)
    assert len(log.warnings) == 1


def test_broker_copies_for_overlapping_filters_are_not_duplicated(lib,
                                                                   client):
    # Mosquitto sends one copy per matching subscription, back to back.
    lib.subscribe('a/#', 1, timeout=0)
    lib.subscribe('a/+', 1, timeout=0)
    lib.subscribe('a/1', 1, timeout=0)
    for payload in ('one', 'two'):
        for _ in range(3):
            client.fire_message('a/1', payload)
    client.fire_message('a/2', 'three')
    client.fire_message('a/2', 'three')
    for topic in ('a/#', 'a/+'):
        assert lib.listen(topic, timeout=0, limit=0) == ['one', 'two',
                                                         'three']
    assert lib.listen('a/1', timeout=0, limit=0) == ['one', 'two']


def test_single_copy_for_overlapping_filters_reaches_each(lib, client):
    # Brokers may also send a single copy for overlapping subscriptions.
    lib.subscribe('a/#', 1, timeout=0)
    lib.subscribe('a/1', 1, timeout=0)
    client.fire_message('a/1', 'one')
    client.fire_message('a/1', 'two')
    assert lib.listen('a/#', timeout=0, limit=0) == ['one', 'two']
    assert lib.listen('a/1', timeout=0, limit=0) == ['one', 'two']


def test_identical_messages_for_one_filter_are_kept(lib, client):
    lib.subscribe('a', 1, timeout=0)
    client.fire_message('a', 'same')
    client.fire_message('a', 'same')
    assert lib.listen('a', timeout=0, limit=0) == ['same', 'same']


def test_subscribing_again_keeps_queued_messages(lib, client):
    lib.subscribe('a', 1, timeout=0)
    client.fire_message('a', 'one')
    lib.subscribe('a', 1, timeout=0)
    assert lib.listen('a', timeout=0) == ['one']
    assert len(client.subscriptions) == 2


def test_unsubscribe_drops_only_its_filter(lib, client):
    lib.subscribe('a', 1, timeout=0)
    lib.subscribe('b', 1, timeout=0)
    client.fire_message('a', 'one')
    lib.unsubscribe('a')
    client.fire_message('b', 'two')
    assert client.unsubscriptions == ['a']
    assert lib.listen('b', timeout=0) == ['two']
    assert lib.listen('a', timeout=0) == []


@pytest.mark.parametrize('limit, returned, kept', [
    (1, ['m0'], ['m1', 'm2']),
    (2, ['m0', 'm1'], ['m2']),
    (0, ['m0', 'm1', 'm2'], []),
    (5, ['m0', 'm1', 'm2'], []),
])
def test_listen_returns_oldest_first_and_keeps_the_rest(lib, client, limit,
                                                        returned, kept):
    lib.subscribe('a', 1, timeout=0)
    for i in range(3):
        client.fire_message('a', 'm%d' % i)
    assert lib.listen('a', timeout=0, limit=limit) == returned
    assert lib.listen('a', timeout=0, limit=0) == kept


def test_sync_subscribe_listens(lib, client):
    client.fire_message('a', 'queued')
    assert lib.subscribe('a', 1, timeout='0.1 s', limit=1) == ['queued']


def test_listen_returns_when_the_limit_arrives(lib, client):
    lib.subscribe('a', 1, timeout=0)
    timer = threading.Timer(0.05, client.fire_message, ('a', 'late'))
    timer.start()
    assert lib.listen('a', timeout='5 s', limit=1) == ['late']
    timer.join()


def test_listen_fails_when_the_connection_drops(lib, client):
    lib.subscribe('a', 1, timeout=0)
    timer = threading.Timer(0.05, client.fire_disconnect, (
        reason(PacketTypes.DISCONNECT, 'Keep alive timeout'),))
    timer.start()
    with pytest.raises(RuntimeError, match=r'^Listen on a failed \(connection '
                       r'lost: Keep alive timeout\)$'):
        lib.listen('a', timeout='5 s', limit=0)
    timer.join()


def test_listen_after_a_drop_returns_what_was_received(lib, client):
    lib.subscribe('a', 1, timeout=0)
    client.fire_message('a', 'one')
    client.fire_disconnect(reason(PacketTypes.DISCONNECT, 'Unspecified error'))
    assert lib.listen('a', timeout='5 s', limit=2) == ['one']


def test_listen_drops_only_an_undecodable_message(lib, client):
    lib.subscribe('a', 1, timeout=0)
    client.fire_message('a', 'one')
    client.fire_message('a', b'\xff')
    client.fire_message('a', 'three')
    with pytest.raises(RuntimeError, match='^Dropped a message on a that is '
                       'not valid UTF-8: '):
        lib.listen('a', timeout=0, limit=0)
    assert lib.listen('a', timeout=0, limit=0) == ['one', 'three']


def test_listen_without_subscribe_warns(lib, client, log):
    assert lib.listen('a', timeout=0) == []
    assert log.warnings == ['Cannot listen when not subscribed to topic: a']


def test_subscribe_and_validate_consumes_until_a_match(lib, client):
    client.fire_message('a', 'no')
    client.fire_message('a', 'yes 1')
    client.fire_message('a', 'yes 2')
    lib.subscribe_and_validate('a', 1, '^yes', timeout=0)
    assert lib.listen('a', timeout=0, limit=0) == ['yes 2']


def test_subscribe_and_validate_waits_for_a_match(lib, client):
    timer = threading.Timer(0.05, client.fire_message, ('a', 'late'))
    timer.start()
    lib.subscribe_and_validate('a', 1, 'late', timeout='5 s')
    timer.join()


def test_subscribe_and_validate_skips_undecodable_messages(lib, client):
    client.fire_message('a', b'\xff')
    client.fire_message('a', 'yes')
    lib.subscribe_and_validate('a', 1, 'yes', timeout=0)


def test_subscribe_and_validate_fails_when_the_connection_drops(lib, client):
    timer = threading.Timer(0.05, client.fire_disconnect, (
        reason(PacketTypes.DISCONNECT, 'Keep alive timeout'),))
    timer.start()
    with pytest.raises(AssertionError, match=r"^The expected payload didn't "
                       r"arrive in the topic \(connection lost: Keep alive "
                       r"timeout\)$"):
        lib.subscribe_and_validate('a', 1, 'yes', timeout='5 s')
    timer.join()


def test_subscribe_and_validate_fails_without_a_match(lib, client):
    client.fire_message('a', 'no')
    with pytest.raises(AssertionError,
                       match="The expected payload didn't arrive in the topic"):
        lib.subscribe_and_validate('a', 1, 'yes', timeout='0.05 s')


def test_dispatch_is_safe_while_filters_change(lib, client):
    lib.subscribe('keep', 1, timeout=0)
    count = 2000
    errors = []

    def publisher():
        try:
            for i in range(count):
                client.fire_message('keep', str(i))
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    thread = threading.Thread(target=publisher)
    thread.start()
    for i in range(1000):
        lib.subscribe('other/%d' % i, 0, timeout=0)
        lib.unsubscribe('other/%d' % i)
    thread.join()

    assert errors == []
    assert lib.listen('keep', timeout=0, limit=0) == [str(i)
                                                      for i in range(count)]


# Connect


def test_connect_configures_the_client(lib, fake):
    lib.set_username_and_password('user', 'secret')
    returned = lib.connect('broker.test', '1884', 'me', False, '30')
    client = fake.instances[-1]
    assert returned is client
    assert client.kwargs == {
        'callback_api_version': mqtt.CallbackAPIVersion.VERSION2,
        'client_id': 'me',
        'clean_session': False,
        'reconnect_on_failure': False,
    }
    assert client.connect_timeout == 0.05
    assert client.credentials == ('user', 'secret')
    assert client.connect_args == ('broker.test', 1884, 30)
    assert client.loop_starts == 1


def test_connect_without_credentials(lib, client):
    assert client.credentials is None


def test_refused_connect_fails_with_the_reason(lib, fake, monkeypatch):
    monkeypatch.setattr(FakeClient, '__init__', _refusing_init)
    with pytest.raises(RuntimeError, match='^Connection to broker.test:1883 '
                       'failed: Not authorized$'):
        lib.connect('broker.test')
    client = fake.instances[-1]
    assert client.stopped
    assert lib._connections == {}


def _refusing_init(self, **kwargs):
    _original_init(self, **kwargs)
    self.connack = reason(PacketTypes.CONNACK, 'Not authorized')


_original_init = FakeClient.__init__


def test_connect_times_out_without_connack(lib, fake, monkeypatch):
    def silent_init(self, **kwargs):
        _original_init(self, **kwargs)
        self.connack = None
    monkeypatch.setattr(FakeClient, '__init__', silent_init)
    with pytest.raises(RuntimeError, match='^Connection to broker.test:1883 '
                       'failed: no CONNACK within 0.05 seconds$'):
        lib.connect('broker.test')
    assert fake.instances[-1].stopped


def test_disconnect_before_connack_fails_connect(lib, fake, monkeypatch):
    def dropping_init(self, **kwargs):
        _original_init(self, **kwargs)
        self.connack = None
        self.loop_start = lambda: self.fire_disconnect(
            reason(PacketTypes.DISCONNECT, 'Unspecified error'))
    monkeypatch.setattr(FakeClient, '__init__', dropping_init)
    with pytest.raises(RuntimeError, match=r'failed: the broker closed the '
                       r'connection without accepting it \(Unspecified '
                       r'error\). It may have rejected the protocol version '
                       r'or the client id$'):
        lib.connect('broker.test')


def test_connect_socket_error_names_the_host(lib, fake, monkeypatch):
    def failing_init(self, **kwargs):
        _original_init(self, **kwargs)
        self.connect_error = ConnectionRefusedError('Connection refused')
    monkeypatch.setattr(FakeClient, '__init__', failing_init)
    with pytest.raises(RuntimeError, match='^Connection to broker.test:1 '
                       'failed: Connection refused$'):
        lib.connect('broker.test', 1)
    assert fake.instances[-1].loop_starts == 0


def test_connect_again_on_an_alias_replaces_it(lib, fake, log):
    lib.connect('broker.test', alias='sub')
    old = fake.instances[-1]
    lib.connect('broker.test', alias='sub')
    assert old.disconnects == 1
    assert old.stopped
    assert log.warnings == ["Connection 'sub' to broker.test:1883 was still "
                            "open. Disconnecting it before connecting again."]
    assert lib._connections['sub'].client is fake.instances[-1]


def test_connect_again_after_a_lost_connection_warns(lib, fake, log):
    lib.connect('broker.test')
    fake.instances[-1].fire_disconnect(
        reason(PacketTypes.DISCONNECT, 'Keep alive timeout'))
    lib.connect('broker.test')
    assert log.warnings[1] == ('The client disconnected unexpectedly: '
                               'Keep alive timeout')


# Aliases


def test_keywords_use_the_last_connection(lib, fake):
    lib.connect('broker.test', alias='sub')
    sub = fake.instances[-1]
    lib.connect('broker.test', alias='pub')
    pub = fake.instances[-1]
    lib.publish('t', 'to pub')
    assert lib.switch_connection('sub') == 'pub'
    lib.publish('t', 'to sub')
    lib.publish('t', 'explicit', alias='pub')
    assert pub.published == [('t', 'to pub', 0, False),
                             ('t', 'explicit', 0, False)]
    assert sub.published == [('t', 'to sub', 0, False)]


def test_switch_to_unknown_alias_fails(lib):
    with pytest.raises(RuntimeError, match="^No connection with alias 'x'.$"):
        lib.switch_connection('x')


def test_keywords_without_a_connection_fail(lib):
    with pytest.raises(RuntimeError, match="^No connection with alias "
                       "'default'. Use Connect first.$"):
        lib.publish('t', 'm')


def test_disconnect_and_unsubscribe_without_a_connection_do_nothing(lib):
    lib.unsubscribe('t')
    lib.disconnect()


# Disconnect


def test_disconnect_stops_the_loop(lib, client):
    lib.disconnect()
    assert client.disconnects == 1
    assert client.stopped
    assert lib._connections == {}


def test_disconnect_without_confirmation_warns(lib, client, log):
    client.disconnect_reason = None
    lib.disconnect()
    assert client.stopped
    assert log.warnings == ['The broker did not confirm the disconnect of '
                            'broker.test:1883 within 0.05 seconds']


def test_disconnect_does_not_wait_for_a_stuck_loop(lib, client, log):
    client.stuck = True
    start = time.monotonic()
    lib.disconnect()
    assert time.monotonic() - start < 1
    assert log.warnings == ['The broker did not confirm the disconnect of '
                            'broker.test:1883 within 0.05 seconds']
    client.stuck = False
    client.loop_thread.join()


def test_disconnect_after_the_loop_ended_by_itself(lib, client):
    client._thread_terminate = True
    client.loop_thread.join()
    assert client._thread is None
    lib.disconnect()
    assert client.stopped


def test_disconnect_after_a_lost_connection_fails(lib, client):
    client.fire_disconnect(reason(PacketTypes.DISCONNECT, 'Session taken over'))
    with pytest.raises(RuntimeError, match='^The client disconnected '
                       'unexpectedly: Session taken over$'):
        lib.disconnect()
    assert client.disconnects == 0
    assert client.stopped


def test_disconnect_all_tries_every_connection(lib, fake):
    for alias in ('one', 'two', 'three'):
        lib.connect('broker.test', alias=alias)
    one, two, three = fake.instances
    two.fire_disconnect(reason(PacketTypes.DISCONNECT, 'Unspecified error'))
    with pytest.raises(RuntimeError, match='^Disconnect All failed for two: '
                       'The client disconnected unexpectedly: Unspecified '
                       'error$'):
        lib.disconnect_all()
    assert all(c.stopped for c in (one, two, three))
    assert lib._connections == {}
    assert lib._alias == 'default'


# Publish


def test_publish_waits_for_the_acknowledgement(lib, client):
    lib.publish('t', 'm', '1', True)
    assert client.published == [('t', 'm', 1, True)]


def test_publish_error_names_the_paho_code(lib, client):
    client.publish_rc = mqtt.MQTT_ERR_NO_CONN
    with pytest.raises(RuntimeError, match='^Publish to t failed: '
                       'MQTT_ERR_NO_CONN$'):
        lib.publish('t', 'm')


def test_publish_error_after_a_lost_connection_says_why(lib, client):
    client.fire_disconnect(reason(PacketTypes.DISCONNECT, 'Keep alive timeout'))
    client.publish_rc = mqtt.MQTT_ERR_NO_CONN
    with pytest.raises(RuntimeError, match=r'^Publish to t failed: '
                       r'MQTT_ERR_NO_CONN \(connection lost: Keep alive '
                       r'timeout\)$'):
        lib.publish('t', 'm')


def test_publish_unknown_error_code(lib, client):
    client.publish_rc = 99
    with pytest.raises(RuntimeError, match='^Publish to t failed: 99$'):
        lib.publish('t', 'm')


def test_publish_without_acknowledgement_fails(lib, client):
    client.puback = False
    with pytest.raises(RuntimeError, match='^Publish to t not acknowledged '
                       'within 0.05 seconds$'):
        lib.publish('t', 'm', 1)


# Subscribe and Unsubscribe


def test_refused_subscription_fails_and_drops_the_filter(lib, client):
    client.suback = [reason(PacketTypes.SUBACK, 'Unspecified error')]
    with pytest.raises(RuntimeError, match='^Subscribe to a failed: '
                       'Unspecified error$'):
        lib.subscribe('a', 1, timeout=0)
    assert lib.listen('a', timeout=0) == []


def test_refused_repeat_subscription_keeps_the_filter(lib, client):
    lib.subscribe('a', 1, timeout=0)
    client.fire_message('a', 'one')
    client.suback = [reason(PacketTypes.SUBACK, 'Unspecified error')]
    with pytest.raises(RuntimeError):
        lib.subscribe('a', 1, timeout=0)
    assert lib.listen('a', timeout=0) == ['one']


def test_failed_subscribe_keeps_unclaimed_messages(lib, client):
    client.fire_message('a', 'queued')
    client.suback = None
    with pytest.raises(RuntimeError, match='not acknowledged'):
        lib.subscribe('a', 1, timeout=0)
    client.suback = [reason(PacketTypes.SUBACK, 'Granted QoS 1')]
    assert lib.subscribe('a', 1, timeout='1 s') == ['queued']


def test_late_suback_does_not_answer_a_later_subscribe(lib, client):
    client.suback = None
    with pytest.raises(RuntimeError, match='not acknowledged'):
        lib.subscribe('a', 1, timeout=0)
    late_mid = client._mid
    conn = lib._connections['default']
    client.on_subscribe(client, None, late_mid,
                        [reason(PacketTypes.SUBACK, 'Granted QoS 1')], None)
    assert conn._acks == {}
    assert conn._abandoned == set()


def test_subscribe_error_names_the_paho_code(lib, client):
    client.subscribe_rc = mqtt.MQTT_ERR_NO_CONN
    with pytest.raises(RuntimeError, match='^Subscribe to a failed: '
                       'MQTT_ERR_NO_CONN$'):
        lib.subscribe('a', 1, timeout=0)


def test_subscribe_without_suback_fails(lib, client):
    client.suback = None
    with pytest.raises(RuntimeError, match='^Subscribe to a not acknowledged '
                       'within 0.05 seconds$'):
        lib.subscribe('a', 1, timeout=0)


def test_unsubscribe_without_unsuback_warns(lib, client, log):
    lib.subscribe('a', 1, timeout=0)
    client.unsuback = None
    lib.unsubscribe('a')
    assert log.warnings == ["Client didn't receive an unsubscribe callback"]
    assert lib.listen('a', timeout=0) == []


def test_unsubscribe_error_fails_and_drops_the_filter(lib, client):
    lib.subscribe('a', 1, timeout=0)
    client.unsubscribe_rc = mqtt.MQTT_ERR_NO_CONN
    with pytest.raises(RuntimeError, match='^Unsubscribe from a failed: '
                       'MQTT_ERR_NO_CONN$'):
        lib.unsubscribe('a')
    assert lib.listen('a', timeout=0) == []


# Publish Single and Publish Multiple


@pytest.mark.parametrize('given, expected', [
    (3, mqtt.MQTTv31),
    ('4', mqtt.MQTTv311),
    ('MQTTv311', mqtt.MQTTv311),
    ('mqttv5', mqtt.MQTTv5),
    (' MQTTv31 ', mqtt.MQTTv31),
])
def test_publish_single_protocol(lib, monkeypatch, given, expected):
    calls = []
    monkeypatch.setattr('paho.mqtt.publish.single',
                        lambda *args: calls.append(args))
    lib.publish_single('t', 'm', protocol=given)
    assert calls[0][-1] is expected


def test_publish_multiple_protocol_default(lib, monkeypatch):
    calls = []
    monkeypatch.setattr('paho.mqtt.publish.multiple',
                        lambda *args: calls.append(args))
    lib.publish_multiple([{'topic': 't'}])
    assert calls[0][-1] is mqtt.MQTTv31


@pytest.mark.parametrize('given', [7, 'MQTTv4', ''])
def test_unknown_protocol_fails(lib, given):
    with pytest.raises(RuntimeError, match='^Unknown MQTT protocol version: '):
        lib.publish_single('t', 'm', protocol=given)
