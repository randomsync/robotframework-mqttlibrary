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

Connect with MQTT 5
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    protocol=MQTTv5
    ${info}=    Get Connection Info
    Should Be Equal    ${info}[protocol]    MQTTv5
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    over mqtt 5    qos=1
    Listen Should Return    ${TOPIC}    over mqtt 5

Connect with a protocol number
    Connect    ${BROKER}    ${PORT}    protocol=3
    ${info}=    Get Connection Info
    Should Be Equal    ${info}[protocol]    MQTTv31

An unknown protocol fails
    Run Keyword And Expect Error    Unknown MQTT protocol version: MQTTv6*
    ...    Connect    ${BROKER}    ${PORT}    protocol=MQTTv6

An MQTT 5 session with an expiry outlives the connection
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    protocol=MQTTv5
    ...    clean_start=${False}    session_expiry=60    alias=session
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=session
    Disconnect    session
    Publish And Disconnect    ${TOPIC}    kept for the session    qos=1
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    protocol=MQTTv5
    ...    clean_start=${False}    session_expiry=0    alias=session
    @{messages}=    Subscribe    ${TOPIC}    qos=1    timeout=5    alias=session
    Lists Should Be Equal    ${messages}    ${{["kept for the session"]}}

An MQTT 5 session without an expiry ends with the connection
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    protocol=MQTTv5
    ...    clean_start=${False}    alias=session
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=session
    Disconnect    session
    Publish And Disconnect    ${TOPIC}    nobody keeps this    qos=1
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    protocol=MQTTv5
    ...    clean_start=${False}    alias=session
    @{messages}=    Subscribe    ${TOPIC}    qos=1    timeout=1s    alias=session
    Should Be Empty    ${messages}

MQTT 5 with clean_session false points to clean_start
    Run Keyword And Expect Error
    ...    clean_session applies to MQTT 3.1 and 3.1.1. With MQTTv5, use clean_start=\${False}*
    ...    Connect    ${BROKER}    ${PORT}    ${CLIENT}    ${False}
    ...    protocol=MQTTv5

Session options need MQTT 5
    Run Keyword And Expect Error
    ...    clean_start and session_expiry need protocol=MQTTv5.
    ...    Connect    ${BROKER}    ${PORT}    ${CLIENT}    clean_start=${False}

The broker publishes the last will when the connection drops
    Connect    ${BROKER}    ${PORT}    alias=watcher
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=watcher
    Set Last Will    ${TOPIC}    gone    qos=1
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    alias=victim
    Take Over Session    ${CLIENT}
    Listen Should Return    ${TOPIC}    gone    alias=watcher
    Run Keyword And Expect Error    The client disconnected unexpectedly: *
    ...    Disconnect    victim

The last will is not published after Disconnect
    Connect    ${BROKER}    ${PORT}    alias=watcher
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=watcher
    Set Last Will    ${TOPIC}    gone    qos=1
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    alias=leaver
    Disconnect    leaver
    Listen Should Return    ${TOPIC}    timeout=1s    alias=watcher

The last will applies only to the next Connect
    Connect    ${BROKER}    ${PORT}    alias=watcher
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=watcher
    Set Last Will    ${TOPIC}    first only    qos=1
    Connect    ${BROKER}    ${PORT}    ${CLIENT}-first    alias=first
    Connect    ${BROKER}    ${PORT}    ${CLIENT}-second    alias=second
    Take Over Session    ${CLIENT}-second
    Listen Should Return    ${TOPIC}    timeout=1s    alias=watcher
    Run Keyword And Expect Error    The client disconnected unexpectedly: *
    ...    Disconnect    second

A last will topic with a wildcard fails
    Run Keyword And Expect Error
    ...    The last will topic must be a topic name without wildcards, not '${TOPIC}/#'.
    ...    Set Last Will    ${TOPIC}/#    gone

A dropped connection reconnects and subscribes again
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    reconnect_on_failure=${True}
    ...    reconnect_delay_min=2    alias=victim
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=victim
    Connect    ${BROKER}    ${PORT}    ${CLIENT}    alias=thief
    Wait Until Keyword Succeeds    2s    0.05s
    ...    Connected Should Be    ${False}    victim
    Disconnect    thief
    Wait Until Keyword Succeeds    10s    0.2s
    ...    Connected Should Be    ${True}    victim
    Publish And Disconnect    ${TOPIC}    after reconnecting    qos=1
    Listen Should Return    ${TOPIC}    after reconnecting    alias=victim
