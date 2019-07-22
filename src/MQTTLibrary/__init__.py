from MQTTLibrary.MQTTKeywords import MQTTKeywords
from MQTTLibrary.version import VERSION

__version__ = VERSION


class MQTTLibrary(MQTTKeywords):

    """ A keyword library for Robot Framework. It provides keywords for
        performing various operations on an MQTT broker. See http://mqtt.org/
        for more details on MQTT specification.

        This library uses eclipse project's paho client. For more information
        on underlying methods and documentation, see:
            http://eclipse.org/paho/clients/python/docs/

    """

    ROBOT_LIBRARY_SCOPE = 'GLOBAL'
    ROBOT_LIBRARY_VERSION = __version__
