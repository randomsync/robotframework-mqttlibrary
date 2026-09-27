import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish

from robot.libraries.DateTime import convert_time
from robot.api import logger

from MQTTLibrary.connection import _Connection

# paho 2 defines the protocol versions as an IntEnum. A plain int default keeps
# Robot Framework converting the argument as an int, as it did with paho 1.
MQTT_V31 = int(mqtt.MQTTv31)

_PROTOCOLS = {
    'mqttv31': mqtt.MQTTv31,
    'mqttv311': mqtt.MQTTv311,
    'mqttv5': mqtt.MQTTv5,
}

DEFAULT_ALIAS = 'default'


def _protocol(value):
    """Accept a protocol version as a name (MQTTv311) or a number (4)."""
    name = str(value).strip().lower()
    if name in _PROTOCOLS:
        return _PROTOCOLS[name]
    try:
        return mqtt.MQTTProtocolVersion(int(name))
    except ValueError:
        raise RuntimeError('Unknown MQTT protocol version: %s. Use MQTTv31, '
                           'MQTTv311 or MQTTv5.' % value) from None


class MQTTKeywords(object):

    # Timeout used for all blocking operations: connect, acknowledgements and
    # disconnect. This serves as a safeguard to not block forever, in case of
    # unexpected/unhandled errors
    LOOP_TIMEOUT = '5 seconds'

    def __init__(self, loop_timeout=LOOP_TIMEOUT):
        self._loop_timeout = convert_time(loop_timeout)
        self._connections = {}
        self._alias = DEFAULT_ALIAS
        self._username = None
        self._password = None

    def _connection(self, alias):
        alias = alias or self._alias
        try:
            return self._connections[alias]
        except KeyError:
            raise RuntimeError("No connection with alias '%s'. Use Connect "
                               "first." % alias) from None

    def set_username_and_password(self, username, password=None):
        self._username = username
        self._password = password

    def connect(self, broker, port=1883, client_id="", clean_session=True,
                keepalive=60, alias=None):
        """ Connect to an MQTT broker. This is a pre-requisite step for publish
        and subscribe keywords.

        The connection is serviced by a background network loop until
        `Disconnect`, so keepalive pings and acknowledgements are handled
        between keywords.

        `broker` MQTT broker host

        `port` broker port (default 1883)

        `client_id` if not specified, a random id is generated

        `clean_session` specifies the clean session flag for the connection

        `keepalive` seconds between keepalive pings (default 60)

        `alias` names the connection so that several can be open at once.
        Other keywords take the same `alias` argument; without one they use
        the connection opened or switched to last. Default `default`.
        Connecting again on an alias that is still connected disconnects the
        old connection first, with a warning.

        Fails with the broker's reason, for example
        `Connection to 127.0.0.1:11883 failed: Not authorized`, if the broker
        refuses the connection or does not answer within the library's
        timeout.

        Examples:

        Connect to a broker with default port and client id
        | Connect | 127.0.0.1 |

        Connect to a broker by specifying the port and client id explicitly
        | Connect | 127.0.0.1 | 1883 | test.client |

        Connect to a broker with clean session flag set to false
        | Connect | 127.0.0.1 | clean_session=${false} |

        Open a subscriber and a publisher connection
        | Connect | 127.0.0.1 | alias=sub |
        | Connect | 127.0.0.1 | alias=pub |

        """
        alias = alias or DEFAULT_ALIAS
        old = self._connections.pop(alias, None)
        if old is not None:
            logger.warn("Connection '%s' to %s was still open. Disconnecting "
                        "it before connecting again." % (alias, old.address))
            try:
                old.close()
            except RuntimeError as exc:
                logger.warn(str(exc))

        logger.info('Connecting to %s at port %s' % (broker, port))
        conn = _Connection(alias, broker, int(port), client_id, clean_session,
                           int(keepalive), self._loop_timeout,
                           self._username, self._password)
        conn.open()
        self._connections[alias] = conn
        self._alias = alias
        logger.debug('client_id: %s' % conn.client._client_id)
        return conn.client

    def switch_connection(self, alias):
        """ Make the connection named `alias` the one that keywords use when
        they are called without an `alias`. Returns the previous alias.

        Example:
        | Connect | 127.0.0.1 | alias=sub |
        | Connect | 127.0.0.1 | alias=pub |
        | Switch Connection | sub |

        """
        if alias not in self._connections:
            raise RuntimeError("No connection with alias '%s'." % alias)
        previous, self._alias = self._alias, alias
        return previous

    def publish(self, topic, message=None, qos=0, retain=False, alias=None):
        """ Publish a message to a topic with specified qos and retained flag.
        It is required that a connection has been established using `Connect`
        keyword before using this keyword. Waits until the message is sent
        (qos 0) or acknowledged (qos 1 and 2), and fails if it is not within
        the library's timeout.

        `topic` topic to which the message will be published

        `message` message payload to publish

        `qos` qos of the message

        `retain` retained flag

        `alias` the connection to use (see `Connect`)

        Examples:

        | Publish | test/test | test message | 1 | ${false} |

        """
        logger.info('Publish topic: %s, message: %s, qos: %s, retain: %s'
            % (topic, message, qos, retain))
        self._connection(alias).publish(topic, message, int(qos), retain)

    def subscribe(self, topic, qos, timeout=1, limit=1, alias=None):
        """ Subscribe to a topic and return a list of message payloads received
            within the specified time. Waits for the broker to acknowledge the
            subscription, and fails if it refuses it.

        `topic` topic to subscribe to

        `qos` quality of service for the subscription

        `timeout` duration of subscription. Specify 0 to return immediately
            (async); read the messages later with `Listen`. Otherwise this is
            the same as `Listen` with the same `timeout` and `limit`.

        `limit` the max number of payloads that will be returned. Specify 0
            for no limit. The oldest messages are returned first; the rest
            stay queued for the next `Listen` on the same connection.

        `alias` the connection to use (see `Connect`)

        Examples:

        Subscribe and get a list of all messages received within 5 seconds
        | ${messages}= | Subscribe | test/test | qos=1 | timeout=5 | limit=0 |

        Subscribe and get 1st message received within 60 seconds
        | @{messages}= | Subscribe | test/test | qos=1 | timeout=60 | limit=1 |
        | Length should be | ${messages} | 1 |

        """
        seconds = convert_time(timeout)
        conn = self._connection(alias)
        logger.info('Subscribing to topic: %s' % topic)
        conn.subscribe(str(topic), int(qos))
        if seconds == 0:
            return []
        return conn.listen(str(topic), seconds, int(limit))

    def listen(self, topic, timeout=1, limit=1, alias=None):
        """ Listen to a topic and return a list of message payloads received
            within the specified time. Requires a Subscribe to have been called previously.

        Messages are queued from the moment of `Subscribe`, so none are lost
        between two calls. Fails if the connection is lost and no message is
        queued.

        `topic` topic to listen to

        `timeout` duration to listen. Returns as soon as `limit` messages
            are available.

        `limit` the max number of payloads that will be returned. Specify 0
            for no limit. The oldest messages are returned first; the rest
            stay queued for the next `Listen`.

        `alias` the connection to use (see `Connect`)

        Examples:

        Listen and get a list of all messages received within 5 seconds
        | ${messages}= | Listen | test/test | timeout=5 | limit=0 |

        Listen and get 1st message received within 60 seconds
        | @{messages}= | Listen | test/test | timeout=60 | limit=1 |
        | Length should be | ${messages} | 1 |

        """
        seconds = convert_time(timeout)
        logger.info('Listening on topic: %s' % topic)
        messages = self._connection(alias).listen(str(topic), seconds,
                                                  int(limit))
        if messages is None:
            logger.warn('Cannot listen when not subscribed to topic: %s' % topic)
            return []
        return messages

    def subscribe_and_validate(self, topic, qos, payload, timeout=1,
                               alias=None):
        """ Subscribe to a topic and validate that the specified payload is
        received within timeout. It is required that a connection has been
        established using `Connect` keyword. The payload can be specified as
        a python regular expression. If the specified payload is not received
        within timeout, an AssertionError is thrown. Messages that do not
        match are consumed.

        `topic` topic to subscribe to

        `qos` quality of service for the subscription

        `payload` payload (message) that is expected to arrive

        `timeout` time to wait for the payload to arrive

        `alias` the connection to use (see `Connect`)

        Examples:

        | Subscribe And Validate | test/test | 1 | test message |

        """
        seconds = convert_time(timeout)
        conn = self._connection(alias)
        logger.info('Subscribing to topic: %s' % topic)
        conn.subscribe(str(topic), int(qos))
        if not conn.validate(str(topic), str(payload), seconds):
            raise AssertionError("The expected payload didn't arrive in the topic")

    def unsubscribe(self, topic, alias=None):
        """ Unsubscribe the client from the specified topic. Messages still
        queued for the topic are dropped. Other subscriptions on the
        connection are not affected.

        `topic` topic to unsubscribe from

        `alias` the connection to use (see `Connect`)

        Example:
        | Unsubscribe | test/mqtt_test |

        """
        alias = alias or self._alias
        conn = self._connections.get(alias)
        if conn is None:
            logger.info('No MQTT connection found so nothing to unsubscribe from.')
            return

        logger.info('Unsubscribing from topic: %s' % topic)
        if not conn.unsubscribe(str(topic)):
            logger.warn('Client didn\'t receive an unsubscribe callback')

    def disconnect(self, alias=None):
        """ Disconnect from MQTT Broker and stop the connection's network
        loop. Does nothing if there is no such connection.

        `alias` the connection to disconnect (see `Connect`)

        Example:
        | Disconnect |

        """
        alias = alias or self._alias
        conn = self._connections.pop(alias, None)
        if conn is None:
            logger.info('No MQTT connection found so nothing to disconnect from.')
            return
        if not conn.close():
            logger.warn('The broker did not confirm the disconnect of %s '
                        'within %s seconds' % (conn.address, conn.timeout))

    def disconnect_all(self):
        """ Disconnect every open connection. Tries all of them, then fails
        if any failed.

        Example:
        | [Teardown] | Disconnect All |

        """
        errors = []
        for alias in list(self._connections):
            try:
                self.disconnect(alias)
            except Exception as exc:
                errors.append('%s: %s' % (alias, exc))
        self._alias = DEFAULT_ALIAS
        if errors:
            raise RuntimeError('Disconnect All failed for %s'
                               % '; '.join(errors))

    def publish_single(self, topic, payload=None, qos=0, retain=False,
            hostname="localhost", port=1883, client_id="", keepalive=60,
            will=None, auth=None, tls=None, protocol=MQTT_V31):

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

        `protocol` MQTT protocol version, as a name (MQTTv31, MQTTv311 or
            MQTTv5) or a number (3, 4 or 5). Default MQTTv31.

        Example:

        Publish a message on specified topic and disconnect:
        | Publish Single | topic=t/mqtt | payload=test | hostname=127.0.0.1 |

        """
        logger.info('Publishing to: %s:%s, topic: %s, payload: %s, qos: %s' %
                    (hostname, port, topic, payload, qos))
        publish.single(topic, payload, qos, retain, hostname, port,
                        client_id, keepalive, will, auth, tls,
                        _protocol(protocol))

    def publish_multiple(self, msgs, hostname="localhost", port=1883,
            client_id="", keepalive=60, will=None, auth=None,
            tls=None, protocol=MQTT_V31):

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
                        will, auth, tls, _protocol(protocol))
