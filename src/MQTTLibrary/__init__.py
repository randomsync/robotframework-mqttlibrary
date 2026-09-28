from MQTTLibrary.MQTTKeywords import MQTTKeywords
from MQTTLibrary.version import VERSION

__version__ = VERSION


class MQTTLibrary(MQTTKeywords):
    """A keyword library for Robot Framework. It provides keywords for
    performing various operations on an MQTT broker. See https://mqtt.org/
    for more details on MQTT specification.

    This library uses the Eclipse Paho Python client, see
    https://eclipse.dev/paho/files/paho.mqtt.python/html/index.html.

    = Connections =

    `Connect` opens a connection and `Disconnect` closes it. In between, a
    background network loop services the connection, so keepalive pings and
    acknowledgements are handled while a test does other things.

    Several connections can be open at once. Give each one an ``alias``
    when connecting, and pass the same ``alias`` to the other keywords.
    Keywords called without an ``alias`` use the connection opened, or
    switched to with `Switch Connection`, last. `Disconnect All` closes
    every connection, which makes it a good suite or test teardown.

    | Connect | 127.0.0.1 | alias=sub |
    | Subscribe | test/topic | qos=1 | timeout=0 | alias=sub |
    | Connect | 127.0.0.1 | alias=pub |
    | Publish | test/topic | hello | qos=1 | alias=pub |
    | ${messages}= | Listen | test/topic | timeout=5s | alias=sub |
    | [Teardown] | Disconnect All |

    = Messages =

    Each connection queues the messages for each of its subscriptions from
    the moment of `Connect`, including messages a persistent session
    delivers before `Subscribe`. `Subscribe` (with a timeout) and `Listen`
    return the oldest messages first. ``limit`` caps how many a call returns;
    the rest stay queued for the next `Listen` on the same connection.
    ``limit=0`` returns everything that arrives within the timeout. Payloads
    are returned as strings decoded as UTF-8.

    = Timeouts =

    Arguments named ``timeout`` take Robot Framework time strings such as
    ``5s`` or ``1 minute``, or numbers of seconds. Waits for the broker, such
    as the CONNACK in `Connect` or the acknowledgement in `Publish`, are
    bounded by the ``loop_timeout`` given when importing the library.

    = Errors =

    Keywords fail with the broker's reason when it refuses an operation,
    for example ``Connection to 127.0.0.1:11883 failed: Not authorized``.
    """

    ROBOT_LIBRARY_SCOPE = "GLOBAL"
    ROBOT_LIBRARY_VERSION = __version__
