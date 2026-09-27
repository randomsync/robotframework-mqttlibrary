*** Settings ***
Documentation     Shared settings and keywords for the acceptance suites.
...
...               Broker addresses come from environment variables, so the
...               suites can run against another broker:
...               ``MQTT_HOST``, ``MQTT_PORT`` (anonymous broker),
...               ``MQTT_AUTH_PORT`` (broker with authentication) and
...               ``MQTT_WS_PORT`` (its websockets listener).
...
...               The keywords here do not return values, so the suites run
...               unchanged on Robot Framework 4 through 7.
Library           Collections
Library           MQTTLibrary

*** Variables ***
${BROKER}         %{MQTT_HOST=127.0.0.1}
${PORT}           %{MQTT_PORT=1883}
${AUTH PORT}      %{MQTT_AUTH_PORT=11883}
${WS PORT}        %{MQTT_WS_PORT=9001}

*** Keywords ***
Create Unique Topic
    [Documentation]    Sets ``${TOPIC}`` to a topic only this test uses,
    ...    built from the test name and a random suffix, and ``${CLIENT}``
    ...    to a matching client id. Suites use it as their test setup.
    ${name}=    Evaluate    re.sub(r'[^a-z0-9]+', '-', $TEST_NAME.lower()).strip('-')[:40]
    ...    modules=re
    ${id}=    Evaluate    uuid.uuid4().hex[:12]    modules=uuid
    Set Test Variable    ${TOPIC}    test/${name}/${id}
    Set Test Variable    ${CLIENT}    robot.${id}

Thread Count Should Be
    [Documentation]    Fails unless ``threading.active_count()`` equals
    ...    ``expected``.
    [Arguments]    ${expected}
    ${count}=    Evaluate    threading.active_count()    modules=threading
    Should Be Equal As Integers    ${count}    ${expected}

Open Persistent Session
    [Documentation]    Creates a persistent session for ``client`` that is
    ...    subscribed to ``topic``, then disconnects. The broker queues QoS 1
    ...    messages for it until the client reconnects.
    [Arguments]    ${client}    ${topic}    ${port}=${PORT}
    Connect    ${BROKER}    ${port}    ${client}    ${False}    alias=session
    Subscribe    ${topic}    qos=1    timeout=0    alias=session
    [Teardown]    Disconnect    session

Persistent Session Should Receive
    [Documentation]    Reconnects the persistent session of ``client``,
    ...    subscribes to ``topic`` and checks the payloads it gets, oldest
    ...    first. With ``limit=0`` it waits the whole ``timeout``.
    [Arguments]    ${client}    ${topic}    @{expected}    ${limit}=0    ${timeout}=1s
    Connect    ${BROKER}    ${PORT}    ${client}    ${False}    alias=session
    @{messages}=    Subscribe    ${topic}    qos=1    timeout=${timeout}
    ...    limit=${limit}    alias=session
    Lists Should Be Equal    ${messages}    ${expected}
    [Teardown]    Disconnect    session

Persistent Session Should Validate
    [Documentation]    Reconnects the persistent session of ``client`` and
    ...    runs `Subscribe And Validate` for ``payload`` on ``topic``.
    [Arguments]    ${client}    ${topic}    ${payload}=${EMPTY}    ${timeout}=1s
    ...    ${port}=${PORT}
    Connect    ${BROKER}    ${port}    ${client}    ${False}    alias=session
    Subscribe And Validate    ${topic}    1    ${payload}    ${timeout}
    ...    alias=session
    [Teardown]    Disconnect    session

Publish And Disconnect
    [Documentation]    Publishes one message on a connection of its own.
    [Arguments]    ${topic}    ${message}=${EMPTY}    ${qos}=0    ${retain}=${False}
    ...    ${port}=${PORT}
    Connect    ${BROKER}    ${port}    alias=pub
    Publish    ${topic}    ${message}    ${qos}    ${retain}    alias=pub
    [Teardown]    Disconnect    pub

Listen Should Return
    [Documentation]    Runs `Listen` and checks the payloads it returns.
    [Arguments]    ${topic}    @{expected}    ${timeout}=5s    ${limit}=1
    ...    ${alias}=${None}
    @{messages}=    Listen    ${topic}    ${timeout}    ${limit}    alias=${alias}
    Lists Should Be Equal    ${messages}    ${expected}
