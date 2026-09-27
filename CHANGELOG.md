# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Progress towards the next releases is tracked in
[the roadmap issue](https://github.com/randomsync/robotframework-mqttlibrary/issues/39).

## [Unreleased]

### Added

- A CI job builds the sdist and wheel, checks their contents and metadata,
  and installs the wheel in a clean environment ([#43](https://github.com/randomsync/robotframework-mqttlibrary/issues/43)).
- Tests run on GitHub Actions for every push to master and every pull
  request, against the docker compose brokers ([#41](https://github.com/randomsync/robotframework-mqttlibrary/issues/41)).

### Changed

- Requires paho-mqtt 2.0 or later below 3, and uses paho's version 2
  callback API. paho-mqtt 1.x is no longer supported; stay on 0.7.x if you
  need it. Keyword names, arguments and error messages are unchanged, and
  `Publish Single` and `Publish Multiple` still default to MQTT v3.1. CI runs
  the tests on paho-mqtt 2.0.0 and on the latest 2.x ([#34](https://github.com/randomsync/robotframework-mqttlibrary/issues/34),
  [#44](https://github.com/randomsync/robotframework-mqttlibrary/issues/44)).
  Based on [PR #36](https://github.com/randomsync/robotframework-mqttlibrary/pull/36)
  by [@lcaiffa](https://github.com/lcaiffa).
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
