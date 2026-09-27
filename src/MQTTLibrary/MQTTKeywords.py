from datetime import timedelta
from typing import Optional, Union

import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
from robot.api import logger
from robot.libraries.DateTime import convert_time

from MQTTLibrary.connection import _Connection

# paho 2 defines the protocol versions as an IntEnum. A plain int default keeps
# Robot Framework converting the argument as an int, as it did with paho 1.
MQTT_V31 = int(mqtt.MQTTv31)

_PROTOCOLS = {
    "mqttv31": mqtt.MQTTv31,
    "mqttv311": mqtt.MQTTv311,
    "mqttv5": mqtt.MQTTv5,
}

DEFAULT_ALIAS = "default"

# What paho accepts as a message payload.
Payload = Union[str, bytes, bytearray, int, float, None]


def _protocol(value):
    """Accept a protocol version as a name (MQTTv311) or a number (4)."""
    name = str(value).strip().lower()
    if name in _PROTOCOLS:
        return _PROTOCOLS[name]
    try:
        return mqtt.MQTTProtocolVersion(int(name))
    except ValueError:
        raise RuntimeError(
            "Unknown MQTT protocol version: %s. Use MQTTv31, "
            "MQTTv311 or MQTTv5." % value
        ) from None


def _seconds(value):
    """Seconds from a timedelta (converted by Robot Framework) or from a
    number or time string (when called from Python)."""
    if isinstance(value, timedelta):
        return value.total_seconds()
    return convert_time(value)


