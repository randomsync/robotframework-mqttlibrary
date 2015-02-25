MQTTLibrary for Robot Framework
===============================

.. image:: https://travis-ci.org/randomsync/robotframework-mqttlibrary.svg?branch=master
    :target: https://travis-ci.org/randomsync/robotframework-mqttlibrary

.. image:: https://pypip.in/version/robotframework-mqttlibrary/badge.png?text=version
   :target: https://pypi.python.org/pypi/robotframework-mqttlibrary/
   :alt: Latest version

.. image:: https://pypip.in/download/robotframework-mqttlibrary/badge.png
   :target: https://pypi.python.org/pypi/robotframework-mqttlibrary/
   :alt: Number of downloads

MQTTLibrary is a `Robot Framework`_ library that provides keywords for testing on MQTT brokers. MQTT_ is a lightweight protocol for machine-to-machine communication, typically used for IoT messaging. This library uses the paho_ client library published by eclipse project.

.. _Robot Framework: http://robotframework.org
.. _MQTT: http://mqtt.org/
.. _paho: https://eclipse.org/paho/

Installation
------------

MQTTLibrary can be installed using `pip <http://pip-installer.org>`__::

    pip install robotframework-mqttlibrary

You can also install it from the source distribution by running::

    python setup.py install

You may need to run the above command with administrator privileges.

Usage
-------

Import the library:

.. code-block:: robotframework

    *** Settings ***
    Library          MQTTLibrary

Connect to the broker, publish and disconnect:

.. code-block:: robotframework

    *** Test Cases ***
    Publish
        Connect     127.0.0.1
        Publish     topic=test/mqtt_test    message=test message
        [Teardown]  Disconnect

Connect to the broker, subscribe and validate that a message is received:

.. code-block:: robotframework

    *** Test Cases ***
    Subsribe and Validate
        Connect                 127.0.0.1
        Subscribe and Validate  topic=test/mqtt_test    qos=1   payload=test
        [Teardown]              Disconnect


Keyword documentation is available at: http://randomsync.github.io/robotframework-mqttlibrary.

Also look at ``tests`` folder for examples.

For general information about using test libraries with Robot Framework, see
`Robot Framework User Guide`__.

__ http://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html#using-test-libraries
