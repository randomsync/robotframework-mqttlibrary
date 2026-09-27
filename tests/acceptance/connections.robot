*** Settings ***
Documentation     Named connections.
Resource          common.resource
Test Setup        Create Unique Topic
Test Teardown     Disconnect All
Suite Teardown    Disconnect All
Test Timeout      30 seconds

*** Test Cases ***
Publish and subscribe on two named connections
    Connect    ${BROKER}    ${PORT}    alias=sub
    Subscribe    ${TOPIC}    qos=1    timeout=0    alias=sub
    Connect    ${BROKER}    ${PORT}    alias=pub
    Publish    ${TOPIC}    hello    qos=1    alias=pub
    Listen Should Return    ${TOPIC}    hello    alias=sub

Keywords without an alias use the last connection opened or switched to
    Connect    ${BROKER}    ${PORT}    alias=sub
    Connect    ${BROKER}    ${PORT}    alias=pub
    ${previous}=    Switch Connection    sub
    Should Be Equal    ${previous}    pub
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    hello    qos=1    alias=pub
    Listen Should Return    ${TOPIC}    hello
    ${info}=    Get Connection Info
    Should Be Equal    ${info}[alias]    sub

Switch Connection to an unknown alias fails
    Run Keyword And Expect Error    No connection with alias 'nope'.
    ...    Switch Connection    nope

Connecting again on an open alias replaces the connection
    [Documentation]    The old connection is disconnected with a warning,
    ...    so no network thread is left behind.
    [Tags]    thread-leak
    ${before}=    Evaluate    threading.active_count()    modules=threading
    Connect    ${BROKER}    ${PORT}    ${CLIENT}.old    alias=sub
    Connect    ${BROKER}    ${PORT}    ${CLIENT}.new    alias=sub
    Thread Count Should Be    ${before + 1}
    ${info}=    Get Connection Info    sub
    Should Be Equal    ${info}[client_id]    ${CLIENT}.new
    Disconnect    sub
    Thread Count Should Be    ${before}

Disconnect All closes every connection
    ${before}=    Evaluate    threading.active_count()    modules=threading
    Connect    ${BROKER}    ${PORT}    alias=one
    Connect    ${BROKER}    ${PORT}    alias=two
    Disconnect All
    Thread Count Should Be    ${before}
    Run Keyword And Expect Error    No connection with alias 'one'. *
    ...    Publish    ${TOPIC}    hello    alias=one

Keywords fail clearly without a connection
    Run Keyword And Expect Error
    ...    No connection with alias 'default'. Use Connect first.
    ...    Publish    ${TOPIC}    hello

Unsubscribe without a connection does nothing
    Unsubscribe    ${TOPIC}    alias=never
