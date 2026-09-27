# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Progress towards the next releases is tracked in
[the roadmap issue](https://github.com/randomsync/robotframework-mqttlibrary/issues/39).

## [Unreleased]

### Added

- Every connection now runs paho's background network loop from `Connect`
  to `Disconnect`, so keepalive pings, acknowledgements and incoming messages
  are handled between keywords. Connections no longer drop while a test is
  idle ([#25](https://github.com/randomsync/robotframework-mqttlibrary/issues/25)), messages published right after `Subscribe` arrive
  ([#33](https://github.com/randomsync/robotframework-mqttlibrary/issues/33)), and no message is lost or left unacknowledged ([#28](https://github.com/randomsync/robotframework-mqttlibrary/issues/28))
  ([#45](https://github.com/randomsync/robotframework-mqttlibrary/issues/45)).
- Named connections: an `alias=` argument on `Connect` and on every keyword
  that uses a connection, and the new keywords `Switch Connection` and
  `Disconnect All`. Without an alias, keywords use the connection opened or
  switched to last ([#45](https://github.com/randomsync/robotframework-mqttlibrary/issues/45)).
- A `keepalive=` argument on `Connect` ([#45](https://github.com/randomsync/robotframework-mqttlibrary/issues/45)).
- A pytest unit layer with a fake paho client, and regression tests for
  [#23](https://github.com/randomsync/robotframework-mqttlibrary/issues/23), [#24](https://github.com/randomsync/robotframework-mqttlibrary/issues/24), [#25](https://github.com/randomsync/robotframework-mqttlibrary/issues/25), [#28](https://github.com/randomsync/robotframework-mqttlibrary/issues/28) and [#33](https://github.com/randomsync/robotframework-mqttlibrary/issues/33). CI runs both layers under
  coverage and requires at least 90% ([#45](https://github.com/randomsync/robotframework-mqttlibrary/issues/45)).
- A CI job builds the sdist and wheel, checks their contents and metadata,
  and installs the wheel in a clean environment ([#43](https://github.com/randomsync/robotframework-mqttlibrary/issues/43)).
- Tests run on GitHub Actions for every push to master and every pull
  request, against the docker compose brokers ([#41](https://github.com/randomsync/robotframework-mqttlibrary/issues/41)).

### Changed

- **Breaking:** messages are queued per subscription filter from the moment
  of `Connect`, including persistent-session messages that arrive before
  `Subscribe`. `Subscribe` and `Listen` return the oldest messages first and
  keep the rest for the next `Listen` on the same connection. 0.7 returned
  the newest ones and discarded the others ([#23](https://github.com/randomsync/robotframework-mqttlibrary/issues/23)). Because every
  delivered message is now read and acknowledged, `limit` no longer leaves
  messages on the broker for a later session. Subscribing again to a filter
  keeps its queue. With overlapping filters (`a/#` and `a/1`) each filter
  gets a message once, whether the broker sends one copy or one per
  subscription. One limit: on a broker that sends a single copy, the second
  of two identical messages published back to back to such a topic is
  dropped. Each queue holds up to 10000 messages; beyond that the oldest
  are dropped with a warning. `Listen` fails if the connection drops and
  nothing is queued, and fails on a payload that is not valid UTF-8, dropping
  only that message. `Subscribe` with `timeout=0` returns an empty list
  ([#45](https://github.com/randomsync/robotframework-mqttlibrary/issues/45)).
- **Breaking:** connecting again on an alias that is still connected
  disconnects the old connection with a warning. 0.7 left the old connection
  running in the background. Tests that relied on several such connections
  should name them with `alias=` ([#45](https://github.com/randomsync/robotframework-mqttlibrary/issues/45)).
- **Breaking:** errors carry the broker's reason. A refused `Connect` fails
  with, for example, `Connection to 127.0.0.1:11883 failed: Not authorized`
  instead of `The client disconnected unexpectedly`. An unreachable or
  malformed host fails within the library's timeout and names the host
  ([#24](https://github.com/randomsync/robotframework-mqttlibrary/issues/24)). `Disconnect` on a connection the broker dropped fails with
  `The client disconnected unexpectedly: <reason>` ([#45](https://github.com/randomsync/robotframework-mqttlibrary/issues/45)).
- **Breaking:** `Publish` waits for its own acknowledgement and fails with
  the paho error name, for example `Publish to test failed:
  MQTT_ERR_NO_CONN`, or when the message is not acknowledged within the
  library's timeout. 0.7 only logged a warning. `Subscribe` waits for its
  SUBACK in both modes and fails if the broker refuses the subscription.
  `Unsubscribe` removes only its own filter and no longer stops the network
  loop ([#45](https://github.com/randomsync/robotframework-mqttlibrary/issues/45)).
- `Subscribe And Validate` reads from the same queues as `Listen`, so it can
  be mixed with `Subscribe` on one connection. It consumes the messages that
  do not match. Its error text is unchanged, with the reason appended if the
  connection drops while it waits ([#45](https://github.com/randomsync/robotframework-mqttlibrary/issues/45)).
- `Publish Single` and `Publish Multiple` accept `protocol` as a name
  (`MQTTv31`, `MQTTv311`, `MQTTv5`, any case) or a number, and fail on an
  unknown version ([#45](https://github.com/randomsync/robotframework-mqttlibrary/issues/45)).
- The Robot Framework suites move to `tests/acceptance` ([#45](https://github.com/randomsync/robotframework-mqttlibrary/issues/45)).
- Requires paho-mqtt 2.1 or later below 3, and uses paho's version 2
  callback API. paho-mqtt 1.x is no longer supported; stay on 0.7.x if you
  need it. paho-mqtt 2.0.0 is excluded because its `Client.protocol` property
  recurses forever. Existing keyword names and arguments are unchanged, and
  `Publish Single` and `Publish Multiple` still default to MQTT v3.1. CI runs
  the tests on paho-mqtt 2.1.0 and on the latest 2.x ([#34](https://github.com/randomsync/robotframework-mqttlibrary/issues/34),
  [#44](https://github.com/randomsync/robotframework-mqttlibrary/issues/44)).
  Based on [PR #36](https://github.com/randomsync/robotframework-mqttlibrary/pull/36)
  by [@lcaiffa](https://github.com/lcaiffa).

  **Breaking:** when the broker refuses the connection, `Publish Single` and
  `Publish Multiple` fail with paho 2's reason text, for example
  `Not authorized` or `Bad user name or password`, instead of paho 1's
  `Connection Refused: not authorised.` Update any `Run Keyword And Expect
  Error` patterns that match the old text.
- Packaging moves to `pyproject.toml` built with hatchling, replacing
  `setup.py`, `MANIFEST.in` and `requirements.txt`. The package requires
  Python 3.9 or later and declares its license as the SPDX expression
  `Apache-2.0` ([#43](https://github.com/randomsync/robotframework-mqttlibrary/issues/43)).
- Test brokers now run on Mosquitto 2 through `docker compose up --wait`,
  with explicit listener configs and a regenerated password file ([#40](https://github.com/randomsync/robotframework-mqttlibrary/issues/40)).

### Removed

- The Travis CI configuration and badge, since travis-ci.org has shut down.
  That configuration also published tagged releases to PyPI, which stopped
  working when Travis shut down. Until a GitHub Actions release workflow
  lands ([#47](https://github.com/randomsync/robotframework-mqttlibrary/issues/47)), releases are built and uploaded by hand, starting
  with 0.7.2 ([#42](https://github.com/randomsync/robotframework-mqttlibrary/issues/42)). Pushing a tag does not publish anything.

## [0.7.2] - 2026-09-26

Released from the `0.7.x` branch for suites that need paho-mqtt 1.x.

### Fixed

- Declare `paho-mqtt>=1.3,<2`. 0.7.x does not work with paho-mqtt 2, and
  until then a fresh install pulled it in and failed on the first keyword
  ([#29](https://github.com/randomsync/robotframework-mqttlibrary/issues/29), [#34](https://github.com/randomsync/robotframework-mqttlibrary/issues/34)). No library code changed.

## [0.7.1] - 2020-07-21

### Fixed

- Subscribe in async mode with wildcard topics ([#19](https://github.com/randomsync/robotframework-mqttlibrary/pull/19)).
- Listen now waits for the subscription to complete ([#20](https://github.com/randomsync/robotframework-mqttlibrary/pull/20)).

### Changed

- Tests use local brokers instead of a public broker ([#22](https://github.com/randomsync/robotframework-mqttlibrary/pull/22)).

[Unreleased]: https://github.com/randomsync/robotframework-mqttlibrary/compare/0.7.1...HEAD
[0.7.2]: https://github.com/randomsync/robotframework-mqttlibrary/compare/0.7.1...0.7.2
[0.7.1]: https://github.com/randomsync/robotframework-mqttlibrary/compare/0.7.0...0.7.1
