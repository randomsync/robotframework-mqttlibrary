*** Settings ***
Documentation     Named connections, subscription bookkeeping and argument
...               handling.
Library           MQTTLibrary
Test Setup        Create Unique Topic
Test Teardown     Disconnect All
Test Timeout      30 seconds

*** Variables ***
${BROKER}         127.0.0.1
${PORT}           1883

*** Test Cases ***
Publish and subscribe on two named connections
    Connect    ${BROKER}    ${PORT}    alias=sub
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=sub
    Connect    ${BROKER}    ${PORT}    alias=pub
    Publish    ${TOPIC}    hello    qos=1    alias=pub
    @{messages}=    Listen    ${TOPIC}    timeout=5s    alias=sub
    Should Be Equal    ${messages}    ${{['hello']}}

Keywords without an alias use the last connection opened or switched to
    Connect    ${BROKER}    ${PORT}    alias=sub
    Connect    ${BROKER}    ${PORT}    alias=pub
    ${previous}=    Switch Connection    sub
    Should Be Equal    ${previous}    pub
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    hello    qos=1    alias=pub
    @{messages}=    Listen    ${TOPIC}    timeout=5s
    Should Be Equal    ${messages}    ${{['hello']}}

Switch Connection to an unknown alias fails
    Run Keyword And Expect Error    No connection with alias 'nope'.
    ...    Switch Connection    nope

Connecting again on an open alias replaces the connection
    [Documentation]    The old connection is disconnected with a warning,
    ...    so no network thread is left behind.
    ${before}=    Evaluate    threading.active_count()    modules=threading
    Connect    ${BROKER}    ${PORT}    alias=sub
    Connect    ${BROKER}    ${PORT}    alias=sub
    ${during}=    Evaluate    threading.active_count()    modules=threading
    Should Be Equal As Integers    ${during}    ${before + 1}
    Disconnect    sub
    ${after}=    Evaluate    threading.active_count()    modules=threading
    Should Be Equal As Integers    ${after}    ${before}

Disconnect All closes every connection
    ${before}=    Evaluate    threading.active_count()    modules=threading
    Connect    ${BROKER}    ${PORT}    alias=one
    Connect    ${BROKER}    ${PORT}    alias=two
    Disconnect All
    ${after}=    Evaluate    threading.active_count()    modules=threading
    Should Be Equal As Integers    ${after}    ${before}
    Run Keyword And Expect Error    No connection with alias 'one'. *
    ...    Publish    ${TOPIC}    hello    alias=one

Keywords fail clearly without a connection
    Run Keyword And Expect Error
    ...    No connection with alias 'default'. Use Connect first.
    ...    Publish    ${TOPIC}    hello

Disconnect and Unsubscribe without a connection do nothing
    Unsubscribe    ${TOPIC}    alias=never
    Disconnect    alias=never

Overlapping subscriptions each receive every message once
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}/#    qos=1    timeout=0
    Subscribe    ${TOPIC}/1    qos=1    timeout=0
    Publish    ${TOPIC}/1    hello    qos=1
    Publish    ${TOPIC}/1    hello    qos=1
    Publish    ${TOPIC}/2    other    qos=1
    # limit=0 so that duplicates would show.
    @{wide}=    Listen    ${TOPIC}/#    timeout=2s    limit=0
    @{narrow}=    Listen    ${TOPIC}/1    timeout=0    limit=0
    Should Be Equal    ${wide}    ${{['hello', 'hello', 'other']}}
    Should Be Equal    ${narrow}    ${{['hello', 'hello']}}

Unsubscribe keeps the other subscriptions
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}/a    qos=1    timeout=0
    Subscribe    ${TOPIC}/b    qos=1    timeout=0
    Unsubscribe    ${TOPIC}/a
    Publish    ${TOPIC}/b    hello    qos=1
    @{messages}=    Listen    ${TOPIC}/b    timeout=5s
    Should Be Equal    ${messages}    ${{['hello']}}
    @{messages}=    Listen    ${TOPIC}/a    timeout=0
    Should Be Empty    ${messages}

Subscribing again to a filter keeps its queued messages
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    hello    qos=1
    Subscribe    ${TOPIC}    qos=1    timeout=0
    @{messages}=    Listen    ${TOPIC}    timeout=5s
    Should Be Equal    ${messages}    ${{['hello']}}

Publish Single accepts the protocol as a name or a number
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish Single    ${TOPIC}    by name    qos=1    hostname=${BROKER}
    ...    protocol=MQTTv311
    Publish Single    ${TOPIC}    by number    qos=1    hostname=${BROKER}
    ...    protocol=5
    @{messages}=    Listen    ${TOPIC}    timeout=5s    limit=2
    Should Be Equal    ${messages}    ${{['by name', 'by number']}}

Publish Single rejects an unknown protocol
    Run Keyword And Expect Error    Unknown MQTT protocol version: 7. *
    ...    Publish Single    ${TOPIC}    hello    hostname=${BROKER}
    ...    protocol=7

*** Keywords ***
Create Unique Topic
    ${id}=    Evaluate    uuid.uuid4().hex    modules=uuid
    Set Test Variable    ${TOPIC}    test/connections/${id}
