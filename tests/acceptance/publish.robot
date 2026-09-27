*** Settings ***
Documentation     Publish, Publish Single and Publish Multiple, checked on
...               the receiving side.
Resource          common.resource
Test Setup        Create Unique Topic
Test Teardown     Disconnect All
Suite Teardown    Disconnect All
Test Timeout      30 seconds

*** Test Cases ***
Publish a message
    ${time}=    Get Time    epoch
    Publish And Disconnect    ${TOPIC}    test message ${time}

Publish an empty message
    Publish And Disconnect    ${TOPIC}

Publish with QoS 1 and validate that the message is received
    Run Keyword And Expect Error    The expected payload didn't arrive in the topic
    ...    Persistent Session Should Validate    ${CLIENT}    ${TOPIC}    test message
    Publish And Disconnect    ${TOPIC}    test message    qos=1
    Persistent Session Should Validate    ${CLIENT}    ${TOPIC}    test message

Validation succeeds only after the expected message is published
    Run Keyword And Expect Error    The expected payload didn't arrive in the topic
    ...    Persistent Session Should Validate    ${CLIENT}    ${TOPIC}    test message
    Publish And Disconnect    ${TOPIC}    message1    qos=1
    Publish And Disconnect    ${TOPIC}    message2    qos=1
    Run Keyword And Expect Error    The expected payload didn't arrive in the topic
    ...    Persistent Session Should Validate    ${CLIENT}    ${TOPIC}    test message
    Publish And Disconnect    ${TOPIC}    test message    qos=1
    Publish And Disconnect    ${TOPIC}    message3    qos=1
    Publish And Disconnect    ${TOPIC}    message4    qos=1
    Persistent Session Should Validate    ${CLIENT}    ${TOPIC}    test message

Publish an empty message with QoS 1 and validate
    Run Keyword And Expect Error    The expected payload didn't arrive in the topic
    ...    Persistent Session Should Validate    ${CLIENT}    ${TOPIC}
    Publish And Disconnect    ${TOPIC}    qos=1
    Persistent Session Should Validate    ${CLIENT}    ${TOPIC}

Validate with a regular expression
    Run Keyword And Expect Error    The expected payload didn't arrive in the topic
    ...    Persistent Session Should Validate    ${CLIENT}    ${TOPIC}    whatever
    Publish And Disconnect    ${TOPIC}    subscription test message    qos=1
    Persistent Session Should Validate    ${CLIENT}    ${TOPIC}
    ...    ^subscription [test]{4} message$

Publish with QoS 2 delivers the message once
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=2    timeout=0
    Publish    ${TOPIC}    exactly once    qos=2
    Listen Should Return    ${TOPIC}    exactly once    timeout=1s    limit=0

A retained message reaches a later subscriber
    Publish And Disconnect    ${TOPIC}    retained    qos=1    retain=${True}
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Listen Should Return    ${TOPIC}    retained
    [Teardown]    Run Keywords    Publish And Disconnect    ${TOPIC}    retain=${True}
    ...    AND    Disconnect All

Publish Single sends a message
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish Single    ${TOPIC}    single message    qos=1    hostname=${BROKER}
    ...    port=${PORT}
    Listen Should Return    ${TOPIC}    single message

Publish Multiple sends every message in order
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    ${msg1}=    Create Dictionary    topic=${TOPIC}    payload=message 1    qos=${1}
    ${msg2}=    Create Dictionary    topic=${TOPIC}    payload=message 2    qos=${1}
    ${msg3}=    Create Dictionary    topic=${TOPIC}    payload=message 3    qos=${1}
    @{msgs}=    Create List    ${msg1}    ${msg2}    ${msg3}
    Publish Multiple    msgs=${msgs}    hostname=${BROKER}    port=${PORT}
    Listen Should Return    ${TOPIC}    message 1    message 2    message 3    limit=3

Listen with no limit returns all 200 QoS 1 messages
    [Documentation]    #28: no message is lost or left unacknowledged.
    [Tags]    issue-28
    Connect    ${BROKER}    ${PORT}    alias=sub
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=sub
    ${msgs}=    Evaluate    [{'topic': '${TOPIC}', 'payload': str(i), 'qos': 1} for i in range(200)]
    Publish Multiple    ${msgs}    hostname=${BROKER}    port=${PORT}
    @{messages}=    Listen    ${TOPIC}    timeout=3s    limit=0    alias=sub
    ${expected}=    Evaluate    [str(i) for i in range(200)]
    Lists Should Be Equal    ${messages}    ${expected}

Publish Single accepts the protocol as a name or a number
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish Single    ${TOPIC}    by name    qos=1    hostname=${BROKER}
    ...    port=${PORT}    protocol=MQTTv311
    Publish Single    ${TOPIC}    by number    qos=1    hostname=${BROKER}
    ...    port=${PORT}    protocol=5
    Listen Should Return    ${TOPIC}    by name    by number    limit=2

Publish rejects a payload paho cannot send
    ${payload}=    Create Dictionary    a=1
    Connect    ${BROKER}    ${PORT}
    Run Keyword And Expect Error    *payload must be a string, bytearray, int, float or None*
    ...    Publish    ${TOPIC}    ${payload}

Publish Single takes an SSL context for tls
    [Documentation]    The broker has no TLS listener, so the handshake fails;
    ...    the point is that the context reaches paho.
    ${context}=    Evaluate    ssl.create_default_context()    modules=ssl
    ${status}    ${error}=    Run Keyword And Ignore Error
    ...    Publish Single    ${TOPIC}    hello    hostname=${BROKER}    port=${PORT}
    ...    tls=${context}
    Should Be Equal    ${status}    FAIL
    Should Not Contain    ${error}    cannot be converted

Publish Single rejects an unknown protocol
    Run Keyword And Expect Error    Unknown MQTT protocol version: 7. *
    ...    Publish Single    ${TOPIC}    hello    hostname=${BROKER}
    ...    port=${PORT}    protocol=7
