from MQTTKeywords import MQTTKeywords
from version import VERSION

__version__ = VERSION


class MQTTLibrary(MQTTKeywords):

    """ A keyword library for Robot Framework. It provides keywords for performing various operations on an MQTT broker. See http://mqtt.org/ for more details on MQTT specification.

    """

    ROBOT_LIBRARY_SCOPE = 'GLOBAL'
    ROBOT_LIBRARY_VERSION = __version__