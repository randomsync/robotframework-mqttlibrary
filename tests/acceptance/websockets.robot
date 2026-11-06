*** Settings ***
Documentation     MQTT over websockets, on the authenticated broker's
...               ``MQTT_WS_PORT``.
Resource          common.resource
Test Setup        Create Unique Topic
Test Teardown     Disconnect All
Suite Teardown    Disconnect All
Test Timeout      30 seconds
Force Tags        websockets

*** Test Cases ***
Publish and subscribe over websockets
    Connect    ${BROKER}    ${WS PORT}    transport=websockets
    ...    username=authuser1    password=password1
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    over websockets    qos=1
    Listen Should Return    ${TOPIC}    over websockets

Websockets and TCP clients exchange messages
    Connect    ${BROKER}    ${WS PORT}    transport=websockets
    ...    username=authuser1    password=password1    alias=ws
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=ws
    Connect    ${BROKER}    ${AUTH PORT}    username=authuser2
    ...    password=password2    alias=tcp
    Publish    ${TOPIC}    from tcp    qos=1    alias=tcp
    Listen Should Return    ${TOPIC}    from tcp    alias=ws

A path and headers are sent with the handshake
    [Documentation]    Mosquitto accepts any path and ignores extra
    ...    headers, so this shows the arguments are accepted. The unit tests
    ...    check they reach paho.
    ${headers}=    Create Dictionary    X-Test=robot
    Connect    ${BROKER}    ${WS PORT}    transport=websockets
    ...    ws_path=/custom    ws_headers=${headers}
    ...    username=authuser1    password=password1
    Connected Should Be    ${True}

Websockets with wrong credentials fails with the broker's reason
    Run Keyword And Expect Error
    ...    Connection to ${BROKER}:${WS PORT} failed: Not authorized
    ...    Connect    ${BROKER}    ${WS PORT}    transport=websockets
    ...    username=authuser1    password=wrong

A TCP client on the websockets port fails
    Run Keyword And Expect Error    Connection to ${BROKER}:${WS PORT} failed: *
    ...    Connect    ${BROKER}    ${WS PORT}
    ...    username=authuser1    password=password1

Websockets options without websockets fail
    Run Keyword And Expect Error
    ...    ws_path and ws_headers need transport=websockets.
    ...    Connect    ${BROKER}    ${WS PORT}    ws_path=/mqtt
