from paho.mqtt.matcher import MQTTMatcher
import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
import robot
import time
import re

from robot.libraries.DateTime import convert_time
from robot.api import logger

# https://github.com/eclipse/paho.mqtt.python/blob/1eec03edf39128e461e6729694cf5d7c1959e5e4/src/paho/mqtt/client.py#L250
def topic_matches_sub(sub, topic):
    """Check whether a topic matches a subscription.
    For example:
    foo/bar would match the subscription foo/# or +/bar
    non/matching would not match the subscription non/+/+
    """
    matcher = MQTTMatcher()
    matcher[sub] = True
    try:
        next(matcher.iter_match(topic))
        return True
    except StopIteration:
        return False

class MQTTKeywords(object):

    # Timeout used for all blocking loop* functions. This serves as a
    # safeguard to not block forever, in case of unexpected/unhandled errors
    LOOP_TIMEOUT = '5 seconds'

    def __init__(self, loop_timeout=LOOP_TIMEOUT):
        self._loop_timeout = convert_time(loop_timeout)
        self._background_mqttc = None
        self._messages = {}
        self._username = None
        self._password = None
        #self._mqttc = mqtt.Client()

    def set_username_and_password(self, username, password=None):
        self._username = username
        self._password = password

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
        logger.info('Connecting to %s at port %s' % (broker, port))
        self._connected = False
        self._unexpected_disconnect = False
        self._mqttc = mqtt.Client(client_id, clean_session)

        # set callbacks
        self._mqttc.on_connect = self._on_connect
        self._mqttc.on_disconnect = self._on_disconnect

        if self._username:
            self._mqttc.username_pw_set(self._username, self._password)

        self._mqttc.connect(broker, int(port))

        timer_start = time.time()
        while time.time() < timer_start + self._loop_timeout:
            if self._connected or self._unexpected_disconnect:
                break;
            self._mqttc.loop()

        if self._unexpected_disconnect:
            raise RuntimeError("The client disconnected unexpectedly")
        logger.debug('client_id: %s' % self._mqttc._client_id)
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
        logger.info('Publish topic: %s, message: %s, qos: %s, retain: %s'
            % (topic, message, qos, retain))
        self._mid = -1
        self._mqttc.on_publish = self._on_publish
        result, mid = self._mqttc.publish(topic, message, int(qos), retain)
        if result != 0:
            raise RuntimeError('Error publishing: %s' % result)

        timer_start = time.time()
        while time.time() < timer_start + self._loop_timeout:
            if mid == self._mid:
                break;
            self._mqttc.loop()

        if mid != self._mid:
            logger.warn('mid wasn\'t matched: %s' % mid)

    def subscribe(self, topic, qos, timeout=1, limit=1):
        """ Subscribe to a topic and return a list of message payloads received
            within the specified time.

        `topic` topic to subscribe to

        `qos` quality of service for the subscription

        `timeout` duration of subscription. Specify 0 to enable background looping (async)

        `limit` the max number of payloads that will be returned. Specify 0
            for no limit

        Examples:

        Subscribe and get a list of all messages received within 5 seconds
        | ${messages}= | Subscribe | test/test | qos=1 | timeout=5 | limit=0 |

        Subscribe and get 1st message received within 60 seconds
        | @{messages}= | Subscribe | test/test | qos=1 | timeout=60 | limit=1 |
        | Length should be | ${messages} | 1 |

        """
        seconds = convert_time(timeout)
        self._messages[topic] = []
        limit = int(limit)
        self._subscribed = False

        logger.info('Subscribing to topic: %s' % topic)
        self._mqttc.on_subscribe = self._on_subscribe
        self._mqttc.subscribe(str(topic), int(qos))

        self._mqttc.on_message = self._on_message_list

        if seconds == 0:
            logger.info('Starting background loop')
            self._background_mqttc = self._mqttc
            self._background_mqttc.loop_start()
            return self._messages[topic]

        timer_start = time.time()
        while time.time() < timer_start + seconds:
            if limit == 0 or len(self._messages[topic]) < limit:
                self._mqttc.loop()
            else:
                # workaround for client to ack the publish. Otherwise,
                # it seems that if client disconnects quickly, broker
                # will not get the ack and publish the message again on
                # next connect.
                time.sleep(1)
                break
        return self._messages[topic]

    def listen(self, topic, timeout=1, limit=1):
        """ Listen to a topic and return a list of message payloads received
            within the specified time. Requires an async Subscribe to have been called previously.

        `topic` topic to listen to

        `timeout` duration to listen

        `limit` the max number of payloads that will be returned. Specify 0
            for no limit

        Examples:

        Listen and get a list of all messages received within 5 seconds
        | ${messages}= | Listen | test/test | timeout=5 | limit=0 |

        Listen and get 1st message received within 60 seconds
        | @{messages}= | Listen | test/test | timeout=60 | limit=1 |
        | Length should be | ${messages} | 1 |

        """
        timer_start = time.time()
        while time.time() < timer_start + self._loop_timeout:
            if self._subscribed:
                break;
            time.sleep(1)
        if not self._subscribed:
            logger.warn('Cannot listen when not subscribed to a topic')
            return []

        if topic not in self._messages:
            logger.warn('Cannot listen when not subscribed to topic: %s' % topic)
            return []

        # If enough messages have already been gathered, return them
        if limit != 0 and len(self._messages[topic]) >= limit:
            messages = self._messages[topic][:]  # Copy the list's contents
            self._messages[topic] = []
            return messages[-limit:]

        seconds = convert_time(timeout)
        limit = int(limit)

        logger.info('Listening on topic: %s' % topic)
        timer_start = time.time()
        while time.time() < timer_start + seconds:
            if limit == 0 or len(self._messages[topic]) < limit:
                # If the loop is running in the background
                # merely sleep here for a second or so and continue
                # otherwise, do the loop ourselves
                if self._background_mqttc:
                    time.sleep(1)
                else:
                    self._mqttc.loop()
            else:
                # workaround for client to ack the publish. Otherwise,
                # it seems that if client disconnects quickly, broker
                # will not get the ack and publish the message again on
                # next connect.
                time.sleep(1)
                break

        messages = self._messages[topic][:]  # Copy the list's contents
        self._messages[topic] = []
        return messages[-limit:] if limit != 0 else messages

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

        logger.info('Subscribing to topic: %s' % topic)
        self._payload = str(payload)
        self._mqttc.on_message = self._on_message
        self._mqttc.subscribe(str(topic), int(qos))

        timer_start = time.time()
        while time.time() < timer_start + seconds:
            if self._verified:
                break
            self._mqttc.loop()

        if not self._verified:
            raise AssertionError("The expected payload didn't arrive in the topic")

    def unsubscribe(self, topic):
        """ Unsubscribe the client from the specified topic.

        `topic` topic to unsubscribe from

        Example:
        | Unsubscribe | test/mqtt_test |

        """
        try:
            tmp = self._mqttc
        except AttributeError:
            logger.info('No MQTT Client instance found so nothing to unsubscribe from.')
            return

        if self._background_mqttc:
            logger.info('Closing background loop')
            self._background_mqttc.loop_stop()
            self._background_mqttc = None

        if topic in self._messages:
            del self._messages[topic]

        logger.info('Unsubscribing from topic: %s' % topic)
        self._unsubscribed = False
        self._mqttc.on_unsubscribe = self._on_unsubscribe
        self._mqttc.unsubscribe(str(topic))

        timer_start = time.time()
        while (not self._unsubscribed and
                time.time() < timer_start + self._loop_timeout):
            self._mqttc.loop()

        if not self._unsubscribed:
            logger.warn('Client didn\'t receive an unsubscribe callback')

    def disconnect(self):
        """ Disconnect from MQTT Broker.

        Example:
        | Disconnect |

        """
        try:
            tmp = self._mqttc
        except AttributeError:
            logger.info('No MQTT Client instance found so nothing to disconnect from.')
            return

        self._disconnected = False
        self._unexpected_disconnect = False
        self._mqttc.on_disconnect = self._on_disconnect
        self._mqttc.disconnect()

        timer_start = time.time()
        while time.time() < timer_start + self._loop_timeout:
            if self._disconnected or self._unexpected_disconnect:
                break;
            self._mqttc.loop()
        if self._unexpected_disconnect:
            raise RuntimeError("The client disconnected unexpectedly")

    def publish_single(self, topic, payload=None, qos=0, retain=False,
            hostname="localhost", port=1883, client_id="", keepalive=60,
            will=None, auth=None, tls=None, protocol=mqtt.MQTTv31):

        """ Publish a single message and disconnect. This keyword uses the
        [http://eclipse.org/paho/clients/python/docs/#single|single]
        function of publish module.

        `topic` topic to which the message will be published

        `payload` message payload to publish (default None)

        `qos` qos of the message (default 0)

        `retain` retain flag (True or False, default False)

        `hostname` MQTT broker host (default localhost)

        `port` broker port (default 1883)

        `client_id` if not specified, a random id is generated

        `keepalive` keepalive timeout value for client

        `will` a dict containing will parameters for client:
            will = {'topic': "<topic>", 'payload':"<payload">, 'qos':<qos>,
                'retain':<retain>}

        `auth` a dict containing authentication parameters for the client:
            auth = {'username':"<username>", 'password':"<password>"}

        `tls` a dict containing TLS configuration parameters for the client:
            dict = {'ca_certs':"<ca_certs>", 'certfile':"<certfile>",
                'keyfile':"<keyfile>", 'tls_version':"<tls_version>",
                'ciphers':"<ciphers">}

        `protocol` MQTT protocol version (MQTTv31 or MQTTv311)

        Example:

        Publish a message on specified topic and disconnect:
        | Publish Single | topic=t/mqtt | payload=test | hostname=127.0.0.1 |

        """
        logger.info('Publishing to: %s:%s, topic: %s, payload: %s, qos: %s' %
                    (hostname, port, topic, payload, qos))
        publish.single(topic, payload, qos, retain, hostname, port,
                        client_id, keepalive, will, auth, tls, protocol)

    def publish_multiple(self, msgs, hostname="localhost", port=1883,
            client_id="", keepalive=60, will=None, auth=None,
            tls=None, protocol=mqtt.MQTTv31):

        """ Publish multiple messages and disconnect. This keyword uses the
        [http://eclipse.org/paho/clients/python/docs/#multiple|multiple]
        function of publish module.

        `msgs` a list of messages to publish. Each message is either a dict
                or a tuple. If a dict, it must be of the form:
                msg = {'topic':"<topic>", 'payload':"<payload>", 'qos':<qos>,
                        'retain':<retain>}
                Only the topic must be present. Default values will be used
                for any missing arguments. If a tuple, then it must be of the
                form:
                ("<topic>", "<payload>", qos, retain)

                See `publish single` for the description of hostname, port,
                client_id, keepalive, will, auth, tls, protocol.

        Example:

        | ${msg1} | Create Dictionary | topic=${topic} | payload=message 1 |
        | ${msg2} | Create Dictionary | topic=${topic} | payload=message 2 |
        | ${msg3} | Create Dictionary | topic=${topic} | payload=message 3 |
        | @{msgs} | Create List | ${msg1} | ${msg2} | ${msg3} |
        | Publish Multiple | msgs=${msgs} | hostname=127.0.0.1 |

        """
        logger.info('Publishing to: %s:%s, msgs: %s' %
                    (hostname, port, msgs))
        publish.multiple(msgs, hostname, port, client_id, keepalive,
                        will, auth, tls, protocol)

    def _on_message(self, client, userdata, message):
        payload = message.payload.decode('utf-8')
        logger.debug('Received message: %s on topic: %s with QoS: %s'
            % (payload, message.topic, str(message.qos)))
        self._verified = re.match(self._payload, payload)

    def _on_message_list(self, client, userdata, message):
        payload = message.payload.decode('utf-8')
        logger.debug('Received message: %s on topic: %s with QoS: %s'
            % (payload, message.topic, str(message.qos)))
        if message.topic not in self._messages:
            self._messages[message.topic] = []
        for sub in self._messages:
            if topic_matches_sub(sub, message.topic):
                self._messages[sub].append(payload)

    def _on_connect(self, client, userdata, flags, rc):
        self._connected = True if rc == 0 else False

    def _on_disconnect(self, client, userdata, rc):
        if rc == 0:
            self._disconnected = True
            self._unexpected_disconnect = False
        else:
            self._unexpected_disconnect = True

    def _on_subscribe(self, client, userdata, mid, granted_qos):
        self._subscribed = True

    def _on_unsubscribe(self, client, userdata, mid):
        self._unsubscribed = True

    def _on_publish(self, client, userdata, mid):
        self._mid = mid
