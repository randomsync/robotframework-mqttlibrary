"""A fake paho client, so the unit tests need no broker.

The fake answers synchronously: CONNACK arrives in ``loop_start()``, SUBACK
inside ``subscribe()`` and so on, which also covers the case where an
acknowledgement arrives before the keyword starts waiting for it. Set an
answer to None to make the broker stay silent.
"""

import importlib
import threading
import time

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode

from MQTTLibrary import MQTTLibrary as Library

# The package exports the MQTTKeywords class under the module's name, so
# import the modules explicitly.
connection = importlib.import_module('MQTTLibrary.connection')
keywords = importlib.import_module('MQTTLibrary.MQTTKeywords')


def reason(packet_type, name):
    return ReasonCode(packet_type, name)


class FakeClient(object):

    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.connect_timeout = None
        self.credentials = None
        self.connect_args = None
        self.connect_error = None
        self.connack = reason(PacketTypes.CONNACK, 'Success')
        self.suback = [reason(PacketTypes.SUBACK, 'Granted QoS 1')]
        self.unsuback = [reason(PacketTypes.UNSUBACK, 'Success')]
        self.subscribe_rc = mqtt.MQTT_ERR_SUCCESS
        self.unsubscribe_rc = mqtt.MQTT_ERR_SUCCESS
        self.publish_rc = mqtt.MQTT_ERR_SUCCESS
        self.puback = True
        self.disconnect_reason = reason(PacketTypes.DISCONNECT,
                                        'Normal disconnection')
        self.loop_starts = 0
        self.stuck = False
        self._thread_terminate = False
        self.disconnects = 0
        self.subscriptions = []
        self.unsubscriptions = []
        self.published = []
        self._client_id = kwargs.get('client_id', '').encode()
        self._thread = None
        self._mid = 0
        FakeClient.instances.append(self)

    def _next_mid(self):
        self._mid += 1
        return self._mid

    def username_pw_set(self, username, password=None):
        self.credentials = (username, password)

    def connect(self, host, port, keepalive):
        self.connect_args = (host, port, keepalive)
        if self.connect_error is not None:
            raise self.connect_error

    def loop_start(self):
        self.loop_starts += 1
        self.loop_thread = threading.Thread(target=self._loop_forever,
                                            daemon=True)
        self._thread = self.loop_thread
        self.loop_thread.start()
        if self.connack is not None:
            self.on_connect(self, None, None, self.connack, None)

    def _loop_forever(self):
        # Runs until the library sets _thread_terminate, like paho's loop.
        # With `stuck`, it ignores that, like a loop that cannot write.
        while not self._thread_terminate or self.stuck:
            time.sleep(0.001)
        # paho 2.1 clears its reference when the loop ends.
        self._thread = None

    @property
    def stopped(self):
        return self._thread_terminate and not self.loop_thread.is_alive()

    def disconnect(self):
        self.disconnects += 1
        if self.disconnect_reason is not None:
            self.fire_disconnect(self.disconnect_reason)

    def subscribe(self, topic, qos):
        mid = self._next_mid()
        self.subscriptions.append((topic, qos))
        if self.subscribe_rc == mqtt.MQTT_ERR_SUCCESS and self.suback:
            self.on_subscribe(self, None, mid, self.suback, None)
        return self.subscribe_rc, mid

    def unsubscribe(self, topic):
        mid = self._next_mid()
        self.unsubscriptions.append(topic)
        if self.unsubscribe_rc == mqtt.MQTT_ERR_SUCCESS and self.unsuback:
            self.on_unsubscribe(self, None, mid, self.unsuback, None)
        return self.unsubscribe_rc, mid

    def publish(self, topic, payload, qos, retain):
        info = mqtt.MQTTMessageInfo(self._next_mid())
        info.rc = self.publish_rc
        self.published.append((topic, payload, qos, retain))
        if self.publish_rc == mqtt.MQTT_ERR_SUCCESS and self.puback:
            info._set_as_published()
        return info

    # Broker-side events.

    def fire_message(self, topic, payload, qos=0):
        message = mqtt.MQTTMessage(topic=topic.encode())
        if isinstance(payload, str):
            payload = payload.encode()
        message.payload = payload
        message.qos = qos
        self.on_message(self, None, message)

    def fire_disconnect(self, reason_code):
        self.on_disconnect(self, None, None, reason_code, None)


class Recorder(object):
    """Stands in for robot.api.logger and records warnings."""

    def __init__(self):
        self.warnings = []

    def warn(self, message):
        self.warnings.append(message)

    def info(self, message):
        pass

    def debug(self, message):
        pass


@pytest.fixture
def fake(monkeypatch):
    FakeClient.instances = []
    monkeypatch.setattr(connection.mqtt, 'Client', FakeClient)
    return FakeClient


@pytest.fixture
def log(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(keywords, 'logger', recorder)
    monkeypatch.setattr(connection, 'logger', recorder)
    return recorder


@pytest.fixture
def lib(fake, log):
    return Library(loop_timeout='0.05 seconds')


@pytest.fixture
def client(lib):
    """Connect on the default alias and return the fake client."""
    lib.connect('broker.test')
    return FakeClient.instances[-1]
