*** Settings ***
Documentation     Wait Until Message Received, Message Count Should Be,
...               Payload Should Match, Should Be Connected and Should Not Be
...               Connected.
Resource          common.resource
Test Setup        Create Unique Topic
Test Teardown     Disconnect All
Suite Teardown    Disconnect All
Test Timeout      30 seconds

*** Test Cases ***
Wait Until Message Received returns the matching message
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}/#    qos=1    timeout=0
    Publish    ${TOPIC}/status    starting    qos=1
    Publish    ${TOPIC}/status    running    qos=1
    Publish    ${TOPIC}/status    stopped    qos=1
    ${message}=    Wait Until Message Received    ${TOPIC}/#    ^running$
    ...    timeout=5s
    Should Be Equal    ${message.topic}    ${TOPIC}/status
    Should Be Equal    ${message.payload}    running
    Listen Should Return    ${TOPIC}/#    stopped

Wait Until Message Received without a pattern takes the next message
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    anything    qos=1
    ${message}=    Wait Until Message Received    ${TOPIC}
    Should Be Equal    ${message.payload}    anything

Wait Until Message Received matches bytes without decoding
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    ${{bytes([0, 255])}}    qos=1
    ${message}=    Wait Until Message Received    ${TOPIC}    ^\\x00\\xff$
    ...    decode=${False}
    Should Be Equal    ${message.payload}    ${{bytes([0, 255])}}

Wait Until Message Received fails when no message matches
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    stopped    qos=1
    Run Keyword And Expect Error
    ...    Did not receive a message matching 'running' on ${TOPIC} within 1 second. It took 1 other messages: 'stopped'
    ...    Wait Until Message Received    ${TOPIC}    running    timeout=1s

Wait Until Message Received fails when the connection drops
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    alias=victim
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=victim
    Take Over Session    ${CLIENT}
    Run Keyword And Expect Error
    ...    Did not receive a message on ${TOPIC} within 10 seconds (connection lost: *)
    ...    Wait Until Message Received    ${TOPIC}    timeout=10s    alias=victim
    Run Keyword And Expect Error    The client disconnected unexpectedly: *
    ...    Disconnect    victim

Message Count Should Be counts the queued messages
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Message Count Should Be    ${TOPIC}    0
    Publish    ${TOPIC}    one    qos=1
    Publish    ${TOPIC}    two    qos=1
    Wait Until Keyword Succeeds    5s    0.05s
    ...    Message Count Should Be    ${TOPIC}    2
    Listen Should Return    ${TOPIC}    one    two    limit=2

Message Count Should Be fails with the actual count
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Run Keyword And Expect Error
    ...    Expected 1 queued messages on ${TOPIC}, but found 0.
    ...    Message Count Should Be    ${TOPIC}    1

Payload Should Match passes for a matching payload
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    21.5    qos=1
    ${message}=    Wait Until Message Received    ${TOPIC}
    Payload Should Match    ${message}    ^\\d+(\\.\\d+)?$
    Payload Should Match    ${message.payload}    \\.5

Payload Should Match fails and names the topic and pattern
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    hello    qos=1
    ${message}=    Wait Until Message Received    ${TOPIC}
    Run Keyword And Expect Error
    ...    Payload of the message on ${TOPIC} 'hello' does not match '^bye'.
    ...    Payload Should Match    ${message}    ^bye

Should Be Connected passes for an open connection
    Connect    ${BROKER}    ${PORT}    alias=open
    Should Be Connected    open
    Should Be Connected

Should Be Connected fails after the broker drops the connection
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    alias=victim
    Take Over Session    ${CLIENT}
    Wait Until Keyword Succeeds    2s    0.05s
    ...    Should Not Be Connected    victim
    Run Keyword And Expect Error
    ...    Connection 'victim' to ${BROKER}:${PORT} is not connected (connection lost: *).
    ...    Should Be Connected    victim
    Run Keyword And Expect Error    The client disconnected unexpectedly: *
    ...    Disconnect    victim

Should Not Be Connected passes after Disconnect
    Connect    ${BROKER}    ${PORT}    alias=closed
    Disconnect    closed
    Should Not Be Connected    closed

Should Not Be Connected fails for an alias that was never connected
    Connect    ${BROKER}    ${PORT}    alias=publisher
    Run Keyword And Expect Error    No connection with alias 'pubisher'.*
    ...    Should Not Be Connected    pubisher

Wait Until Message Received points to decode for a binary payload
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    ${{bytes([255])}}    qos=1
    Run Keyword And Expect Error
    ...    Did not receive a message on ${TOPIC} within 1 second. It skipped 1 messages that are not valid UTF-8; use decode=\${False} to match bytes
    ...    Wait Until Message Received    ${TOPIC}    timeout=1s

Should Not Be Connected fails for an open connection
    Connect    ${BROKER}    ${PORT}    alias=open
    Run Keyword And Expect Error
    ...    Connection 'open' to ${BROKER}:${PORT} is connected.
    ...    Should Not Be Connected    open
