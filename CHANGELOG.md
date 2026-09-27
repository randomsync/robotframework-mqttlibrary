# Changelog

All notable changes to the 0.7.x line are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The 0.7.x line receives only fixes that keep it installable; new work happens
on master. See [the roadmap](https://github.com/randomsync/robotframework-mqttlibrary/issues/39).

## [0.7.2] - 2026-09-26

### Fixed

- Declare `paho-mqtt>=1.3,<2`. 0.7.x does not work with paho-mqtt 2, and
  until now a fresh install pulled it in and failed on the first keyword
  ([#29](https://github.com/randomsync/robotframework-mqttlibrary/issues/29), [#34](https://github.com/randomsync/robotframework-mqttlibrary/issues/34)). The lower bound is 1.3 because
  the library imports `paho.mqtt.matcher`, which earlier releases lack.
  No library code changed.

### Changed

- Package classifiers list Python 3 only, replacing Python 2.7 and 3.7.
- Tests run on GitHub Actions against the installed package, on both
  paho-mqtt 1.3.0 and the latest 1.x, with Mosquitto 2 brokers started by
  `docker compose up --wait`. Travis CI, which has shut down, is removed.

## [0.7.1] - 2020-07-21

### Fixed

- Subscribe in async mode with wildcard topics ([#19](https://github.com/randomsync/robotframework-mqttlibrary/pull/19)).
- Listen now waits for the subscription to complete ([#20](https://github.com/randomsync/robotframework-mqttlibrary/pull/20)).

### Changed

- Tests use local brokers instead of a public broker ([#22](https://github.com/randomsync/robotframework-mqttlibrary/pull/22)).

[0.7.2]: https://github.com/randomsync/robotframework-mqttlibrary/compare/0.7.1...0.7.2
[0.7.1]: https://github.com/randomsync/robotframework-mqttlibrary/compare/0.7.0...0.7.1
