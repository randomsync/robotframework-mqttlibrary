MQTTLibrary for Robot Framework
===============================

.. image:: https://travis-ci.org/randomsync/robotframework-mqttlibrary.svg?branch=master
    :target: https://travis-ci.org/randomsync/robotframework-mqttlibrary

.. image:: https://badge.fury.io/py/robotframework-mqttlibrary.svg
    :target: https://badge.fury.io/py/robotframework-mqttlibrary

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
    Subscribe and Validate
        Connect                 127.0.0.1
        Subscribe and Validate  topic=test/mqtt_test    qos=1   payload=test
        [Teardown]              Disconnect


Keyword documentation is available at: http://randomsync.github.io/robotframework-mqttlibrary.

Also look at ``tests`` folder for examples.

For general information about using test libraries with Robot Framework, see
`Robot Framework User Guide`__.

__ http://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html#using-test-libraries

Contributing
------------

The keywords in this library are based on some of the methods available in eclipse paho client library. If you'd like to add keywords, see instructions_ on creating/updating libraries for Robot Framework.

The tests are in ``tests`` folder and make use of Robot Framework itself. They are run automatically through travis when code is pushed to a branch. When run locally, these tests rely on locally running mqtt brokers. We need 2 running brokers, one without auth that is used by most of the tests, and the other one with auth (configuration file is provided). You'll need to start them before running the tests. You can then run the tests locally::

    docker pull eclipse-mosquitto
    docker run -d -p 1883:1883 -v $(pwd)/mosquitto/mosquitto-no-passwd.conf:/mosquitto/config/mosquitto.conf eclipse-mosquitto
    docker run -d -p 11883:1883 -p 9001:9001 -v $(pwd)/mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf -v $(pwd)/mosquitto/passwd_file:/mosquitto/config/passwd_file eclipse-mosquitto
    robot -P src tests


Make sure to stop the docker container when it is no longer needed.

.. _instructions: http://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html#creating-test-libraries

License
-------
MQTTLibrary is open source software provided under the `Apache License 2.0`__.

__ http://apache.org/licenses/LICENSE-2.0