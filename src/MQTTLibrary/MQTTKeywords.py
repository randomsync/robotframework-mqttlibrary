import paho.mqtt.client as mqtt 
import robot
import time
import re

from robot.libraries.BuiltIn import BuiltIn
from robot.libraries.DateTime import convert_time

class MQTTKeywords(object):

    def __init__(self):
        self.builtin = BuiltIn()
        #self._mqttc = mqtt.Client()

    def connect(self, broker, port=1883, client_id="", clean_session=True):

        """ Connect to an MQTT broker. This is a pre-requisite step for publish
        and subscribe keywords.

        `broker` MQTT broker host

        `port` broker port (default 1883)

        `client_id` if not specified, a random id is generated

        `clean_session` specifies the clean session flag for the connection

        Examples:

        Connect to a broker with default port and client id
        | Connect | 127.0.0.1 |

        Connect to a broker by specifying the port and client id explicitly
        | Connect | 127.0.0.1 | 1883 | test.client |

        Connect to a broker with clean session flag set to false
        | Connect | 127.0.0.1 | clean_session=${false} |

        """
        self.builtin.log('Connecting to %s at port %s' % (broker, port), 'INFO')
        self._mqttc = mqtt.Client(client_id, clean_session)
        self._mqttc.connect(broker, int(port))
        self.builtin.log('client_id: %s' % self._mqttc._client_id, 'DEBUG')
        return self._mqttc

    def publish(self, topic, message=None, qos=0, retain=False):

        """ Publish a message to a topic with specified qos and retained flag.
        It is required that a connection has been established using `Connect`
        keyword before using this keyword.

        `topic` topic to which the message will be published

        `message` message payload to publish

        `qos` qos of the message

        `retain` retained flag

        Examples:

        | Publish | test/test | test message | 1 | ${false} |

        """
        self.builtin.log('Publish topic: %s, message: %s, qos: %s, retain: %s'
            % (topic, message, qos, retain), 'INFO')
        self._mqttc.publish(topic, message, int(qos), retain)

    def subscribe_and_validate(self, topic, qos, payload, timeout=1):

        """ Subscribe to a topic and validate that the specified payload is
        received within timeout. It is required that a connection has been
        established using `Connect` keyword. The payload can be specified as
        a python regular expression. If the specified payload is not received
        within timeout, an AssertionError is thrown.

        `topic` topic to subscribe to

        `qos` quality of service for the subscription

        `payload` payload (message) that is expected to arrive

        `timeout` time to wait for the payload to arrive

        Examples:

        | Subscribe And Validate | test/test | 1 | test message |

        """
        seconds = convert_time(timeout)
        self._verified = False

        self.builtin.log('Subscribing to topic: %s' % topic, 'INFO')
        self._mqttc.subscribe(str(topic), int(qos))
        self._payload = str(payload)
        self._mqttc.on_message = self._on_message

        timer_start = time.time()
        while time.time() < timer_start + seconds:
            if self._verified:
                break
            self._mqttc.loop()

        if not self._verified:
            raise AssertionError("The expected payload didn't arrive in the topic")

    def disconnect(self):

        """ Disconnect from MQTT Broker.

        Example:
        | Disconnect |

        """
        self._mqttc.disconnect()

    def _on_message(self, client, userdata, message):
        self.builtin.log('Received message: %s on topic: %s with QoS: %s'
            % (str(message.payload), message.topic, str(message.qos)), 'DEBUG')
        self._verified = re.match(self._payload, str(message.payload))
