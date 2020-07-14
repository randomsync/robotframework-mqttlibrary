| *Settings*    | *Value*
| Resource      | keywords.robot
| Test Timeout  | 30 seconds

| *Test Cases*
| Subscribe with a single level wildcard in topic name
| | [Tags]      | wildcards
| | ${time}     | Get Time      | epoch
| | ${client}   | Catenate      | SEPARATOR=.   | robot.mqtt | ${time}
| | ${topic}    | Set Variable  | Company/+/Data
| | ${message}  | Set Variable  | subscription test message
| | Subscribe Async             | client.id=${client}   | topic=${topic}
| | Publish to MQTT Broker      | topic=Company/test/Data    | message=${message}      | qos=1
| | @{messages}= | Listen       | topic=${topic} | limit=1 | timeout=1
| | Should Be Equal As Strings  | ${messages}[0]    | ${message}
| | [Teardown]  | Unsubscribe and Disconnect | ${topic}

| Subscribe with multi level wildcard in topic name
| | [Tags]      | wildcards
| | ${time}     | Get Time      | epoch
| | ${client}   | Catenate      | SEPARATOR=.   | robot.mqtt | ${time}
| | ${topic}    | Set Variable  | Company/test/Data/#
| | ${message}  | Set Variable  | subscription test message
| | Subscribe Async             | client.id=${client}   | topic=${topic}
| | Publish to MQTT Broker      | topic=Company/test/Data/123/abc    | message=${message}      | qos=1
| | @{messages}= | Listen       | topic=${topic} | limit=1 | timeout=1
| | Should Be Equal As Strings  | ${messages}[0]    | ${message}
| | [Teardown]  | Unsubscribe and Disconnect | ${topic}

| Subscribe with both single level and multi level wildcards in topic name
| | [Tags]      | wildcards
| | ${time}     | Get Time      | epoch
| | ${client}   | Catenate      | SEPARATOR=.   | robot.mqtt | ${time}
| | ${topic}    | Set Variable  | Company/+/Data/#
| | ${message}  | Set Variable  | subscription test message
| | Subscribe Async             | client.id=${client}   | topic=${topic}
| | Publish to MQTT Broker      | topic=Company/test/test/123/abc    | message=messagetest
| | Publish to MQTT Broker      | topic=Company/test/Data/123/abc    | message=messageData
| | @{messages}= | Listen       | topic=${topic} | limit=1 | timeout=1
| | Length should be            | ${messages}       | 1
| | Should Be Equal As Strings  | ${messages}[0]    | messageData
| | Should not contain          | ${messages}       | messagetest
| | [Teardown]  | Unsubscribe and Disconnect | ${topic}

| Subscribe with multiple single level wildcards in topic name
| | [Tags]      | wildcards
| | ${time}     | Get Time      | epoch
| | ${client}   | Catenate      | SEPARATOR=.   | robot.mqtt | ${time}
| | ${topic}    | Set Variable  | Company/+/Data/+/test
| | Subscribe Async             | client.id=${client}   | topic=${topic}
| | Publish to MQTT Broker      | topic=Company/test/Data/123/abc     | message=messageabc
| | Publish to MQTT Broker      | topic=Company/test/Data/123/test    | message=messagetest
| | @{messages}= | Listen       | topic=${topic} | limit=10 | timeout=5
| | Length should be            | ${messages}       | 1
| | Should Be Equal As Strings  | ${messages}[0]    | messagetest
| | Should not contain          | ${messages}       | messageabc
| | [Teardown]  | Unsubscribe and Disconnect | ${topic}
