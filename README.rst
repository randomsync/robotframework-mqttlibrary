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

To try the 1.0 release candidate, allow pre-releases::

    pip install --pre robotframework-mqttlibrary

Supported versions:

=============  ==========  ===============  ============
MQTTLibrary    Python      Robot Framework  paho-mqtt
=============  ==========  ===============  ============
1.0            3.9 - 3.14  4.1 - 7          2.1 - 2.x
0.7.2          3           not pinned       1.3 - 1.x
=============  ==========  ===============  ============

1.0 changes some keyword behaviour. See "Migrating from 0.7" in the `changelog <https://github.com/randomsync/robotframework-mqttlibrary/blob/master/CHANGELOG.md>`__ before upgrading.

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

You need Python 3.9 or later and Docker Engine 25 or later. The ``Makefile`` runs the same steps as CI; the first target that needs Python creates ``venv`` with the package installed in editable mode::

    make brokers    # start the test brokers from docker-compose.yml
    make test       # unit and acceptance tests under coverage
    make clean      # stop the brokers and remove test output

Other targets:

- ``make test-unit`` runs the unit tests in ``tests/unit``. They use pytest and a fake paho client, so they need no broker.
- ``make test-acc`` runs the Robot Framework acceptance tests in ``tests/acceptance`` against the brokers: one without authentication, used by most tests, and one that requires a username and password.
- ``make lint`` runs ruff, builds the keyword documentation and dry-runs the acceptance suites.
- ``make docs`` regenerates ``docs/index.html``.

CI requires at least 90% combined coverage (see ``[tool.coverage]`` in ``pyproject.toml``).

The acceptance tests read the broker addresses from environment variables, so they can run against other brokers: ``MQTT_HOST`` (default ``127.0.0.1``), ``MQTT_PORT`` (``1883``) and ``MQTT_AUTH_PORT`` (``11883``). For example::

    MQTT_HOST=192.168.1.10 make test-acc

The test credentials live in ``mosquitto/passwd_file``. To regenerate it, run ``scripts/gen-passwd.sh``.

.. _instructions: http://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html#creating-test-libraries

License
-------
MQTTLibrary is open source software provided under the `Apache License 2.0`__.

__ http://apache.org/licenses/LICENSE-2.0