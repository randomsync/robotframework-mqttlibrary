| *Settings*    | *Value*
| Library       | MQTTLibrary
| Library       | BuiltIn

| *Variables*       | *Value*
#| ${broker.uri}     | mqtt.eclipse.org
| ${broker.uri}     | 127.0.0.1
| ${broker.port}    | 1883
| ${client.id}      | mqtt.test.client
| ${topic}          | test/mqtt_test
| ${sub.topic}      | test/mqtt_test_sub

| *Keywords*    |
| Easy Connect
| | [Arguments] | ${broker.uri}=${broker.uri}   | ${port}=${broker.port}
| | ...         | ${client.id}=${client.id}     | ${clean_session}=${true}
| | Connect     | ${broker.uri} | ${port}       | ${client.id}    | ${clean_session}

| Publish to MQTT Broker
| | [Arguments] | ${broker.uri}=${broker.uri}   | ${port}=${broker.port}
| | ...         | ${client.id}=${client.id}     | ${clean_session}=${true}
| | ...         | ${topic}=${topic}             | ${message}=${EMPTY}
| | ...         | ${qos}=0                      | ${retention}=${false}
| | ...         | ${alias}=pub
| | Connect     | ${broker.uri} | ${port}       | ${client.id}    | ${clean_session}
| | ...         | alias=${alias}
| | Publish     | ${topic}      | ${message}    | ${qos}    | ${retention}
| | ...         | alias=${alias}

| Publish to MQTT Broker and Disconnect
| | [Arguments] | ${broker.uri}=${broker.uri}   | ${port}=${broker.port}
| | ...         | ${client.id}=${client.id}     | ${clean_session}=${true}
| | ...         | ${topic}=${topic}             | ${message}=${EMPTY}
| | ...         | ${qos}=0                      | ${retention}=${false}
| | ...         | ${alias}=pub
| | Connect     | ${broker.uri} | ${port}       | ${client.id}    | ${clean_session}
| | ...         | alias=${alias}
| | Publish     | ${topic}      | ${message}    | ${qos}    | ${retention}
| | ...         | alias=${alias}
| | [Teardown]  | Disconnect    | ${alias}

| Subscribe to MQTT Broker and Validate
| | [Arguments] | ${broker.uri}=${broker.uri}   | ${port}=${broker.port}
| | ...         | ${client.id}=${client.id}     | ${topic}=${topic}
| | ...         | ${message}=${EMPTY}           | ${qos}=1
| | ...         | ${timeout}=1s
| | Connect     | ${broker.uri} | ${port}       | ${client.id}  | ${false}
| | Subscribe and Validate
| | ...         | ${topic}      | ${qos}        | ${message}        | ${timeout}
| | [Teardown]  | Disconnect

| Subscribe and Get Messages
| | [Arguments] | ${broker.uri}=${broker.uri}   | ${port}=${broker.port}
| | ...         | ${client.id}=${client.id}     | ${topic}=${topic}
| | ...         | ${qos}=1                      | ${timeout}=1s
| | ...         | ${limit}=1
| | Connect     | ${broker.uri} | ${port}       | ${client.id}  | ${false}
| | @{messages} | Subscribe     | ${topic} | ${qos} | ${timeout}    | ${limit}
| | [Teardown]  | Disconnect
| | [Return]    | @{messages}

| Subscribe Async
| | [Arguments] | ${broker.uri}=${broker.uri}   | ${port}=${broker.port}
| | ...         | ${client.id}=${client.id}     | ${topic}=${topic}
| | ...         | ${qos}=1                      | ${timeout}=0s
| | ...         | ${limit}=1                    | ${alias}=sub
| | Connect     | ${broker.uri} | ${port}       | ${client.id}  | ${false}
| | ...         | alias=${alias}
| | Subscribe   | ${topic} | ${qos} | ${timeout}    | ${limit}  | alias=${alias}

| Unsubscribe and Disconnect
| | [Arguments] | ${topic}=${topic}     | ${alias}=sub
| | Unsubscribe | ${topic}              | alias=${alias}
| | [Teardown]  | Disconnect All

| Subscribe and Unsubscribe
| | [Arguments] | ${broker.uri}=${broker.uri}   | ${port}=${broker.port}
| | ...         | ${client.id}=${client.id}     | ${topic}=${topic}
| | ...         | ${qos}=1                      | ${timeout}=1s
| | ...         | ${limit}=1
| | Connect     | ${broker.uri} | ${port}       | ${client.id}  | ${false}
| | @{messages} | Subscribe     | ${topic} | ${qos} | ${timeout}    | ${limit}
| | Unsubscribe | ${topic}
| | [Teardown]  | Disconnect
| | [Return]    | @{messages}

| Listen and Get Messages
| | [Arguments] | ${topic}=${topic}   | ${timeout}=1s
| | ...         | ${limit}=1          | ${alias}=sub
| | @{messages} | Listen     | ${topic} | ${timeout}    | ${limit}  | alias=${alias}
| | [Return]    | @{messages}
