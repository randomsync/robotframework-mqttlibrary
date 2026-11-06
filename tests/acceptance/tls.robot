*** Settings ***
Documentation     The TLS broker: server TLS on ``MQTT_TLS_PORT`` and mutual
...               TLS on ``MQTT_MTLS_PORT``, with the certificates from
...               ``scripts/gen-certs.sh``.
Resource          common.resource
Test Setup        Create Unique Topic
Test Teardown     Disconnect All
Suite Teardown    Disconnect All
Test Timeout      30 seconds
Force Tags        tls    issue-14

*** Test Cases ***
Publish and subscribe over TLS
    Connect    ${BROKER}    ${TLS PORT}    ca_certs=${CERTS}/ca.crt
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    over tls    qos=1
    Listen Should Return    ${TOPIC}    over tls

Publish and subscribe over mutual TLS
    Connect    ${BROKER}    ${MTLS PORT}    ca_certs=${CERTS}/ca.crt
    ...    certfile=${CERTS}/client.crt    keyfile=${CERTS}/client.key
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    over mutual tls    qos=1
    Listen Should Return    ${TOPIC}    over mutual tls

A protected client key is decrypted with keyfile_password
    Connect    ${BROKER}    ${MTLS PORT}    ca_certs=${CERTS}/ca.crt
    ...    certfile=${CERTS}/client.crt    keyfile=${CERTS}/client-encrypted.key
    ...    keyfile_password=client-key-password
    Connected Should Be    ${True}

A wrong key password fails before connecting
    Run Keyword And Expect Error
    ...    Cannot load certfile ${CERTS}/client.crt with keyfile ${CERTS}/client-encrypted.key: *
    ...    Connect    ${BROKER}    ${MTLS PORT}    ca_certs=${CERTS}/ca.crt
    ...    certfile=${CERTS}/client.crt    keyfile=${CERTS}/client-encrypted.key
    ...    keyfile_password=wrong

Mutual TLS without a client certificate fails
    Run Keyword And Expect Error    Connection to ${BROKER}:${MTLS PORT} failed: *
    ...    Connect    ${BROKER}    ${MTLS PORT}    ca_certs=${CERTS}/ca.crt

A broker certificate from another CA fails verification
    Run Keyword And Expect Error
    ...    Connection to ${BROKER}:${TLS PORT} failed: *CERTIFICATE_VERIFY_FAILED*
    ...    Connect    ${BROKER}    ${TLS PORT}    ca_certs=${CERTS}/other-ca.crt

The system CAs do not trust the test broker
    Run Keyword And Expect Error
    ...    Connection to ${BROKER}:${TLS PORT} failed: *CERTIFICATE_VERIFY_FAILED*
    ...    Connect    ${BROKER}    ${TLS PORT}    tls=${True}

Insecure connects without verifying the broker
    Connect    ${BROKER}    ${TLS PORT}    ca_certs=${CERTS}/other-ca.crt
    ...    insecure=${True}
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    unverified    qos=1
    Listen Should Return    ${TOPIC}    unverified

TLS version can be pinned
    Connect    ${BROKER}    ${TLS PORT}    ca_certs=${CERTS}/ca.crt
    ...    tls_version=TLSv1.2    alias=v12
    Connect    ${BROKER}    ${TLS PORT}    ca_certs=${CERTS}/ca.crt
    ...    tls_version=TLSv1.3    alias=v13
    Connected Should Be    ${True}    v12
    Connected Should Be    ${True}    v13

MQTT 5 works over TLS
    Connect    ${BROKER}    ${TLS PORT}    ca_certs=${CERTS}/ca.crt
    ...    protocol=MQTTv5
    Subscribe    ${TOPIC}    qos=1    timeout=0
    Publish    ${TOPIC}    v5 over tls    qos=1
    Listen Should Return    ${TOPIC}    v5 over tls

A plain connection to the TLS port fails
    Run Keyword And Expect Error    Connection to ${BROKER}:${TLS PORT} failed: *
    ...    Connect    ${BROKER}    ${TLS PORT}

A missing CA file fails before connecting
    Run Keyword And Expect Error
    ...    Cannot load ca_certs ${CERTS}/missing.crt: *
    ...    Connect    ${BROKER}    ${TLS PORT}    ca_certs=${CERTS}/missing.crt
