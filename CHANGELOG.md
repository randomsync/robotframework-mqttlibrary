# Changelog

All notable changes to the 0.7.x line are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The 0.7.x line receives only fixes that keep it installable; new work happens
on master. See [the roadmap](https://github.com/randomsync/robotframework-mqttlibrary/issues/39).

## [0.7.2] - Unreleased

### Fixed

- Declare `paho-mqtt>=1.1,<2`. 0.7.x does not work with paho-mqtt 2, and
  until now a fresh install pulled it in and failed on the first keyword
  ([#29](https://github.com/randomsync/robotframework-mqttlibrary/issues/29), [#34](https://github.com/randomsync/robotframework-mqttlibrary/issues/34)). No library code changed.

### Changed

- Tests run on GitHub Actions against Mosquitto 2 brokers started with
  `docker compose up --wait`. Travis CI, which has shut down, is removed.

## [0.7.1] - 2020-07-21

### Fixed

- Subscribe in async mode with wildcard topics ([#19](https://github.com/randomsync/robotframework-mqttlibrary/pull/19)).
- Listen now waits for the subscription to complete ([#20](https://github.com/randomsync/robotframework-mqttlibrary/pull/20)).

### Changed

- Tests use local brokers instead of a public broker ([#22](https://github.com/randomsync/robotframework-mqttlibrary/pull/22)).

[0.7.2]: https://github.com/randomsync/robotframework-mqttlibrary/compare/0.7.1...0.7.2
[0.7.1]: https://github.com/randomsync/robotframework-mqttlibrary/compare/0.7.0...0.7.1
