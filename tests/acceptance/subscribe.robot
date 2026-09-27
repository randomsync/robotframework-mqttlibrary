*** Settings ***
Documentation     Subscribe, Listen and Unsubscribe.
Resource          common.resource
Test Setup        Create Unique Topic
Test Teardown     Disconnect All
Suite Teardown    Disconnect All
Test Timeout      30 seconds

*** Test Cases ***
Subscribe for the first time and receive nothing
    Persistent Session Should Receive    ${CLIENT}    ${TOPIC}    timeout=2s

Subscribe, publish one message and receive it
    Open Persistent Session    ${CLIENT}    ${TOPIC}
    Publish And Disconnect    ${TOPIC}    test message    qos=1
    Persistent Session Should Receive    ${CLIENT}    ${TOPIC}    test message    limit=1

Subscribe with no limit and receive every message in order
    Open Persistent Session    ${CLIENT}    ${TOPIC}
    Publish And Disconnect    ${TOPIC}    test message1    qos=1
    Publish And Disconnect    ${TOPIC}    test message2    qos=1
    Publish And Disconnect    ${TOPIC}    test message3    qos=1
    Persistent Session Should Receive    ${CLIENT}    ${TOPIC}
    ...    test message1    test message2    test message3

Subscribe with a limit returns the oldest and keeps the rest
    [Documentation]    The rest stay queued on the connection; they are read
    ...    and acknowledged, so a later session does not get them again.
    [Tags]    limit
    Open Persistent Session    ${CLIENT}    ${TOPIC}
    Publish And Disconnect    ${TOPIC}    test message1    qos=1
    Publish And Disconnect    ${TOPIC}    test message2    qos=1
    Publish And Disconnect    ${TOPIC}    test message3    qos=1
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    ${False}
    @{messages}=    Subscribe    ${TOPIC}    qos=1    timeout=1s    limit=1
    Lists Should Be Equal    ${messages}    ${{['test message1']}}
    Listen Should Return    ${TOPIC}    test message2    test message3    limit=2
    Disconnect
    Persistent Session Should Receive    ${CLIENT}    ${TOPIC}

Unsubscribe and receive no more messages
    Open Persistent Session    ${CLIENT}    ${TOPIC}
    Publish And Disconnect    ${TOPIC}    test message1    qos=1
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    ${False}
    @{messages}=    Subscribe    ${TOPIC}    qos=1    timeout=1s
    Lists Should Be Equal    ${messages}    ${{['test message1']}}
    Unsubscribe    ${TOPIC}
    Disconnect
    Publish And Disconnect    ${TOPIC}    test message2    qos=1
    Persistent Session Should Receive    ${CLIENT}    ${TOPIC}

Messages queued for a persistent session arrive after reconnecting
    [Documentation]    The broker delivers queued messages right after
    ...    CONNACK, before Subscribe. They wait in the connection's queue.
    [Tags]    persistent-session
    Open Persistent Session    ${CLIENT}    ${TOPIC}
    Publish Single    ${TOPIC}    queued message    qos=1    hostname=${BROKER}
    ...    port=${PORT}
    Persistent Session Should Validate    ${CLIENT}    ${TOPIC}    queued message
    ...    timeout=5s

Subscribe async, publish one message and listen for it
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    ${False}    alias=sub
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=sub
    Publish And Disconnect    ${TOPIC}    test message    qos=1
    Listen Should Return    ${TOPIC}    test message    alias=sub

Subscribe async, publish several messages and listen for them
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    ${False}    alias=sub
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=sub
    Publish And Disconnect    ${TOPIC}    test message1    qos=1
    Publish And Disconnect    ${TOPIC}    test message2    qos=1
    Publish And Disconnect    ${TOPIC}    test message3    qos=1
    Listen Should Return    ${TOPIC}    test message1    test message2    test message3
    ...    timeout=1s    limit=0    alias=sub

Subscribe async to two topics on two connections
    Connect    ${BROKER}    ${PORT}    ${CLIENT}.1    ${False}    alias=sub1
    Subscribe    ${TOPIC}/1    qos=1    timeout=0    alias=sub1
    Connect    ${BROKER}    ${PORT}    ${CLIENT}.2    ${False}    alias=sub2
    Subscribe    ${TOPIC}/2    qos=1    timeout=0    alias=sub2
    Publish And Disconnect    ${TOPIC}/2    test message1    qos=1
    Publish And Disconnect    ${TOPIC}/1    test message2    qos=1
    Publish And Disconnect    ${TOPIC}/2    test message3    qos=1
    Listen Should Return    ${TOPIC}/1    test message2
    ...    timeout=1s    limit=0    alias=sub1
    Listen Should Return    ${TOPIC}/2    test message1    test message3
    ...    timeout=1s    limit=0    alias=sub2

Listen right after Subscribe receives the queued message
    Open Persistent Session    ${CLIENT}    ${TOPIC}
    Publish And Disconnect    ${TOPIC}    test message    qos=1
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    ${False}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Listen Should Return    ${TOPIC}    test message    limit=10    timeout=2s

Subscribe, publish and listen on one connection without Sleep
    [Documentation]    #33: messages published right after Subscribe arrive.
    [Tags]    issue-33
    Connect    ${BROKER}    ${PORT}
    FOR    ${i}    IN RANGE    20
        Subscribe    ${TOPIC}/${i}    qos=1    timeout=0
        Publish    ${TOPIC}/${i}    message ${i}
        Listen Should Return    ${TOPIC}/${i}    message ${i}
    END

Two Listen calls in a row lose no messages
    [Documentation]    #23: Listen no longer resets the queue.
    [Tags]    issue-23
    Connect    ${BROKER}    ${PORT}    alias=sub
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=sub
    Connect    ${BROKER}    ${PORT}    alias=pub
    Publish    ${TOPIC}    message 1    qos=1    alias=pub
    Publish    ${TOPIC}    message 2    qos=1    alias=pub
    Listen Should Return    ${TOPIC}    message 1    alias=sub
    Publish    ${TOPIC}    message 3    qos=1    alias=pub
    Listen Should Return    ${TOPIC}    message 2    message 3    limit=2    alias=sub

Overlapping subscriptions each receive every message once
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}/#    qos=1    timeout=0
    Subscribe    ${TOPIC}/1    qos=1    timeout=0
    Publish    ${TOPIC}/1    hello    qos=1
    Publish    ${TOPIC}/1    hello    qos=1
    Publish    ${TOPIC}/2    other    qos=1
    # limit=0 so that duplicates would show.
    Listen Should Return    ${TOPIC}/#    hello    hello    other    timeout=2s    limit=0
    Listen Should Return    ${TOPIC}/1    hello    hello    timeout=0    limit=0

Unsubscribe keeps the other subscriptions
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}/a    qos=1    timeout=0
    Subscribe    ${TOPIC}/b    qos=1    timeout=0
    Unsubscribe    ${TOPIC}/a
    Publish    ${TOPIC}/b    hello    qos=1
    Listen Should Return    ${TOPIC}/b    hello

Subscribing again to a filter keeps its queued messages
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    hello    qos=1
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Listen Should Return    ${TOPIC}    hello
