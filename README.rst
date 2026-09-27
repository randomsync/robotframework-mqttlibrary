MQTTLibrary for Robot Framework
===============================

.. image:: https://github.com/randomsync/robotframework-mqttlibrary/actions/workflows/ci.yml/badge.svg?branch=0.7.x&event=push
    :target: https://github.com/randomsync/robotframework-mqttlibrary/actions/workflows/ci.yml
    :alt: CI

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

The tests are in ``tests`` folder and make use of Robot Framework itself. They need two local MQTT brokers: one without authentication, used by most tests, and one that requires a username and password. Both are defined in ``docker-compose.yml``. They need Docker Engine 25 or later. Start them, run the tests, and stop them when you are done::

    docker compose up --wait
    robot -P src tests
    docker compose down

The test credentials live in ``mosquitto/passwd_file``. To regenerate it, run ``scripts/gen-passwd.sh``.

.. _instructions: http://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html#creating-test-libraries

License
-------
MQTTLibrary is open source software provided under the `Apache License 2.0`__.

__ http://apache.org/licenses/LICENSE-2.0