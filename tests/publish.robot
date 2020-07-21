*** Settings ***
| Library       | MQTTLibrary
| Library       | Collections
| Test Timeout  | 30 seconds

*** Variables ***
| ${broker.uri}     | 127.0.0.1
| ${broker.port}    | 1883
| ${client.id}      | mqtt.test.client
| ${topic}          | test/mqtt_test
| ${sub.topic}      | test/mqtt_test_sub

** Test Cases ***
| Publish a single message and disconnect
| | ${time}     | Get Time      | epoch
| | ${message}  | Catenate      | test message      | ${time}
| | Publish Single              | topic=${topic}    | payload=${message}
| | ...                         | hostname=${broker.uri}

| Publish multiple messages and disconnect
| | ${msg1} | Create Dictionary | topic=${topic}    | payload=message 1
| | ${msg2} | Create Dictionary | topic=${topic}    | payload=message 2
| | ${msg3} | Create Dictionary | topic=${topic}    | payload=message 3
| | @{msgs} | Create List       | ${msg1} | ${msg2} | ${msg3}
| | Publish Multiple            | msgs=${msgs}      | hostname=${broker.uri}
