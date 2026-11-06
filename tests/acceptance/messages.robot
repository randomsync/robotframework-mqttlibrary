*** Settings ***
Documentation     Message objects, binary payloads, Get Messages and
...               Clear Messages.
Resource          common.resource
Test Setup        Create Unique Topic
Test Teardown     Disconnect All
Suite Teardown    Disconnect All
Test Timeout      30 seconds

*** Variables ***
${BINARY}         ${{bytes([255, 254, 0, 128])}}

*** Test Cases ***
Messages of a wildcard subscription carry their topic
    [Tags]    issue-32
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}/#    qos=1    timeout=0
    Publish    ${TOPIC}/temperature    21.5    qos=1
    Publish    ${TOPIC}/humidity/inside    40    qos=0
    @{messages}=    Get Messages    ${TOPIC}/#    timeout=5    limit=2
    Log    ${messages}
    Should Be Equal    ${messages[0].topic}    ${TOPIC}/temperature
    Should Be Equal    ${messages[0].payload}    21.5
    Should Be Equal As Integers    ${messages[0].qos}    1
    Should Be Equal    ${messages[1].topic}    ${TOPIC}/humidity/inside
    Should Be Equal    ${messages[1].payload}    40
    Should Be Equal As Integers    ${messages[1].qos}    0

A message object has all six fields
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    ${start}=    Evaluate    time.time()    modules=time
    Publish    ${TOPIC}    fields    qos=1
    @{messages}=    Get Messages    ${TOPIC}    timeout=5    limit=1
    ${message}=    Set Variable    ${messages}[0]
    Log    ${message}
    Should Be Equal    ${message.topic}    ${TOPIC}
    Should Be Equal    ${message.payload}    fields
    Should Be Equal As Integers    ${message.qos}    1
    Should Be Equal    ${message.retain}    ${False}
    Should Be Empty    ${message.properties}
    Should Be True    ${start} <= ${message.timestamp} <= ${start} + 5

A retained message arrives with the retain flag
    Publish And Disconnect    ${TOPIC}    kept    qos=1    retain=${True}
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    @{messages}=    Get Messages    ${TOPIC}    timeout=5    limit=1
    Should Be Equal    ${messages[0].retain}    ${True}
    [Teardown]    Run Keywords    Publish And Disconnect    ${TOPIC}
    ...    retain=${True}    AND    Disconnect All

A binary payload round-trips as bytes
    [Tags]    issue-31
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    ${mid}=    Publish    ${TOPIC}    ${BINARY}    qos=1
    @{payloads}=    Listen    ${TOPIC}    timeout=5    decode=${False}
    Should Be Equal    ${payloads}[0]    ${BINARY}
    Publish    ${TOPIC}    ${BINARY}    qos=1
    @{messages}=    Get Messages    ${TOPIC}    timeout=5    limit=1
    ...    decode=${False}
    Should Be Equal    ${messages[0].payload}    ${BINARY}

Subscribe returns bytes without decoding
    [Tags]    issue-31
    Publish And Disconnect    ${TOPIC}    ${BINARY}    qos=1    retain=${True}
    Connect    ${BROKER}    ${PORT}
    @{payloads}=    Subscribe    ${TOPIC}    qos=1    timeout=5    decode=${False}
    Should Be Equal    ${payloads}[0]    ${BINARY}
    [Teardown]    Run Keywords    Publish And Disconnect    ${TOPIC}
    ...    retain=${True}    AND    Disconnect All

A binary payload fails decoding and points to decode
    [Tags]    issue-31
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    ${BINARY}    qos=1
    Publish    ${TOPIC}    text    qos=1
    Run Keyword And Expect Error
    ...    Dropped a message on ${TOPIC} that is not valid UTF-8: *Use decode=\${False} to get payloads as bytes.
    ...    Get Messages    ${TOPIC}    timeout=5    limit=2
    Listen Should Return    ${TOPIC}    text

Get Messages returns only what is queued without a timeout
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    @{messages}=    Get Messages    ${TOPIC}
    Should Be Empty    ${messages}

Get Messages with a limit keeps the rest
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    FOR    ${i}    IN RANGE    3
        Publish    ${TOPIC}    message ${i}    qos=1
    END
    @{first}=    Get Messages    ${TOPIC}    timeout=5    limit=2
    Should Be Equal    ${first[0].payload}    message 0
    Should Be Equal    ${first[1].payload}    message 1
    Listen Should Return    ${TOPIC}    message 2

Nothing is lost between two Get Messages calls
    [Documentation]    #23, read with Get Messages.
    [Tags]    issue-23
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    first    qos=1
    @{messages}=    Get Messages    ${TOPIC}    timeout=5    limit=1
    Should Be Equal    ${messages[0].payload}    first
    Publish    ${TOPIC}    second    qos=1
    Publish    ${TOPIC}    third    qos=1
    @{messages}=    Get Messages    ${TOPIC}    timeout=5    limit=2
    Should Be Equal    ${messages[0].payload}    second
    Should Be Equal    ${messages[1].payload}    third

Get Messages without a connection fails
    Run Keyword And Expect Error
    ...    No connection with alias 'default'. Use Connect first.
    ...    Get Messages    ${TOPIC}

Clear Messages drops the queued messages of a topic
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}/a    qos=1    timeout=0
    Subscribe    ${TOPIC}/b    qos=1    timeout=0
    Publish    ${TOPIC}/a    old    qos=1
    Publish    ${TOPIC}/b    kept    qos=1
    Wait For Marker    ${TOPIC}/b
    Clear Messages    ${TOPIC}/a
    Publish    ${TOPIC}/a    new    qos=1
    Listen Should Return    ${TOPIC}/a    new
    Listen Should Return    ${TOPIC}/b    kept

Clear Messages without a topic drops every queued message
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}/a    qos=1    timeout=0
    Subscribe    ${TOPIC}/b    qos=1    timeout=0
    Publish    ${TOPIC}/a    old    qos=1
    Publish    ${TOPIC}/b    old    qos=1
    Wait For Marker    ${TOPIC}/b
    Clear Messages
    @{a}=    Get Messages    ${TOPIC}/a
    @{b}=    Get Messages    ${TOPIC}/b
    Should Be Empty    ${a}
    Should Be Empty    ${b}

Clear Messages without a connection fails
    Run Keyword And Expect Error
    ...    No connection with alias 'default'. Use Connect first.
    ...    Clear Messages

Publish returns the message id
    Connect    ${BROKER}    ${PORT}
    ${first}=    Publish    ${TOPIC}    one    qos=1
    ${second}=    Publish    ${TOPIC}    two    qos=1
    Should Be True    isinstance(${first}, int) and ${second} == ${first} + 1

*** Keywords ***
Wait For Marker
    [Documentation]    Publishes a marker on a topic of its own, next to
    ...    ``topic``, and waits for it. Mosquitto sends a client's messages
    ...    in order, so everything published before it on the same
    ...    connection is queued too.
    [Arguments]    ${topic}
    Subscribe    ${topic}/marker    qos=1    timeout=0
    Publish    ${topic}/marker    marker    qos=1
    Listen Should Return    ${topic}/marker    marker
