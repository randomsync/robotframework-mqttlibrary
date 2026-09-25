# MQTTLibrary Modernization

This document describes how `robotframework-mqttlibrary` moves from its 2020
state (paho-mqtt 1.x, Robot Framework 3, Python 2.7/3.7, Travis CI) to a
maintained library on paho-mqtt 2.x, Robot Framework 4-7 and Python 3.9+,
with GitHub Actions CI.

Progress is tracked in the roadmap issue. Comments and corrections are
welcome there or as PRs against this file.

---

## 1. Where things stand

### 1.1 What is broken

The library fails on the first keyword with any paho-mqtt 2.x release:

```
ValueError: Unsupported callback API version: version 2.0 added a
callback_api_version, see docs/migrations.rst for details
```

`mqtt.Client(client_id, clean_session)` passes the client id into what paho
2.0 made the first positional parameter, `callback_api_version` (#34).

| Item              | Today                                   | Target                          |
|-------------------|-----------------------------------------|---------------------------------|
| paho-mqtt         | `~=1.1` in requirements, unpinned in `setup.py` (#29) | `>=2.0,<3`         |
| Robot Framework   | `~=3.0`                                 | `>=4`, tested on 4.1 and latest 7.x |
| Python            | 2.7 / 3.7 classifiers                   | 3.9 - 3.14                      |
| CI                | travis-ci.org (shut down)               | GitHub Actions                  |
| Packaging         | `setup.py`                              | `pyproject.toml`                |
| Docs              | `docs/index.html` generated in 2019     | Regenerated every release       |

### 1.2 Test broker fixtures

The tracked `mosquitto/mosquitto.conf` is the configuration for the
**authenticated** test broker (port 11883); the anonymous broker on 1883 has
always run with no configuration. That relied on Mosquitto 1.x defaults.
Mosquitto 2.x binds to localhost only unless a `listener` is declared and
refuses anonymous clients by default, so both brokers need explicit configs:

```
# anonymous broker
listener 1883
allow_anonymous true
```

```
# authenticated broker
listener 1883
allow_anonymous false
listener 9001
protocol websockets
password_file /mosquitto/config/passwd_file
```

A `docker-compose.yml` starts both (and, from 1.1, a TLS broker) with
health checks, so local runs and CI use the same fixtures.

### 1.3 Known design problems

These are independent of the paho version and explain most open issues.

1. **The network loop only runs inside keywords.** Every keyword calls
   `client.loop()` in a polling loop. Between keywords nothing services the
   socket, so keepalive pings are missed, the broker drops the client, and
   the next Publish fails with error 4 (`MQTT_ERR_NO_CONN`). Root cause of
   #25, #28 and #33.
2. **Two threads can service one socket.** After an async Subscribe starts
   `loop_start()`, later keywords still call `loop()` from the main thread,
   which paho does not support. `Disconnect` never stops the background
   thread, so it leaks.
3. **One client per library instance.** A test cannot be publisher and
   subscriber at once without relying on the leak above. The existing async
   tests do exactly that: `Connect` replaces the client while the previous
   one's thread keeps collecting messages.
4. **`Connect` returns the raw paho client**, so tests assert on private
   attributes such as `_client_id`.
5. **SUBACK tracking is a single shared flag**, not tied to a message id.
   Async Subscribe can return before its own SUBACK and messages published
   right after can be lost (#33).
6. **Payloads are always decoded as UTF-8**, so binary payloads fail (#31).
7. **Only payload strings are returned**; topic, QoS and retain are dropped
   (#32).
8. **Subscribe and Listen reset the message list**, dropping messages that
   arrived between two quick calls (a fix was proposed in #23).
9. **`Unsubscribe` stops the background loop for all topics.**
10. **A hard-coded `sleep(1)`** works around QoS 1 acknowledgements.
11. **Errors hide the broker's reason**: a wrong password reports "The client
    disconnected unexpectedly" instead of "Not authorized".
12. **`Subscribe And Validate` and `Subscribe` both replace `on_message`**,
    so mixing them on one connection breaks one of them.
13. **Persistent-session delivery works by timing.** Tests using
    `clean_session=False` depend on queued messages arriving after Connect
    returns but before Subscribe installs its handler. Any design that keeps
    the socket serviced must buffer messages from the moment of Connect.
14. **`limit` leaves messages unread on the socket.** A Subscribe with
    `limit=1` reads one packet and disconnects; the rest are redelivered in a
    later session. A background loop reads and acknowledges everything, so
    this behaviour changes in 1.0 (see 4.1 item 10).
15. **No TLS, websockets, last will, keepalive or MQTT v5** on `Connect`
    (#14, PR #26).
16. **`Publish Single` / `Publish Multiple` default to MQTT v3.1**, inherited
    from paho 1.1. paho itself has defaulted to v3.1.1 since 1.2.

---

## 2. paho-mqtt 2.x in brief

- `Client(callback_api_version, client_id="", clean_session=None, ...,
  reconnect_on_failure=True)`; the callback API version is now the first
  positional argument.
- `CallbackAPIVersion.VERSION2` gives one callback signature per event across
  MQTT versions, with `ReasonCode` and `Properties` objects.
- `publish()` returns `MQTTMessageInfo` with `wait_for_publish(timeout)`.
- Also available and not yet exposed by this library: MQTT v5 properties and
  subscribe options, websockets transport, TLS options, proxies,
  `connect_timeout`, `enable_logger()`, `topic_matches_sub()`.

---

## 3. Releases

| Version     | Nature        | Contents |
|-------------|---------------|----------|
| `0.7.2`     | metadata only | Pins `paho-mqtt>=1.1,<2` for users who cannot move yet (#29). |
| `1.0.0rc1`, `1.0.0` | breaking | paho 2.x, background network loop, named connections, `keepalive=`, `pyproject.toml`, GitHub Actions, rewritten tests. |
| `1.1.0`     | additive      | Connect options (TLS, websockets, last will, credentials), message objects with topic and raw bytes, assertion keywords. |
| `1.2.0`     | additive, on request | MQTT v5 properties and subscribe options, request/response, proxy support. |

**Why 1.0.0 and not 0.8.0.** Suites pinned to `~=0.7` resolve to
`>=0.7,<1.0`. A 0.8.0 on paho 2 would install silently into paho 1.x
environments and fail. 1.0.0 requires an explicit upgrade.

**Release candidate.** `1.0.0rc1` is published first. pip ignores
pre-releases unless asked (`pip install --pre`), so people affected by #34
and #25 can try it without affecting anyone else.

**Mechanics.** Tags stay bare (`1.0.0`). Releases publish from GitHub
Actions with PyPI trusted publishing, so no API token is stored. Each tag
gets a GitHub Release whose notes come from `CHANGELOG.md`. The version
lives in `src/MQTTLibrary/version.py` only.

---

## 4. 1.0.0: compatibility and stability

Goal: the same keywords, working on paho 2 / RF 4-7 / Python 3.9+, with
connections that stay alive between keywords.

### 4.1 Library design

1. **Connection object.** A `_Connection` owns the paho client, its message
   queues and its synchronization events. The library keeps a registry of
   them by alias; without an alias, a default one is used.
2. **Client construction.** `CallbackAPIVersion.VERSION2`,
   `reconnect_on_failure=False` (otherwise a wrong password retries forever
   in the background instead of failing the keyword), and `connect_timeout`
   equal to the library's loop timeout so an unreachable host fails within
   the same bound as everything else.
3. **Background loop.** `loop_start()` at Connect, `loop_stop()` at
   Disconnect. No keyword calls `loop()`. Keywords wait on
   `threading.Event`s set from callbacks, bounded by the loop timeout. A
   failed connect stops the loop before raising.
4. **Per-operation acknowledgement.** Connect, Subscribe, Unsubscribe and
   Publish each wait for their own acknowledgement by message id. Subscribe
   returns only after its SUBACK, in both sync and async modes.
5. **Message queues fed from Connect.** A single `on_message`, installed
   before connecting, puts each message into the queue of every subscription
   filter that matches it, or into an "unclaimed" queue when none match.
   Registering a filter first moves matching unclaimed messages into its
   queue. This keeps persistent-session messages, lets overlapping filters
   (`a/#` and `a/1`) both receive a message, and means Listen never drops
   anything. One lock per connection guards the filter registry, since
   keywords change it while the network thread reads it. Subscribing again
   to an existing filter keeps its queue.
6. **Errors carry the broker's reason**, for example
   `Connection to 127.0.0.1:11883 failed: Not authorized`.
7. **Named connections.** `Connect ... alias=`, `Switch Connection`,
   `Disconnect All`, and an `alias=` argument on connection-bound keywords.
   Connecting again on an alias that is still connected disconnects the old
   connection with a warning, rather than leaking it or failing.
8. **`Get Connection Info`** returns host, port, client id, protocol,
   keepalive and connected state. `Connect` no longer returns the paho
   client.
9. **Robot-native arguments.** Type hints on every keyword argument so Robot
   Framework converts values; paho logs routed to the Robot log at DEBUG.
10. **`limit` and ordering.** `limit` caps how many messages a call returns;
    the rest stay queued for the next Listen on the same connection. Results
    are oldest first. (0.7 returned the newest N and discarded the rest.)
11. **Kept as-is in 1.x:** `Set Username And Password` (deprecated in 1.1
    once Connect takes credentials, removed in 2.0), the `Publish Single` /
    `Publish Multiple` protocol default, and the `Subscribe And Validate`
    error text. Sync `Subscribe` (with a timeout) becomes shorthand for
    Subscribe followed by Listen.

### 4.2 Behaviour changes in 1.0

- Requires paho-mqtt 2.x and Python 3.9 or later.
- `Connect` returns nothing; use `Get Connection Info`.
- `limit` returns the oldest messages and keeps the rest (item 10).
- Connecting again on a connected alias disconnects the old connection with a
  warning.
- Error messages include the broker's reason code.
- Tests that relied on several leaked connections should name them with
  `alias=`.

### 4.3 Packaging

`pyproject.toml` with hatchling, `requires-python = ">=3.9"`,
`paho-mqtt>=2.0,<3`, `robotframework>=4`. `setup.py`, `MANIFEST.in` and
`requirements.txt` are removed; development dependencies move to a `dev`
extra.

---

## 5. 1.1.0: features

All additive; 1.0 keywords keep their signatures and return types.

- **Connect options:** `protocol=`, `transport=websockets`, `ws_path=`,
  `ws_headers=`, `username=`, `password=`, TLS (`ca_certs=`, `certfile=`,
  `keyfile=`, `keyfile_password=`, `tls_version=`, `ciphers=`, `insecure=`),
  `clean_start=`, `session_expiry=`, `reconnect_on_failure=` and reconnect
  delays. `Set Last Will` before Connect. Closes #14; carries forward the
  `transport=` option from PR #26.
- **Messages:** `Get Messages` returns objects with `topic`, `payload`,
  `qos`, `retain`, `properties`, `timestamp` (#32). `decode=${False}` returns
  raw bytes (#31). `Clear Messages`. A `max_queue` bound per connection.
  `Publish` accepts bytes and returns the message id.
- **Assertions:** `Wait Until Message Received`, `Message Count Should Be`,
  `Payload Should Match`, `Should Be Connected`, `Should Not Be Connected`.

1.2.0, only when requested: MQTT v5 publish properties and subscribe options,
`Request And Wait For Response`, proxy support, `Subscribe Simple`,
`Clear Retained Message`, shared subscriptions.

---

## 6. Tests and CI

### 6.1 Two layers

- **Unit tests (pytest, no broker)** against a fake paho client: connection
  state, error text, argument conversion, queue dispatch and locking,
  aliases. Most branch coverage comes from here.
- **Acceptance tests (Robot, real Mosquitto brokers)**: `connect`,
  `publish`, `subscribe`, `wildcards`, `auth`, `connections`, and from 1.1
  `tls` and `websockets`.

Rules: a unique topic per test so suites can run in parallel; broker
addresses from environment variables with local defaults; no `Sleep` except
in the keepalive test; `Disconnect All` in suite teardown.

### 6.2 Regression tests for open issues

| Issue | Test |
|-------|------|
| #33 | Connect, Subscribe, Publish immediately, message received, no Sleep |
| #28 | 200 QoS 1 messages, `limit=0`, all 200 received |
| #25 | `keepalive=2`, wait 5 s, Publish succeeds, still connected |
| #24 | Unreachable host (`192.0.2.1`) fails within the timeout and names the host |
| #23 | Two Listen calls with publishes in between lose nothing |
| #31 | Non-UTF-8 payload round-trips as bytes |
| #32 | `a/#` subscription reports each message's topic |
| #14 | TLS suite: server TLS, mutual TLS, wrong CA |
| #29, #34 | CI legs on the minimum and latest supported paho and Robot Framework |

Plus: no leaked threads after Disconnect, persistent-session delivery without
Sleep, two named connections in one test, and the new `limit` behaviour.

### 6.3 CI

GitHub Actions on Linux runners:

- **lint:** ruff, and a libdoc build that fails on docstring errors.
- **test:** Python 3.9-3.14 with the latest Robot Framework and paho, plus a
  minimum-versions leg (Robot Framework 4.1, paho 2.0.0). Brokers from
  `docker compose up --wait`. Robot logs uploaded on every run. Combined
  coverage of at least 90%.
- **build:** sdist and wheel, `twine check`, install and import the wheel.
- **publish (tags):** trusted publishing to PyPI, a check that
  `docs/index.html` matches the released code, and a GitHub Release.

A `Makefile` gives the same steps locally: `make brokers`, `make test`,
`make docs`, `make lint`.

---

## 7. Order of work

1. Broker fixtures, compose file, CHANGELOG.
2. CI running the existing suite unchanged, as a baseline.
3. `0.7.2` with the paho pin.
4. `pyproject.toml`.
5. paho 2 migration, building on PR #36.
6. Background loop, queues and named connections, with the regression tests.
7. Type hints, `Get Connection Info`, test suite modernization, lint.
8. `1.0.0rc1`, about two weeks of feedback, then `1.0.0`.
9. 1.1 features: Connect options, then messages, then assertions.
10. `1.1.0`.

## 8. Credits

This plan builds on work proposed in PRs #36 (paho 2 migration), #35 (an
earlier paho 2 attempt), #27 (moving to a background loop), #26 (websockets
transport) and #23 (keeping messages between Listen calls). Contributors will
be credited in the CHANGELOG entry for the release that carries their idea.