class MQTTKeywords(object):
    # Timeout used for all blocking operations: connect, acknowledgements and
    # disconnect. This serves as a safeguard to not block forever, in case of
    # unexpected/unhandled errors
    LOOP_TIMEOUT = "5 seconds"

    def __init__(self, loop_timeout=LOOP_TIMEOUT):
        """``loop_timeout`` bounds every wait for the broker: the TCP connect
        and CONNACK in `Connect`, the acknowledgements in `Publish`,
        `Subscribe` and `Unsubscribe`, and the disconnect in `Disconnect`.
        It is a Robot Framework time string or a number of seconds. Default
        5 seconds.

        | Library | MQTTLibrary | loop_timeout=10 seconds |
        """
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
            raise RuntimeError(
                "No connection with alias '%s'. Use Connect first." % alias
            ) from None

    def set_username_and_password(
        self, username: Optional[str], password: Optional[str] = None
    ):
        """Set the credentials that later `Connect` calls send to the broker.

        The credentials apply to every connection opened afterwards, until
        they are set again. Set ``username`` to ``${None}`` to connect
        without credentials.

        ``username`` the user name. ``${None}`` clears the credentials.

        ``password`` the password, if the broker requires one.

        Example:
        | Set Username And Password | authuser1 | password1 |
        | Connect | 127.0.0.1 | 11883 |
        """
        self._username = username
        self._password = password

    def connect(
        self,
        broker: str,
        port: int = 1883,
        client_id: str = "",
        clean_session: bool = True,
        keepalive: int = 60,
        alias: Optional[str] = None,
    ):
        """Connect to an MQTT broker. This is a pre-requisite step for publish
        and subscribe keywords.

        The connection is serviced by a background network loop until
        `Disconnect`, so keepalive pings and acknowledgements are handled
        between keywords. Messages for the connection's subscriptions are
        queued from this point on.

        ``broker`` MQTT broker host

        ``port`` broker port (default 1883)

        ``client_id`` if not specified, the broker assigns one

        ``clean_session`` specifies the clean session flag for the connection.
        With ``${False}`` a ``client_id`` is required.

        ``keepalive`` seconds between keepalive pings (default 60)

        ``alias`` names the connection so that several can be open at once.
        Other keywords take the same ``alias`` argument; without one they use
        the connection opened or switched to last. Default ``default``.
        Connecting again on an alias that is still connected disconnects the
        old connection first, with a warning.

        Fails with the broker's reason, for example
        ``Connection to 127.0.0.1:11883 failed: Not authorized``, if the broker
        refuses the connection or does not answer within the library's
        ``loop_timeout``. Use `Get Connection Info` to inspect the connection.

        Examples:

        Connect to a broker with default port and client id
        | Connect | 127.0.0.1 |

        Connect to a broker by specifying the port and client id explicitly
        | Connect | 127.0.0.1 | 1883 | test.client |

        Connect to a broker with clean session flag set to false
        | Connect | 127.0.0.1 | client_id=test.client | clean_session=${false} |

        Open a subscriber and a publisher connection
        | Connect | 127.0.0.1 | alias=sub |
        | Connect | 127.0.0.1 | alias=pub |
        """
        alias = alias or DEFAULT_ALIAS
        old = self._connections.pop(alias, None)
        if old is not None:
            logger.warn(
                "Connection '%s' to %s was still open. Disconnecting "
                "it before connecting again." % (alias, old.address)
            )
            try:
                old.close()
            except RuntimeError as exc:
                logger.warn(str(exc))

        logger.info("Connecting to %s at port %s" % (broker, port))
        conn = _Connection(
            alias,
            broker,
            port,
            client_id,
            clean_session,
            keepalive,
            self._loop_timeout,
            self._username,
            self._password,
        )
        conn.open()
        self._connections[alias] = conn
        self._alias = alias

    def get_connection_info(self, alias: Optional[str] = None) -> dict:
        """Return a dictionary describing a connection.

        The keys are ``alias``, ``host``, ``port``, ``client_id``,
        ``protocol`` (for example ``MQTTv311``), ``keepalive`` and
        ``connected``. ``connected`` becomes ``${False}`` when the broker
        drops the connection.

        ``alias`` the connection to describe (see `Connect`)

        Example:
        | Connect | 127.0.0.1 | client_id=test.client |
        | ${info}= | Get Connection Info |
        | Should Be Equal | ${info}[client_id] | test.client |
        | Should Be True | ${info}[connected] |
        """
        return self._connection(alias).info()

    def switch_connection(self, alias: str) -> str:
        """Make the connection named ``alias`` the one that keywords use when
        they are called without an ``alias``. Returns the previous alias.

        Example:
        | Connect | 127.0.0.1 | alias=sub |
        | Connect | 127.0.0.1 | alias=pub |
        | ${previous}= | Switch Connection | sub |
        """
        if alias not in self._connections:
            raise RuntimeError("No connection with alias '%s'." % alias)
        previous, self._alias = self._alias, alias
        return previous

    def publish(
        self,
        topic: str,
        message: Payload = None,
        qos: int = 0,
        retain: bool = False,
        alias: Optional[str] = None,
    ):
        """Publish a message to a topic with specified qos and retained flag.
        It is required that a connection has been established using `Connect`
        keyword before using this keyword. Waits until the message is sent
        (qos 0) or acknowledged (qos 1 and 2), and fails if it is not within
        the library's ``loop_timeout``.

        ``topic`` topic to which the message will be published

        ``message`` message payload to publish

        ``qos`` qos of the message

        ``retain`` retained flag

        ``alias`` the connection to use (see `Connect`)

        Examples:

        | Publish | test/test | test message | 1 | ${false} |
        """
        logger.info(
            "Publish topic: %s, message: %s, qos: %s, retain: %s"
            % (topic, message, qos, retain)
        )
        self._connection(alias).publish(topic, message, qos, retain)

    def subscribe(
        self,
        topic: str,
        qos: int,
        timeout: timedelta = timedelta(seconds=1),
        limit: int = 1,
        alias: Optional[str] = None,
    ) -> list:
        """Subscribe to a topic and return a list of message payloads
        received within the specified time. Waits for the broker to
        acknowledge the subscription, and fails if it refuses it.

        ``topic`` topic to subscribe to

        ``qos`` quality of service for the subscription

        ``timeout`` duration of subscription. Specify 0 to return
        immediately (async); read the messages later with `Listen`.
        Otherwise this is the same as `Listen` with the same ``timeout`` and
        ``limit``.

        ``limit`` the max number of payloads that will be returned. Specify 0
        for no limit. The oldest messages are returned first; the rest stay
        queued for the next `Listen` on the same connection.

        ``alias`` the connection to use (see `Connect`)

        Examples:

        Subscribe and get a list of all messages received within 5 seconds
        | ${messages}= | Subscribe | test/test | qos=1 | timeout=5 | limit=0 |

        Subscribe and get 1st message received within 60 seconds
        | @{messages}= | Subscribe | test/test | qos=1 | timeout=60 | limit=1 |
        | Length should be | ${messages} | 1 |

        Subscribe now and read the messages later
        | Subscribe | test/test | qos=1 | timeout=0 |
        """
        seconds = _seconds(timeout)
        conn = self._connection(alias)
        logger.info("Subscribing to topic: %s" % topic)
        conn.subscribe(topic, qos)
        if seconds == 0:
            return []
        return conn.listen(topic, seconds, limit)

    def listen(
        self,
        topic: str,
        timeout: timedelta = timedelta(seconds=1),
        limit: int = 1,
        alias: Optional[str] = None,
    ) -> list:
        """Listen to a topic and return a list of message payloads received
        within the specified time. Requires a `Subscribe` to the same topic
        on the same connection.

        Messages are queued from the moment of `Subscribe`, so none are lost
        between two calls. Fails if the connection is lost and no message is
        queued. Returns an empty list, with a warning, if the topic has no
        subscription.

        ``topic`` the topic filter given to `Subscribe`

        ``timeout`` duration to listen. Returns as soon as ``limit`` messages
        are available.

        ``limit`` the max number of payloads that will be returned. Specify 0
        for no limit. The oldest messages are returned first; the rest stay
        queued for the next `Listen`.

        ``alias`` the connection to use (see `Connect`)

        Examples:

        Listen and get a list of all messages received within 5 seconds
        | ${messages}= | Listen | test/test | timeout=5 | limit=0 |

        Listen and get 1st message received within 60 seconds
        | @{messages}= | Listen | test/test | timeout=60 | limit=1 |
        | Length should be | ${messages} | 1 |
        """
        logger.info("Listening on topic: %s" % topic)
        messages = self._connection(alias).listen(topic, _seconds(timeout), limit)
        if messages is None:
            logger.warn("Cannot listen when not subscribed to topic: %s" % topic)
            return []
        return messages

    def subscribe_and_validate(
        self,
        topic: str,
        qos: int,
        payload: str,
        timeout: timedelta = timedelta(seconds=1),
        alias: Optional[str] = None,
    ):
        """Subscribe to a topic and validate that the specified payload is
        received within timeout. It is required that a connection has been
        established using `Connect` keyword. The payload can be specified as
        a python regular expression. If the specified payload is not received
        within timeout, an AssertionError is thrown. Messages that do not
        match are consumed.

        ``topic`` topic to subscribe to

        ``qos`` quality of service for the subscription

        ``payload`` payload (message) that is expected to arrive, as a
        regular expression matched from the start of the payload

        ``timeout`` time to wait for the payload to arrive

        ``alias`` the connection to use (see `Connect`)

        Examples:

        | Subscribe And Validate | test/test | 1 | test message |
        """
        seconds = _seconds(timeout)
        conn = self._connection(alias)
        logger.info("Subscribing to topic: %s" % topic)
        conn.subscribe(topic, qos)
        if not conn.validate(topic, payload, seconds):
            raise AssertionError("The expected payload didn't arrive in the topic")

    def unsubscribe(self, topic: str, alias: Optional[str] = None):
        """Unsubscribe the client from the specified topic. Messages still
        queued for the topic are dropped. Other subscriptions on the
        connection are not affected. Does nothing if there is no such
        connection.

        ``topic`` topic to unsubscribe from

        ``alias`` the connection to use (see `Connect`)

        Example:
        | Unsubscribe | test/mqtt_test |
        """
        alias = alias or self._alias
        conn = self._connections.get(alias)
        if conn is None:
            logger.info("No MQTT connection found so nothing to unsubscribe from.")
            return

        logger.info("Unsubscribing from topic: %s" % topic)
        if not conn.unsubscribe(topic):
            logger.warn("Client didn't receive an unsubscribe callback")

    def disconnect(self, alias: Optional[str] = None):
        """Disconnect from MQTT Broker and stop the connection's network
        loop. Does nothing if there is no such connection.

        Fails with ``The client disconnected unexpectedly: <reason>`` if the
        broker had already dropped the connection.

        ``alias`` the connection to disconnect (see `Connect`)

        Example:
        | Disconnect |
        """
        alias = alias or self._alias
        conn = self._connections.pop(alias, None)
        if conn is None:
            logger.info("No MQTT connection found so nothing to disconnect from.")
            return
        if not conn.close():
            logger.warn(
                "The broker did not confirm the disconnect of %s "
                "within %s seconds" % (conn.address, conn.timeout)
            )

    def disconnect_all(self):
        """Disconnect every open connection. Tries all of them, then fails
        if any failed.

        Example:
        | [Teardown] | Disconnect All |
        """
        errors = []
        for alias in list(self._connections):
            try:
                self.disconnect(alias)
            except Exception as exc:
                errors.append("%s: %s" % (alias, exc))
        self._alias = DEFAULT_ALIAS
        if errors:
            raise RuntimeError("Disconnect All failed for %s" % "; ".join(errors))

    def publish_single(
        self,
        topic: str,
        payload: Payload = None,
        qos: int = 0,
        retain: bool = False,
        hostname: str = "localhost",
        port: int = 1883,
        client_id: str = "",
        keepalive: int = 60,
        will: Optional[dict] = None,
        auth: Optional[dict] = None,
        tls: Optional[dict] = None,
        protocol: Union[int, str] = MQTT_V31,
    ):
        """Publish a single message on its own connection and disconnect.
        This keyword uses the
        [https://eclipse.dev/paho/files/paho.mqtt.python/html/index.html|single]
        function of paho's publish module. It does not use or affect the
        connections opened with `Connect`.

        ``topic`` topic to which the message will be published

        ``payload`` message payload to publish (default None)

        ``qos`` qos of the message (default 0)

        ``retain`` retain flag (True or False, default False)

        ``hostname`` MQTT broker host (default localhost)

        ``port`` broker port (default 1883)

        ``client_id`` if not specified, a random id is generated

        ``keepalive`` keepalive timeout value for client

        ``will`` a dict containing will parameters for client:
            will = {'topic': "<topic>", 'payload':"<payload">, 'qos':<qos>,
                'retain':<retain>}

        ``auth`` a dict containing authentication parameters for the client:
            auth = {'username':"<username>", 'password':"<password>"}

        ``tls`` a dict containing TLS configuration parameters for the client:
            dict = {'ca_certs':"<ca_certs>", 'certfile':"<certfile>",
                'keyfile':"<keyfile>", 'tls_version':"<tls_version>",
                'ciphers':"<ciphers">}

        ``protocol`` MQTT protocol version, as a name (MQTTv31, MQTTv311 or
        MQTTv5) or a number (3, 4 or 5). Default MQTTv31.

        Example:

        Publish a message on specified topic and disconnect:
        | Publish Single | topic=t/mqtt | payload=test | hostname=127.0.0.1 |
        """
        logger.info(
            "Publishing to: %s:%s, topic: %s, payload: %s, qos: %s"
            % (hostname, port, topic, payload, qos)
        )
        publish.single(
            topic,
            payload,
            qos,
            retain,
            hostname,
            port,
            client_id,
            keepalive,
            will,
            auth,
            tls,
            _protocol(protocol),
        )

    def publish_multiple(
        self,
        msgs: list,
        hostname: str = "localhost",
        port: int = 1883,
        client_id: str = "",
        keepalive: int = 60,
        will: Optional[dict] = None,
        auth: Optional[dict] = None,
        tls: Optional[dict] = None,
        protocol: Union[int, str] = MQTT_V31,
    ):
        """Publish multiple messages on their own connection and disconnect.
        This keyword uses the
        [https://eclipse.dev/paho/files/paho.mqtt.python/html/index.html|multiple]
        function of paho's publish module. It does not use or affect the
        connections opened with `Connect`.

        ``msgs`` a list of messages to publish. Each message is either a dict
        or a tuple. If a dict, it must be of the form:
            msg = {'topic':"<topic>", 'payload':"<payload>", 'qos':<qos>,
                'retain':<retain>}
        Only the topic must be present. Default values will be used for any
        missing arguments. If a tuple, then it must be of the form:
            ("<topic>", "<payload>", qos, retain)

        See `Publish Single` for the description of ``hostname``, ``port``,
        ``client_id``, ``keepalive``, ``will``, ``auth``, ``tls`` and
        ``protocol``.

        Example:

        | ${msg1} | Create Dictionary | topic=${topic} | payload=message 1 |
        | ${msg2} | Create Dictionary | topic=${topic} | payload=message 2 |
        | ${msg3} | Create Dictionary | topic=${topic} | payload=message 3 |
        | @{msgs} | Create List | ${msg1} | ${msg2} | ${msg3} |
        | Publish Multiple | msgs=${msgs} | hostname=127.0.0.1 |
        """
        logger.info("Publishing to: %s:%s, msgs: %s" % (hostname, port, msgs))
        publish.multiple(
            msgs,
            hostname,
            port,
            client_id,
            keepalive,
            will,
            auth,
            tls,
            _protocol(protocol),
        )
