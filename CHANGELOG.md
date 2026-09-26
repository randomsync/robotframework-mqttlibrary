# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Progress towards the next releases is tracked in #39.

## [Unreleased]

### Changed

- Test brokers now run on Mosquitto 2 through `docker compose up --wait`,
  with explicit listener configs and a regenerated password file (#40).

## [0.7.1] - 2020-07-21

### Fixed

- Subscribe in async mode with wildcard topics (#19).
- Listen now waits for the subscription to complete (#20).

### Changed

- Tests use local brokers instead of a public broker (#22).

[Unreleased]: https://github.com/randomsync/robotframework-mqttlibrary/compare/0.7.1...HEAD
[0.7.1]: https://github.com/randomsync/robotframework-mqttlibrary/compare/0.7.0...0.7.1
