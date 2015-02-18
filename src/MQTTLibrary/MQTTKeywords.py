import paho.mqtt.client as mqtt 
import robot

from robot.libraries.BuiltIn import BuiltIn

class MQTTKeywords(object):
    ROBOT_LIBRARY_SCOPE = 'Global'

    def __init__(self):
        self.builtin = BuiltIn()
        #self.mqttc = mqtt.Client()

    def connect(self, broker, port=1883, client_id=""):

        """ Connect to an MQTT broker. This is a pre-requisite step for publish and subscribe keywords.

        `broker` MQTT broker host

        `port` broker port (default 1883)

        `client_id` if not specified, a random id is generated

        Example:
        | Connect | 127.0.0.1 | 1883 | test.client |

        """
        self.builtin.log('Connecting to broker: %s' % broker, 'INFO')
        self.mqttc = mqtt.Client(client_id)
        self.mqttc.connect(broker, int(port))


    def publish(self, topic, message=None, qos=0, retain=False):

        """ Publish a message to a topic with specified qos and retained flag.

        `topic` topic to which the message will be published

        `message` message payload to publish

        `qos` qos of the message

        `retain` retained flag

        Example:
        | Publish | test/test | test message | 1 | ${false} |

        """
        self.builtin.log('Publish topic: %s, message: %s, qos: %s, retain: %s' % (topic, message, qos, retain), 'INFO')
        self.mqttc.publish(topic, message, int(qos), retain)

    def disconnect(self):

        """ Disconnect from MQTT Broker.

        Example:
        | Disconnect |

        """
        self.mqttc.disconnect()



