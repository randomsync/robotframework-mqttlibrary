import ssl
from datetime import timedelta
from typing import Any, Optional, Union

import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
from robot.api import logger
from robot.libraries.DateTime import convert_time

from MQTTLibrary.connection import QUEUE_LIMIT, _Connection

# paho 2 defines the protocol versions as an IntEnum. A plain int default keeps
# Robot Framework converting the argument as an int, as it did with paho 1.
MQTT_V31 = int(mqtt.MQTTv31)

_PROTOCOLS = {
    "mqttv31": mqtt.MQTTv31,
    "mqttv311": mqtt.MQTTv311,
    "mqttv5": mqtt.MQTTv5,
}

DEFAULT_ALIAS = "default"

# paho accepts str, bytes, bytearray, int, float or None as a payload. Any
# keeps Robot Framework from converting other values to their repr, so paho
# rejects them instead.
Payload = Any

# The payload types paho accepts. bool is an int.
_PAYLOAD_TYPES = (str, bytes, bytearray, int, float)

# The largest MQTT 5 session expiry interval, a four-byte integer.
_MAX_SESSION_EXPIRY = 0xFFFFFFFF

# paho's publish helpers take a dict of TLS settings or an ssl.SSLContext.
TLS = Union[dict, ssl.SSLContext, None]


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


_TLS_VERSIONS = {
    "tlsv1.2": ssl.TLSVersion.TLSv1_2,
    "tlsv1.3": ssl.TLSVersion.TLSv1_3,
}

_TRANSPORTS = ("tcp", "websockets")


def _tls_context(
    ca_certs, certfile, keyfile, keyfile_password, tls_version, ciphers, insecure
):
    """An SSL context for `Connect`'s TLS arguments.

    Built here rather than with paho's tls_set(), so that ``tls_version`` can
    pin a version without the deprecated ssl.PROTOCOL_TLSv1_2 constants, and
    ``insecure`` can skip verification altogether: paho's tls_insecure_set()
    only skips the host name check.
    """
    if (keyfile or keyfile_password) and not certfile:
        raise RuntimeError("keyfile and keyfile_password need certfile.")
    if insecure and ca_certs:
        raise RuntimeError(
            "insecure skips verifying the broker, so ca_certs would have no effect."
        )
    version = None
    if tls_version:
        version = _TLS_VERSIONS.get(tls_version.strip().lower())
        if version is None:
            raise RuntimeError(
                "Unknown TLS version: %s. Use TLSv1.2 or TLSv1.3." % tls_version
            )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if insecure:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    try:
        if ca_certs:
            step = "ca_certs %s" % ca_certs
            context.load_verify_locations(ca_certs)
        elif not insecure:
            step = "the system's trusted CA certificates"
            context.load_default_certs()
        if certfile:
            step = "certfile %s" % certfile
            if keyfile:
                step += " with keyfile %s" % keyfile
            context.load_cert_chain(certfile, keyfile, keyfile_password)
        if ciphers:
            step = "ciphers %s" % ciphers
            context.set_ciphers(ciphers)
    except (OSError, ValueError) as exc:
        # ssl.SSLError is an OSError. ValueError comes from a key password
        # longer than OpenSSL allows.
        raise RuntimeError("Cannot load %s: %s" % (step, exc)) from None
    if version is not None:
        context.minimum_version = context.maximum_version = version
    return context


