*** Settings ***
Documentation     Regression tests for reported issues and for the 0.7 design
...               problems that the background network loop fixes.
Library           Collections
Library           MQTTLibrary
Test Setup        Create Unique Topic
Test Teardown     Disconnect All
Test Timeout      60 seconds

*** Variables ***
${BROKER}         127.0.0.1
${PORT}           1883
${AUTH PORT}      11883

*** Test Cases ***
Subscribe, publish and listen on one connection without Sleep
    [Documentation]    #33: messages published right after Subscribe arrive.
    [Tags]    issue-33
    Connect    ${BROKER}    ${PORT}
    FOR    ${i}    IN RANGE    20
        Subscribe    ${TOPIC}/${i}    qos=1    timeout=0
        Publish    ${TOPIC}/${i}    message ${i}
        @{messages}=    Listen    ${TOPIC}/${i}    timeout=5s    limit=1
        Should Be Equal    ${messages}    ${{['message ${i}']}}
    END

Listen with no limit returns all 200 QoS 1 messages
    [Documentation]    #28: no message is lost or left unacknowledged.
    [Tags]    issue-28
    Connect    ${BROKER}    ${PORT}    alias=sub
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=sub
    ${msgs}=    Evaluate    [{'topic': '${TOPIC}', 'payload': str(i), 'qos': 1} for i in range(200)]
    Publish Multiple    ${msgs}    hostname=${BROKER}
    @{messages}=    Listen    ${TOPIC}    timeout=3s    limit=0    alias=sub
    ${expected}=    Evaluate    [str(i) for i in range(200)]
    Lists Should Be Equal    ${messages}    ${expected}

Connection stays alive while idle for longer than the keepalive
    [Documentation]    #25: the background loop sends keepalive pings
    ...    between keywords. Mosquitto drops a client after 1.5 x keepalive
    ...    without traffic, so the Sleep is the point of this test.
    [Tags]    issue-25
    Connect    ${BROKER}    ${PORT}    keepalive=2
    Sleep    5s
    Publish    ${TOPIC}    still connected    qos=1

Connecting to an unreachable host fails within the timeout
    [Documentation]    #24: 192.0.2.1 is reserved for documentation
    ...    (RFC 5737) and never answers.
    [Tags]    issue-24
    ${start}=    Evaluate    time.monotonic()    modules=time
    Run Keyword And Expect Error    Connection to 192.0.2.1:1883 failed: *
    ...    Connect    192.0.2.1
    ${elapsed}=    Evaluate    time.monotonic() - ${start}    modules=time
    Should Be True    ${elapsed} < 6    Took ${elapsed} seconds

Connecting to an invalid host name fails and names the host
    [Documentation]    #24: the address from the issue report.
    [Tags]    issue-24
    Run Keyword And Expect Error    Connection to 172..0.0.1:1883 failed: *
    ...    Connect    172..0.0.1

Two Listen calls in a row lose no messages
    [Documentation]    #23: Listen no longer resets the queue.
    [Tags]    issue-23
    Connect    ${BROKER}    ${PORT}    alias=sub
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=sub
    Connect    ${BROKER}    ${PORT}    alias=pub
    Publish    ${TOPIC}    message 1    qos=1    alias=pub
    Publish    ${TOPIC}    message 2    qos=1    alias=pub
    @{messages}=    Listen    ${TOPIC}    timeout=5s    limit=1    alias=sub
    Should Be Equal    ${messages}    ${{['message 1']}}
    Publish    ${TOPIC}    message 3    qos=1    alias=pub
    @{messages}=    Listen    ${TOPIC}    timeout=5s    limit=2    alias=sub
    Should Be Equal    ${messages}    ${{['message 2', 'message 3']}}

Disconnect stops the network thread
    [Documentation]    0.7 left the loop thread of an async Subscribe running.
    [Tags]    thread-leak
    ${before}=    Evaluate    threading.active_count()    modules=threading
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=0    timeout=0
    ${during}=    Evaluate    threading.active_count()    modules=threading
    Should Be Equal As Integers    ${during}    ${before + 1}
    Disconnect
    ${after}=    Evaluate    threading.active_count()    modules=threading
    Should Be Equal As Integers    ${after}    ${before}

A wrong password fails with the broker's reason and leaves no thread
    [Tags]    auth    thread-leak
    Set Username And Password    authuser1    invalidpwd
    ${before}=    Evaluate    threading.active_count()    modules=threading
    ${start}=    Evaluate    time.monotonic()    modules=time
    Run Keyword And Expect Error
    ...    Connection to ${BROKER}:${AUTH PORT} failed: Not authorized
    ...    Connect    ${BROKER}    ${AUTH PORT}
    ${elapsed}=    Evaluate    time.monotonic() - ${start}    modules=time
    Should Be True    ${elapsed} < 5    Took ${elapsed} seconds
    ${after}=    Evaluate    threading.active_count()    modules=threading
    Should Be Equal As Integers    ${after}    ${before}
    [Teardown]    Run Keywords    Set Username And Password    ${NONE}
    ...    AND    Disconnect All

Messages queued for a persistent session arrive after reconnecting
    [Documentation]    The broker delivers queued messages right after
    ...    CONNACK, before Subscribe. They wait in the connection's queue.
    [Tags]    persistent-session
    ${client}=    Set Variable    robot.persist.${ID}
    Connect    ${BROKER}    ${PORT}    ${client}    ${false}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Disconnect
    Publish Single    ${TOPIC}    queued message    qos=1    hostname=${BROKER}
    Connect    ${BROKER}    ${PORT}    ${client}    ${false}
    Subscribe And Validate    ${TOPIC}    1    queued message    timeout=5s

*** Keywords ***
Create Unique Topic
    ${id}=    Evaluate    uuid.uuid4().hex    modules=uuid
    Set Test Variable    ${ID}    ${id}
    Set Test Variable    ${TOPIC}    test/regressions/${id}
