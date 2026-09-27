*** Settings ***
Documentation     Connect, Disconnect and Get Connection Info.
Resource          common.resource
Test Setup        Create Unique Topic
Test Teardown     Disconnect All
Suite Teardown    Disconnect All
Test Timeout      30 seconds

*** Test Cases ***
Connect with the default port and client id
    Skip If    '${PORT}' != '1883'    MQTT_PORT is not the default port
    Connect    ${BROKER}
    ${info}=    Get Connection Info
    Should Be Equal As Integers    ${info}[port]    1883
    Should Be Empty    ${info}[client_id]
    Should Be True    ${info}[connected]

Connect with a client id
    Connect    ${BROKER}    ${PORT}    client_id=${CLIENT}
    ${info}=    Get Connection Info
    Should Be Equal    ${info}[client_id]    ${CLIENT}

Connect with a port and a client id
    Connect    ${BROKER}    ${PORT}    ${CLIENT}
    ${info}=    Get Connection Info
    Should Be Equal As Integers    ${info}[port]    ${PORT}
    Should Be Equal    ${info}[client_id]    ${CLIENT}

Get Connection Info describes the connection
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    keepalive=30    alias=info
    ${info}=    Get Connection Info    info
    ${port}=    Convert To Integer    ${PORT}
    ${expected}=    Create Dictionary    alias=info    host=${BROKER}
    ...    port=${port}    client_id=${CLIENT}    protocol=MQTTv311
    ...    keepalive=${30}    connected=${True}
    Dictionaries Should Be Equal    ${info}    ${expected}

Get Connection Info without a connection fails
    Run Keyword And Expect Error
    ...    No connection with alias 'default'. Use Connect first.
    ...    Get Connection Info

Connections without a client id do not share one
    [Documentation]    With no client id the broker assigns a distinct one to
    ...    each connection, so neither takes over the other's session.
    Connect    ${BROKER}    ${PORT}    client_id=${None}    alias=one
    Connect    ${BROKER}    ${PORT}    client_id=${None}    alias=two
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=one
    Publish    ${TOPIC}    hello    qos=1    alias=two
    Listen Should Return    ${TOPIC}    hello    alias=one
    ${one}=    Get Connection Info    one
    ${two}=    Get Connection Info    two
    Should Be True    ${one}[connected] and ${two}[connected]
    Should Be Empty    ${one}[client_id]

Connect returns nothing
    ${result}=    Connect    ${BROKER}    ${PORT}
    Should Be Equal    ${result}    ${None}

A persistent session needs a client id
    Run Keyword And Expect Error
    ...    *A client id must be provided if clean session is False.*
    ...    Connect    ${BROKER}    ${PORT}    clean_session=${False}

Connection stays alive while idle for longer than the keepalive
    [Documentation]    #25: the background loop sends keepalive pings
    ...    between keywords. Mosquitto drops a client after 1.5 x keepalive
    ...    without traffic, so the Sleep is the point of this test.
    [Tags]    issue-25
    Connect    ${BROKER}    ${PORT}    keepalive=2
    Sleep    5s
    Publish    ${TOPIC}    still connected    qos=1
    ${info}=    Get Connection Info
    Should Be True    ${info}[connected]

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

Disconnect stops the network thread
    [Documentation]    0.7 left the network thread of an async Subscribe
    ...    running after Disconnect.
    [Tags]    thread-leak
    ${before}=    Evaluate    threading.active_count()    modules=threading
    Connect    ${BROKER}    ${PORT}
    Subscribe    ${TOPIC}    qos=0    timeout=0
    Thread Count Should Be    ${before + 1}
    Disconnect
    Thread Count Should Be    ${before}

Disconnect without a connection does nothing
    Disconnect
    Disconnect    alias=never
