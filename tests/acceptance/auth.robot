*** Settings ***
Documentation     The broker that requires a username and password.
Resource          common.resource
Test Setup        Create Unique Topic
Test Teardown     Run Keywords    Set Username And Password    ${None}
...               AND    Disconnect All
Suite Teardown    Disconnect All
Test Timeout      30 seconds
Force Tags        auth

*** Test Cases ***
Publish and subscribe with a username and password
    Set Username And Password    authuser1    password1
    Run Keyword And Expect Error    The expected payload didn't arrive in the topic
    ...    Persistent Session Should Validate    ${CLIENT}    ${TOPIC}
    ...    with credentials    port=${AUTH PORT}
    Publish And Disconnect    ${TOPIC}    with credentials    qos=1    port=${AUTH PORT}
    Persistent Session Should Validate    ${CLIENT}    ${TOPIC}    with credentials
    ...    port=${AUTH PORT}

A wrong password fails with the broker's reason and leaves no thread
    Set Username And Password    authuser1    invalidpwd
    ${before}=    Evaluate    threading.active_count()    modules=threading
    ${start}=    Evaluate    time.monotonic()    modules=time
    Run Keyword And Expect Error    *Not authorized*
    ...    Connect    ${BROKER}    ${AUTH PORT}    ${CLIENT}
    ${elapsed}=    Evaluate    time.monotonic() - ${start}    modules=time
    Should Be True    ${elapsed} < 5    Took ${elapsed} seconds
    Thread Count Should Be    ${before}

Connecting without credentials is refused
    Run Keyword And Expect Error
    ...    Connection to ${BROKER}:${AUTH PORT} failed: Not authorized
    ...    Connect    ${BROKER}    ${AUTH PORT}
