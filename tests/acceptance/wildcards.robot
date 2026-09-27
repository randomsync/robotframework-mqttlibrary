*** Settings ***
Documentation     Subscriptions with single and multi level wildcards.
Resource          common.resource
Test Setup        Create Unique Topic
Test Teardown     Disconnect All
Suite Teardown    Disconnect All
Test Timeout      30 seconds
Force Tags        wildcards

*** Test Cases ***
Subscribe with a single level wildcard
    Subscribe Async    ${TOPIC}/+/Data
    Publish And Disconnect    ${TOPIC}/test/Data    message    qos=1
    Listen Should Return    ${TOPIC}/+/Data    message    alias=sub

Subscribe with a multi level wildcard
    Subscribe Async    ${TOPIC}/test/Data/#
    Publish And Disconnect    ${TOPIC}/test/Data/123/abc    message    qos=1
    Listen Should Return    ${TOPIC}/test/Data/#    message    alias=sub

Subscribe with single and multi level wildcards
    Subscribe Async    ${TOPIC}/+/Data/#
    Publish And Disconnect    ${TOPIC}/test/test/123/abc    messagetest
    Publish And Disconnect    ${TOPIC}/test/Data/123/abc    messageData
    Listen Should Return    ${TOPIC}/+/Data/#    messageData
    ...    timeout=1s    limit=0    alias=sub

Subscribe with several single level wildcards
    Subscribe Async    ${TOPIC}/+/Data/+/test
    Publish And Disconnect    ${TOPIC}/test/Data/123/abc    messageabc
    Publish And Disconnect    ${TOPIC}/test/Data/123/test    messagetest
    Listen Should Return    ${TOPIC}/+/Data/+/test    messagetest
    ...    timeout=1s    limit=0    alias=sub

*** Keywords ***
Subscribe Async
    [Arguments]    ${filter}
    Connect    ${BROKER}    ${PORT}    alias=sub
    Subscribe    ${filter}    qos=1    timeout=0    alias=sub
