MQTTLibrary for Robot Framework
===============================

.. image:: https://github.com/randomsync/robotframework-mqttlibrary/actions/workflows/ci.yml/badge.svg?branch=master&event=push
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

MQTTLibrary can be installed using `pip <https://pip.pypa.io>`__::

    pip install robotframework-mqttlibrary

To install from a clone of this repository, run this in its root directory::

    pip install .

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

Use named connections to subscribe and publish in one test. Messages are queued from the moment of ``Subscribe``, and ``Listen`` returns the oldest first:

.. code-block:: robotframework

    *** Test Cases ***
    Publish and Listen
        Connect         127.0.0.1    alias=sub
        Subscribe       test/mqtt_test    qos=1    timeout=0    alias=sub
        Connect         127.0.0.1    alias=pub
        Publish         test/mqtt_test    hello    qos=1    alias=pub
        @{messages}=    Listen    test/mqtt_test    timeout=5s    alias=sub
        Should Be Equal    ${messages}[0]    hello
        [Teardown]      Disconnect All


Keyword documentation is available at: http://randomsync.github.io/robotframework-mqttlibrary.

Also look at the ``tests/acceptance`` folder for examples.

For general information about using test libraries with Robot Framework, see
`Robot Framework User Guide`__.

__ http://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html#using-test-libraries

Contributing
------------

The keywords in this library are based on some of the methods available in eclipse paho client library. If you'd like to add keywords, see instructions_ on creating/updating libraries for Robot Framework.

There are two layers of tests. The unit tests in ``tests/unit`` use pytest and a fake paho client, so they need no broker::

    pip install -e ".[dev]"
    pytest tests/unit

The acceptance tests in ``tests/acceptance`` make use of Robot Framework itself. They need two local MQTT brokers: one without authentication, used by most tests, and one that requires a username and password. Both are defined in ``docker-compose.yml``. They need Docker Engine 25 or later. Start them, run the tests, and stop them when you are done::

    docker compose up --wait
    robot tests/acceptance
    docker compose down

CI runs both layers under coverage and requires at least 90% combined coverage (see ``[tool.coverage]`` in ``pyproject.toml``).

The test credentials live in ``mosquitto/passwd_file``. To regenerate it, run ``scripts/gen-passwd.sh``.

.. _instructions: http://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html#creating-test-libraries

License
-------
MQTTLibrary is open source software provided under the `Apache License 2.0`__.

__ http://apache.org/licenses/LICENSE-2.0