# Timeout arguments are annotated timedelta so Robot Framework converts and
# validates them, but default to strings such as "1 second" so libdoc shows a
# readable default. _seconds() accepts both, and numbers from Python callers.
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

    def __init__(self, loop_timeout=LOOP_TIMEOUT, max_queue: int = QUEUE_LIMIT):
        """``loop_timeout`` bounds every wait for the broker: the TCP connect
        and CONNACK in `Connect`, the acknowledgements in `Publish`,
        `Subscribe` and `Unsubscribe`, and the disconnect in `Disconnect`.
        It is a Robot Framework time string or a number of seconds. Default
        5 seconds.

        ``max_queue`` is the most messages each subscription of a connection
        keeps queued, and the most it keeps that match no subscription yet.
        When a queue is full, the oldest message is dropped and the next read
        warns. Default 10000.

        | Library | MQTTLibrary | loop_timeout=10 seconds |
        | Library | MQTTLibrary | max_queue=100 |
        """
        if max_queue < 1:
            raise ValueError("max_queue must be at least 1, not %s." % max_queue)
        self._loop_timeout = convert_time(loop_timeout)
        self._max_queue = max_queue
        self._connections = {}
        self._alias = DEFAULT_ALIAS
        self._username = None
        self._password = None
        self._will = None

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
        """*DEPRECATED in 1.1.* Pass username and password to Connect instead.

        This keyword will be removed in 2.0, and using it logs a deprecation
        warning. It sets the credentials that later `Connect` calls send to
        the broker. The ``username`` and ``password`` arguments of `Connect`
        take precedence.

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

    def set_last_will(
        self,
        topic: Optional[str],
        payload: Payload = None,
        qos: int = 0,
        retain: bool = False,
    ):
        """Set the last will of the next `Connect`: a message the broker
        publishes on the connection's behalf if the connection ends without
        `Disconnect`, for example when the client crashes or the network
        fails.

        The will applies to the next `Connect` that succeeds, whatever its
        ``alias``, and is then cleared. Set ``topic`` to ``${None}`` to clear
        it without connecting.

        ``topic`` the topic to publish the will to. It cannot contain
        wildcards.

        ``payload`` the will message: a string, bytes, a number or
        ``${None}`` for an empty message

        ``qos`` qos of the will message (default 0)

        ``retain`` retained flag (default ``${False}``)

        Example:
        | Set Last Will | devices/robot/status | offline | qos=1 | retain=${True} |
        | Connect | 127.0.0.1 | client_id=robot |
        """
        if topic is None:
            self._will = None
            return
        if not topic or "+" in topic or "#" in topic:
            raise RuntimeError(
                "The last will topic must be a topic name without wildcards, "
                "not '%s'." % topic
            )
        if qos not in (0, 1, 2):
            raise RuntimeError("The last will qos must be 0, 1 or 2, not %s." % qos)
        if payload is not None and not isinstance(payload, _PAYLOAD_TYPES):
            raise RuntimeError(
                "The last will payload must be a string, bytes, a number or "
                "${None}, not %s." % type(payload).__name__
            )
        self._will = (topic, payload, qos, retain)

    def connect(
        self,
        broker: str,
        port: int = 1883,
        client_id: Optional[str] = "",
        clean_session: bool = True,
        keepalive: int = 60,
        alias: Optional[str] = None,
        *,
        protocol: Union[int, str] = "MQTTv311",
        username: Optional[str] = None,
        password: Optional[str] = None,
        transport: str = "tcp",
        ws_path: Optional[str] = None,
        ws_headers: Optional[dict] = None,
        tls: bool = False,
        ca_certs: Optional[str] = None,
        certfile: Optional[str] = None,
        keyfile: Optional[str] = None,
        keyfile_password: Optional[str] = None,
        tls_version: Optional[str] = None,
        ciphers: Optional[str] = None,
        insecure: bool = False,
        clean_start: Optional[bool] = None,
        session_expiry: Optional[int] = None,
        reconnect_on_failure: bool = False,
        reconnect_delay_min: int = 1,
        reconnect_delay_max: int = 120,
    ):
        """Connect to an MQTT broker. This is a pre-requisite step for publish
        and subscribe keywords.

        The connection is serviced by a background network loop until
        `Disconnect`, so keepalive pings and acknowledgements are handled
        between keywords. Messages for the connection's subscriptions are
        queued from this point on.

        ``broker`` MQTT broker host

        ``port`` broker port (default 1883)

        ``client_id`` if not specified (empty or ``${None}``), the broker
        assigns one

        ``clean_session`` specifies the clean session flag for the connection.
        With ``${False}`` a ``client_id`` is required.

        ``keepalive`` seconds between keepalive pings (default 60)

        ``alias`` names the connection so that several can be open at once.
        Other keywords take the same ``alias`` argument; without one they use
        the connection opened or switched to last. Default ``default``.
        Connecting again on an alias that is still connected disconnects the
        old connection first, with a warning.

        The arguments below must be given by name.

        ``protocol`` the MQTT version: ``MQTTv31``, ``MQTTv311`` (default) or
        ``MQTTv5``, or the number 3, 4 or 5.

        ``username`` and ``password`` the credentials to send. Without
        either, the ones set with the deprecated `Set Username And Password`
        are sent, if any. ``username=${EMPTY}`` connects without credentials
        even then.

        ``transport`` ``tcp`` (default) or ``websockets``.

        ``ws_path`` the URL path of the websockets handshake (default
        ``/mqtt``), and ``ws_headers`` a dictionary of extra HTTP headers to
        send with it. Both need ``transport=websockets``.

        *TLS*

        ``tls`` ``${True}`` connects with TLS and verifies the broker's
        certificate against the system's trusted CA certificates. Any of the
        other TLS arguments below also turns TLS on. Remember the broker's
        TLS port, usually 8883.

        ``ca_certs`` a file of CA certificates (PEM) to verify the broker
        against, instead of the system's.

        ``certfile`` and ``keyfile`` the client certificate and its private
        key (PEM), for brokers that require one. Leave out ``keyfile`` if
        ``certfile`` contains the key. ``keyfile_password`` decrypts a
        protected key.

        ``tls_version`` ``TLSv1.2`` or ``TLSv1.3`` allows only that version.
        By default both sides agree on the newest one they support.

        ``ciphers`` the allowed ciphers, in OpenSSL cipher list format.

        ``insecure`` ``${True}`` skips verifying the broker's certificate and
        host name. Use it only for testing.

        *MQTT 5 sessions*

        ``clean_start`` ``${False}`` resumes the session the broker kept for
        ``client_id``, and ``${True}`` always starts a new one. By default the
        first connect starts a new session and reconnects resume it.

        ``session_expiry`` how many seconds the broker keeps the session after
        the connection ends, up to 4294967295, which means it never expires.
        By default the session ends with the connection.

        Both need ``protocol=MQTTv5``. With MQTT 3.1 and 3.1.1, use
        ``clean_session`` instead; with MQTT 5 it must keep its default.

        *Reconnecting*

        ``reconnect_on_failure`` ``${True}`` reconnects in the background when
        the broker drops the connection. paho waits ``reconnect_delay_min``
        seconds (default 1, at least 1) before the first attempt and doubles
        the wait after each failed one, up to ``reconnect_delay_max`` (default
        120). After reconnecting, the connection subscribes again to its
        topics unless the broker kept the session; `Listen` fails on a topic
        the broker then refuses. While the connection is down, `Listen` waits
        until its timeout instead of failing, `Disconnect` stops reconnecting
        without failing, and other keywords fail as usual. A refused first
        connect still fails.

        Use `Set Last Will` before `Connect` to give the connection a last
        will.

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

        Connect with credentials
        | Connect | 127.0.0.1 | username=user | password=secret |

        Connect with TLS, verifying the broker against a CA file
        | Connect | broker.example.com | 8883 | ca_certs=${CURDIR}/ca.crt |

        Connect with TLS and a client certificate
        | Connect | broker.example.com | 8883 | ca_certs=ca.crt |
        | ... | certfile=client.crt | keyfile=client.key |

        Connect over websockets
        | Connect | 127.0.0.1 | 9001 | transport=websockets |

        Resume an MQTT 5 session that the broker keeps for five minutes
        | Connect | 127.0.0.1 | client_id=test.client | protocol=MQTTv5 |
        | ... | clean_start=${False} | session_expiry=300 |

        Reconnect if the broker drops the connection
        | Connect | 127.0.0.1 | reconnect_on_failure=${True} |
        """
        protocol = _protocol(protocol)
        if protocol == mqtt.MQTTv5:
            if not clean_session:
                raise RuntimeError(
                    "clean_session applies to MQTT 3.1 and 3.1.1. With MQTTv5, "
                    "use clean_start=${False} and session_expiry to resume a "
                    "session."
                )
        elif clean_start is not None or session_expiry is not None:
            raise RuntimeError("clean_start and session_expiry need protocol=MQTTv5.")
        if session_expiry is not None and not (
            0 <= session_expiry <= _MAX_SESSION_EXPIRY
        ):
            raise RuntimeError(
                "session_expiry must be between 0 and %d, not %s."
                % (_MAX_SESSION_EXPIRY, session_expiry)
            )
        if reconnect_delay_min < 1 or reconnect_delay_max < reconnect_delay_min:
            raise RuntimeError(
                "reconnect_delay_min must be at least 1 and no more than "
                "reconnect_delay_max, not %s and %s."
                % (reconnect_delay_min, reconnect_delay_max)
            )
        transport = transport.strip().lower()
        if transport not in _TRANSPORTS:
            raise RuntimeError(
                "Unknown transport: %s. Use tcp or websockets." % transport
            )
        if transport != "websockets" and (
            ws_path is not None or ws_headers is not None
        ):
            raise RuntimeError("ws_path and ws_headers need transport=websockets.")
        if username is None and password is None:
            username, password = self._username, self._password
        elif not username:
            if password is not None:
                raise RuntimeError("password needs username.")
            username = None
        context = None
        if (
            tls
            or insecure
            or any(
                (ca_certs, certfile, keyfile, keyfile_password, tls_version, ciphers)
            )
        ):
            context = _tls_context(
                ca_certs,
                certfile,
                keyfile,
                keyfile_password,
                tls_version,
                ciphers,
                insecure,
            )

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
            client_id or "",
            clean_session,
            keepalive,
            self._loop_timeout,
            username,
            password,
            protocol=protocol,
            transport=transport,
            ws_path=ws_path,
            ws_headers=ws_headers,
            tls=context,
            will=self._will,
            reconnect=(
                (reconnect_delay_min, reconnect_delay_max)
                if reconnect_on_failure
                else None
            ),
            clean_start=clean_start,
            session_expiry=session_expiry,
            max_queue=self._max_queue,
        )
        conn.open()
        self._connections[alias] = conn
        self._alias = alias
        self._will = None

    def get_connection_info(self, alias: Optional[str] = None) -> dict:
        """Return a dictionary describing a connection.

        The keys are ``alias``, ``host``, ``port``, ``client_id`` (the id
        the client sent, so empty when the broker assigned one),
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
    ) -> int:
        """Publish a message to a topic with specified qos and retained flag.
        It is required that a connection has been established using `Connect`
        keyword before using this keyword. Waits until the message is sent
        (qos 0) or acknowledged (qos 1 and 2), and fails if it is not within
        the library's ``loop_timeout``. Returns the message id.

        ``topic`` topic to which the message will be published

        ``message`` message payload to publish: a string, bytes, a number or
        ``${None}`` for an empty message

        ``qos`` qos of the message

        ``retain`` retained flag

        ``alias`` the connection to use (see `Connect`)

        Examples:

        | Publish | test/test | test message | 1 | ${false} |
        | ${mid}= | Publish | test/test | ${{bytes([0, 255])}} | qos=1 |
        """
        logger.info(
            "Publish topic: %s, message: %s, qos: %s, retain: %s"
            % (topic, message, qos, retain)
        )
        return self._connection(alias).publish(topic, message, qos, retain)

    def subscribe(
        self,
        topic: str,
        qos: int,
        timeout: timedelta = "1 second",
        limit: int = 1,
        alias: Optional[str] = None,
        *,
        decode: bool = True,
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

        ``decode`` returns payloads as strings decoded as UTF-8 (default).
        ``${False}`` returns them as bytes, for binary payloads. Must be
        given by name.

        Examples:

        Subscribe and get a list of all messages received within 5 seconds
        | ${messages}= | Subscribe | test/test | qos=1 | timeout=5 | limit=0 |

        Subscribe and get 1st message received within 60 seconds
        | @{messages}= | Subscribe | test/test | qos=1 | timeout=60 | limit=1 |
        | Length should be | ${messages} | 1 |

        Subscribe now and read the messages later
        | Subscribe | test/test | qos=1 | timeout=0 |

        Subscribe and get binary payloads as bytes
        | ${payloads}= | Subscribe | test/raw | qos=1 | timeout=5 | decode=${False} |
        """
        seconds = _seconds(timeout)
        conn = self._connection(alias)
        logger.info("Subscribing to topic: %s" % topic)
        conn.subscribe(topic, qos)
        if seconds == 0:
            return []
        return [m.payload for m in conn.listen(topic, seconds, limit, decode)]

    def listen(
        self,
        topic: str,
        timeout: timedelta = "1 second",
        limit: int = 1,
        alias: Optional[str] = None,
        *,
        decode: bool = True,
    ) -> list:
        """Listen to a topic and return a list of message payloads received
        within the specified time. Requires a `Subscribe` to the same topic
        on the same connection. Use `Get Messages` to get each message's
        topic, qos and other details too.

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

        ``decode`` returns payloads as strings decoded as UTF-8 (default).
        ``${False}`` returns them as bytes, for binary payloads. With
        ``${True}``, a payload that is not valid UTF-8 fails the keyword and
        is dropped; the other messages stay queued. Must be given by name.

        Examples:

        Listen and get a list of all messages received within 5 seconds
        | ${messages}= | Listen | test/test | timeout=5 | limit=0 |

        Listen and get 1st message received within 60 seconds
        | @{messages}= | Listen | test/test | timeout=60 | limit=1 |
        | Length should be | ${messages} | 1 |
        """
        messages = self._take("Listening on", topic, timeout, limit, alias, decode)
        return [message.payload for message in messages]

    def get_messages(
        self,
        topic: str,
        timeout: timedelta = "0 seconds",
        limit: int = 0,
        alias: Optional[str] = None,
        decode: bool = True,
    ) -> list:
        """Return the messages queued for a topic as message objects, oldest
        first, and remove them from the queue. Requires a `Subscribe` to the
        same topic on the same connection.

        Like `Listen`, but each message has the attributes ``topic`` (the
        topic it was published to, which tells messages of a wildcard
        subscription apart), ``payload``, ``qos``, ``retain``,
        ``properties`` (a dictionary of MQTT 5 properties, empty for earlier
        versions) and ``timestamp`` (when it arrived, in seconds since the
        epoch). Returns an empty list, with a warning, if the topic has no
        subscription.

        ``topic`` the topic filter given to `Subscribe`

        ``timeout`` how long to wait for messages. Default 0: return what is
        queued now.

        ``limit`` the most messages to return. Default 0: all of them. With
        a ``timeout``, returns as soon as ``limit`` messages are queued, or
        with 0 waits the whole ``timeout``.

        ``alias`` the connection to use (see `Connect`)

        ``decode`` decodes payloads as UTF-8 strings (default). ``${False}``
        keeps them as bytes. See `Listen`.

        Examples:

        Tell the messages of a wildcard subscription apart by topic
        | Subscribe | sensors/# | qos=1 | timeout=0 |
        | ${messages}= | Get Messages | sensors/# | timeout=5 | limit=2 |
        | Should Be Equal | ${messages[0].topic} | sensors/temperature |
        | Should Be Equal | ${messages[0].payload} | 21.5 |

        Get a binary payload as bytes
        | ${messages}= | Get Messages | test/raw | timeout=5 | limit=1 |
        | ... | decode=${False} |
        | Should Be Equal | ${messages[0].payload} | ${{bytes([0, 255])}} |
        """
        return self._take("Getting messages on", topic, timeout, limit, alias, decode)

    def _take(self, action, topic, timeout, limit, alias, decode):
        logger.info("%s topic: %s" % (action, topic))
        conn = self._connection(alias)
        messages = conn.listen(topic, _seconds(timeout), limit, decode)
        if messages is None:
            logger.warn("Cannot listen when not subscribed to topic: %s" % topic)
            return []
        return messages

    def clear_messages(self, topic: Optional[str] = None, alias: Optional[str] = None):
        """Drop the messages queued for a topic, or without a topic every
        message the connection has queued, including those that match no
        subscription yet. Subscriptions stay as they are, and later messages
        are queued as usual.

        ``topic`` the topic filter given to `Subscribe`. Warns if the topic
        has no subscription.

        ``alias`` the connection to use (see `Connect`)

        Examples:
        | Clear Messages | test/test |
        | Clear Messages |
        """
        count = self._connection(alias).clear(topic)
        if count is None:
            logger.warn(
                "Cannot clear messages when not subscribed to topic: %s" % topic
            )
        else:
            logger.info("Cleared %d messages" % count)

    def subscribe_and_validate(
        self,
        topic: str,
        qos: int,
        payload: str,
        timeout: timedelta = "1 second",
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
        broker had already dropped the connection, unless the connection was
        opened with ``reconnect_on_failure=${True}``.

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
        client_id: Optional[str] = "",
        keepalive: int = 60,
        will: Optional[dict] = None,
        auth: Optional[dict] = None,
        tls: TLS = None,
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
        or an ``ssl.SSLContext``.

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
        client_id: Optional[str] = "",
        keepalive: int = 60,
        will: Optional[dict] = None,
        auth: Optional[dict] = None,
        tls: TLS = None,
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
