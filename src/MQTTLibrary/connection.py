"""One MQTT connection: the paho client, its message queues and the state
that keywords wait on.

paho runs the network loop in a background thread (``loop_start()``), so the
callbacks below run on that thread while keywords run on Robot Framework's
main thread. Everything the two share is guarded by ``self._cond``, one
``threading.Condition`` per connection. Callbacks only update state and
notify, except that ``_on_connect`` renews subscriptions after a reconnect.
They never log, because Robot Framework ignores log messages from other
threads. Keyword-side methods never call into paho while holding
``self._cond``: paho takes its own locks around callbacks, so doing so could
deadlock.
"""

import collections
import copy
import dataclasses
import logging
import re
import threading
import time
from typing import Union

import paho.mqtt.client as mqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties
from robot.api import logger

# The most messages a queue holds by default; the library's max_queue
# argument changes it. When a queue is full the oldest message is dropped,
# and the next Listen on that filter warns. The unclaimed queue holds
# messages that match no registered filter, for example persistent-session
# messages the broker delivers between CONNACK and SUBSCRIBE, until a
# Subscribe claims them.
QUEUE_LIMIT = 10000

# paho logs here. Robot Framework shows Python logging in its log at the
# matching level, so paho's messages appear with --loglevel DEBUG. Messages
# from the network thread are dropped, as for any non-main thread.
PAHO_LOGGER = logging.getLogger("MQTTLibrary.paho")

# How long a late SUBACK or UNSUBACK for an operation that timed out is
# recognised and discarded. After that the mid is free again, so an
# acknowledgement that never came cannot block a later operation that reuses
# the mid once paho's 16-bit counter wraps.
ABANDONED_ACK_SECONDS = 60


# eq=False: compared and hashed by identity. Field equality would compare
# timestamps, and hashing would fail on the properties dict.
@dataclasses.dataclass(frozen=True, eq=False)
class Message:
    """A received message.

    The queues hold ``payload`` as bytes; keywords return it decoded as
    UTF-8 unless asked for bytes. ``properties`` maps MQTT 5 property names,
    such as ``ContentType`` or ``UserProperty``, to their values, and is
    empty for earlier protocol versions. ``timestamp`` is when the message
    arrived, in seconds since the epoch. Each queue holds its own object.
    """

    topic: str
    payload: Union[bytes, str]
    qos: int
    retain: bool
    properties: dict
    timestamp: float


class _Copies(object):
    """A message just queued for overlapping filters, while the broker may
    still send copies of it, one per further matching subscription."""

    def __init__(self, key, remaining, qos, entries):
        self.key = key
        self.remaining = remaining
        self.qos = qos
        # [filter, queue, the Message queued for it]
        self.entries = entries


class _Queue(collections.deque):
    """A bounded message queue that counts the messages it dropped."""

    def __init__(self, maxlen):
        super().__init__(maxlen=maxlen)
        self.dropped = 0

    def put(self, message):
        if len(self) == self.maxlen:
            self.dropped += 1
        self.append(message)


class _Connection(object):
    def __init__(
        self,
        alias,
        host,
        port,
        client_id,
        clean_session,
        keepalive,
        timeout,
        username=None,
        password=None,
        *,
        protocol=mqtt.MQTTv311,
        transport="tcp",
        ws_path=None,
        ws_headers=None,
        tls=None,
        will=None,
        reconnect=None,
        clean_start=None,
        session_expiry=None,
        max_queue=QUEUE_LIMIT,
    ):
        """``tls`` is an ``ssl.SSLContext``, ``will`` a (topic, payload,
        qos, retain) tuple and ``reconnect`` a (min, max) tuple of delays in
        seconds that turns reconnecting on. ``clean_start`` and
        ``session_expiry`` are for MQTT 5 only, and ``clean_session`` is
        ignored with it. ``max_queue`` bounds every message queue."""
        self.alias = alias
        self.host = host
        self.port = port
        self.protocol = protocol
        self.keepalive = keepalive
        self.timeout = timeout
        self.address = "%s:%s" % (host, port)
        self.reconnect = reconnect is not None
        self._clean_start = clean_start
        self._session_expiry = session_expiry
        self.max_queue = max_queue

        self._cond = threading.Condition()
        self._filters = {}
        # The QoS of each acknowledged subscription, to subscribe again after
        # a reconnect.
        self._qos = {}
        # Subscriptions renewed after a reconnect whose SUBACK has not come:
        # mid -> (time sent, topics). Then the ones the broker refused:
        # topic -> reason code.
        self._renewals = {}
        self._refused = {}
        self._unclaimed = _Queue(max_queue)
        self._duplicates = None
        self._acks = {}
        self._abandoned = {}
        self._connack = None
        self._disconnect_reason = None
        self._thread = None

        # reconnect_on_failure starts False, unlike paho's default, so a
        # refused first connection fails the keyword. With it on, paho 2.1
        # also answers CONNACK 1 and 2 by falling back to MQTT 3.1 or a random
        # client id. _on_connect turns it on after the first successful
        # CONNACK when reconnecting was asked for. paho raises ValueError here
        # for an empty client id with clean_session=False; that message is
        # the keyword failure. paho requires clean_session None with MQTT 5.
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            clean_session=None if protocol == mqtt.MQTTv5 else clean_session,
            protocol=protocol,
            transport=transport,
            reconnect_on_failure=False,
        )
        self.client.enable_logger(PAHO_LOGGER)
        # Bounds the TCP connect in client.connect(), so an unreachable host
        # fails within the same timeout as everything else.
        self.client.connect_timeout = timeout
        if username:
            self.client.username_pw_set(username, password)
        if transport == "websockets":
            self.client.ws_set_options(path=ws_path or "/mqtt", headers=ws_headers)
        if tls is not None:
            self.client.tls_set_context(tls)
        if will is not None:
            self.client.will_set(*will)
        if reconnect is not None:
            self.client.reconnect_delay_set(*reconnect)

        # on_message is set before connecting, so messages the broker sends
        # right after CONNACK are queued, not lost.
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_subscribe = self._on_ack
        self.client.on_unsubscribe = self._on_ack

    @property
    def _connected(self):
        return (
            self._connack is not None
            and not self._connack.is_failure
            and self._disconnect_reason is None
        )

    # Keyword-side operations, called from Robot Framework's thread.

    def info(self):
        return {
            "alias": self.alias,
            "host": self.host,
            "port": self.port,
            # What paho sends, not the argument: paho has no public
            # accessor for it in 2.1.
            "client_id": self.client._client_id.decode(),
            "protocol": self.protocol.name,
            "keepalive": self.keepalive,
            "connected": self._connected,
        }

    def open(self):
        """Connect, start the network loop and wait for CONNACK."""
        options = {}
        if self._clean_start is not None:
            options["clean_start"] = self._clean_start
        if self._session_expiry is not None:
            properties = Properties(PacketTypes.CONNECT)
            properties.SessionExpiryInterval = self._session_expiry
            options["properties"] = properties
        try:
            self.client.connect(self.host, self.port, self.keepalive, **options)
        except (OSError, UnicodeError) as exc:
            # OSError covers refused, unreachable and unresolvable hosts, and
            # TLS and websockets handshake failures. UnicodeError comes from
            # the IDNA encoding of a malformed name such as 172..0.0.1.
            raise RuntimeError(
                "Connection to %s failed: %s" % (self.address, exc)
            ) from None
        self.client.loop_start()
        self._thread = self.client._thread

        with self._cond:
            self._cond.wait_for(
                lambda: (
                    self._connack is not None or self._disconnect_reason is not None
                ),
                self.timeout,
            )
            if self._connected:
                return
            connack = self._connack
            reason = self._disconnect_reason

        if connack is not None:
            # A refused CONNACK, or a disconnect right after accepting.
            reason = connack if connack.is_failure else reason
        elif reason is not None:
            # With MQTT 3.1.1 and reconnect_on_failure=False, paho does not
            # report CONNACK codes 1 (unacceptable protocol version) and 2
            # (identifier rejected); it closes the connection instead.
            reason = (
                "the broker closed the connection without accepting "
                "it (%s). It may have rejected the protocol version or "
                "the client id" % reason
            )
        else:
            reason = "no CONNACK within %s seconds" % self.timeout
        # Closes the socket if it is still open, for example after a timeout.
        self.client.disconnect()
        self._stop()
        raise RuntimeError("Connection to %s failed: %s" % (self.address, reason))

    def close(self):
        """Disconnect and stop the network loop.

        Returns False if the broker did not confirm the disconnect, or the
        network thread did not end, within the timeout. Raises if the
        connection was lost before or during the disconnect, unless
        reconnecting is on.
        """
        confirmed = True
        if self._connected:
            self.client.disconnect()
            with self._cond:
                confirmed = self._cond.wait_for(
                    lambda: self._disconnect_reason is not None, self.timeout
                )
        elif self.reconnect:
            # Stops paho's reconnect attempts, which check its state between
            # tries.
            self.client.disconnect()
        stopped = self._stop()
        if stopped and self.reconnect and self.client.socket() is not None:
            # A reconnect finished while the loop was stopping. With the loop
            # gone, paho writes the DISCONNECT and closes the socket at once,
            # so the broker does not publish the last will.
            self.client.disconnect()
        reason = self._disconnect_reason
        if reason is not None and reason.is_failure and not self.reconnect:
            raise RuntimeError("The client disconnected unexpectedly: %s" % reason)
        return confirmed and stopped

    def publish(self, topic, payload, qos, retain):
        """Publish and wait for the acknowledgement. Returns the mid."""
        info = self.client.publish(topic, payload, qos, retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(
                "Publish to %s failed: %s%s"
                % (topic, _error_name(info.rc), self._lost())
            )
        info.wait_for_publish(self.timeout)
        if not info.is_published():
            raise RuntimeError(
                "Publish to %s not acknowledged within %s "
                "seconds%s" % (topic, self.timeout, self._lost())
            )
        return info.mid

    def subscribe(self, topic, qos):
        """Register ``topic`` as a filter, subscribe and wait for SUBACK."""
        created = self.register(topic)
        try:
            rc, mid = self.client.subscribe(topic, qos)
            if rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(
                    "Subscribe to %s failed: %s%s"
                    % (topic, _error_name(rc), self._lost())
                )
            codes = self._wait_ack(mid)
            if codes is None:
                raise RuntimeError(
                    "Subscribe to %s not acknowledged within "
                    "%s seconds%s" % (topic, self.timeout, self._lost())
                )
            failures = [code for code in codes if code.is_failure]
            if failures:
                raise RuntimeError("Subscribe to %s failed: %s" % (topic, failures[0]))
            with self._cond:
                self._qos[topic] = qos
                self._refused.pop(topic, None)
        except Exception:
            if created:
                # Keeps what register() took from the unclaimed queue, so a
                # retried Subscribe still gets persistent-session messages.
                self.unregister(topic, keep_messages=True)
            raise

    def unsubscribe(self, topic):
        """Unsubscribe and drop the filter's queue.

        Returns False if the broker did not send UNSUBACK within the timeout.
        """
        try:
            rc, mid = self.client.unsubscribe(topic)
            if rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(
                    "Unsubscribe from %s failed: %s%s"
                    % (topic, _error_name(rc), self._lost())
                )
            return self._wait_ack(mid) is not None
        finally:
            self.unregister(topic)

    def listen(self, topic, timeout, limit, decode=True, keyword="Listen"):
        """Return up to ``limit`` of the oldest messages on ``topic``, as
        Message objects with their payloads decoded as UTF-8, or as bytes
        without ``decode``.

        Waits until ``limit`` messages are queued, the connection is lost, or
        ``timeout`` elapses. With ``limit`` 0, waits the whole timeout and
        returns everything. Returns None if ``topic`` is not a registered
        filter. Fails if nothing is queued and the connection is lost, unless
        reconnecting is on, or the broker refused the subscription after a
        reconnect. ``keyword`` names the keyword in errors.
        """
        with self._cond:
            queue = self._filters.get(topic)
            if queue is None:
                return None

            def failed():
                return self._gone() or topic in self._refused

            if limit > 0:
                self._cond.wait_for(lambda: len(queue) >= limit or failed(), timeout)
            else:
                self._cond.wait_for(failed, timeout)
            self._warn_dropped(topic, queue)
            if not queue and topic in self._refused:
                raise RuntimeError(
                    "%s on %s failed: the broker refused the subscription "
                    "after a reconnect: %s" % (keyword, topic, self._refused[topic])
                )
            if not queue and failed():
                raise RuntimeError("%s on %s failed%s" % (keyword, topic, self._lost()))
            count = len(queue) if limit == 0 else min(limit, len(queue))
            # Decode before taking, so an undecodable message does not take
            # the good ones with it.
            messages = []
            for index in range(count):
                message = queue[index]
                if decode:
                    try:
                        message = dataclasses.replace(message, payload=_decode(message))
                    except UnicodeDecodeError as exc:
                        del queue[index]
                        raise RuntimeError(
                            "Dropped a message on %s that is not valid UTF-8: "
                            "%s. Use decode=${False} to get payloads as bytes."
                            % (topic, exc)
                        ) from None
                messages.append(message)
            for _ in range(count):
                queue.popleft()
            return messages

    def validate(self, topic, pattern, timeout):
        """Take messages from ``topic`` until one matches ``pattern``.

        Returns True on a match. Returns False if none arrives within
        ``timeout``, and raises AssertionError if the connection is lost
        first and reconnecting is off. Messages that do not match, including
        ones that are not valid UTF-8, are consumed.
        """
        deadline = time.monotonic() + timeout
        with self._cond:
            queue = self._filters[topic]
            while True:
                self._warn_dropped(topic, queue)
                while queue:
                    try:
                        payload = _decode(queue.popleft())
                    except UnicodeDecodeError:
                        continue
                    if re.match(pattern, payload):
                        return True
                if self._gone():
                    raise AssertionError(
                        "The expected payload didn't arrive "
                        "in the topic%s" % self._lost()
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)

    def clear(self, topic=None):
        """Drop the messages queued for ``topic``, or without a topic every
        queued message, including those that match no filter. Warns first
        about messages a full queue dropped. Returns how many were queued,
        or None if ``topic`` is not a registered filter.
        """
        with self._cond:
            if topic is None:
                named = list(self._filters.items()) + [(None, self._unclaimed)]
            elif topic in self._filters:
                named = [(topic, self._filters[topic])]
            else:
                return None
            count = 0
            for name, queue in named:
                self._warn_dropped(name, queue)
                count += len(queue)
                queue.clear()
            return count

    def register(self, topic):
        """Start queueing messages that match ``topic``.

        Matching messages already in the unclaimed queue move into the new
        queue, oldest first. Registering an existing filter keeps its queue.
        Returns True if the filter is new.
        """
        with self._cond:
            if topic in self._filters:
                return False
            self._warn_dropped(None, self._unclaimed)
            queue = self._filters[topic] = _Queue(self.max_queue)
            unclaimed = []
            for message in self._unclaimed:
                if mqtt.topic_matches_sub(topic, message.topic):
                    queue.put(message)
                else:
                    unclaimed.append(message)
            self._unclaimed.clear()
            self._unclaimed.extend(unclaimed)
            return True

    def unregister(self, topic, keep_messages=False):
        """Stop queueing messages for ``topic``.

        With ``keep_messages``, its queued messages go back to the front of
        the unclaimed queue.
        """
        with self._cond:
            queue = self._filters.pop(topic, None)
            self._qos.pop(topic, None)
            self._refused.pop(topic, None)
            if keep_messages and queue:
                # The returned messages are the oldest, so when the unclaimed
                # queue is full the oldest go, as with any other overflow.
                messages = list(queue) + list(self._unclaimed)
                overflow = max(0, len(messages) - self.max_queue)
                self._unclaimed.dropped += overflow
                self._unclaimed.clear()
                self._unclaimed.extend(messages[overflow:])

    # Internals.

    def _wait_ack(self, mid):
        """Wait for the SUBACK or UNSUBACK of ``mid``.

        Returns its reason codes, or None on timeout or a lost connection.
        """
        with self._cond:
            self._cond.wait_for(
                lambda: mid in self._acks or self._disconnect_reason is not None,
                self.timeout,
            )
            if mid not in self._acks:
                # A late ack for this mid must not answer a later operation
                # that reuses the mid.
                self._abandoned[mid] = time.monotonic()
            return self._acks.pop(mid, None)

    def _warn_dropped(self, topic, queue):
        """Warn once about messages a full queue dropped. Holds the lock."""
        if queue.dropped:
            where = "on %s" % topic if topic else "that matched no filter"
            logger.warn(
                "%d messages %s were dropped because more than %d "
                "were queued" % (queue.dropped, where, queue.maxlen)
            )
            queue.dropped = 0

    def _renewed(self, topics, codes):
        """Record the renewed subscriptions the broker refused. Holds the
        lock."""
        for topic, code in zip(topics, codes):
            if code.is_failure and topic in self._qos:
                del self._qos[topic]
                self._refused[topic] = code
        self._cond.notify_all()

    def _gone(self):
        """True if the connection is lost and will not come back by itself.
        With reconnecting on, a lost connection may come back, so waits
        continue until their timeout. Holds the lock."""
        return self._disconnect_reason is not None and not self.reconnect

    def _lost(self):
        reason = self._disconnect_reason
        if reason is None:
            return ""
        return " (connection lost: %s)" % reason

    def _stop(self):
        """Stop the network loop and wait up to the timeout for its thread.

        Does what paho's loop_stop() does, but with a bounded join. paho's own
        join has no timeout, so a DISCONNECT that cannot be written would block
        until the keepalive closes the socket. loop_stop() also fails if the
        thread clears its reference while ending by itself, for example after
        a refused CONNACK. Returns False if the thread is still running; it
        is a daemon thread and keeps its socket until the loop ends.
        """
        thread, self._thread = self._thread, None
        if thread is None:
            return True
        # The flag paho 2.1's loop_stop() sets; loop_forever() checks it.
        self.client._thread_terminate = True
        thread.join(self.timeout)
        return not thread.is_alive()

    # paho callbacks, called from the network thread.

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        with self._cond:
            # After a reconnect, the broker has no subscriptions unless it
            # kept the session. On the first CONNACK there are none yet.
            resubscribe = []
            if not reason_code.is_failure:
                self._disconnect_reason = None
                if self._connack is not None and not flags.session_present:
                    resubscribe = list(self._qos.items())
                # paho reads the flag when the connection drops. Set here, on
                # the network thread, it is on before any drop can be seen.
                if self.reconnect:
                    client._reconnect_on_failure = True
            self._connack = reason_code
            self._cond.notify_all()
        if resubscribe:
            # Outside the lock, like every call into paho. Nobody waits for
            # this SUBACK; _on_ack records the topics it refuses.
            topics = [topic for topic, _ in resubscribe]
            rc, mid = client.subscribe(resubscribe)
            if rc == mqtt.MQTT_ERR_SUCCESS:
                with self._cond:
                    codes = self._acks.pop(mid, None)
                    if codes is None:
                        self._renewals[mid] = (time.monotonic(), topics)
                    else:
                        self._renewed(topics, codes)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        with self._cond:
            self._disconnect_reason = reason_code
            self._cond.notify_all()

    def _on_ack(self, client, userdata, mid, reason_codes, properties):
        with self._cond:
            renewal = self._renewals.pop(mid, None)
            if (
                renewal is not None
                and time.monotonic() - renewal[0] < ABANDONED_ACK_SECONDS
            ):
                self._renewed(renewal[1], reason_codes)
                return
            abandoned = self._abandoned.pop(mid, None)
            if (
                abandoned is not None
                and time.monotonic() - abandoned < ABANDONED_ACK_SECONDS
            ):
                return
            self._acks[mid] = reason_codes
            self._cond.notify_all()

    def _on_message(self, client, userdata, message):
        # With overlapping subscriptions (a/# and a/1), MQTT 3.1.1 lets the
        # broker send either one copy or one copy per matching subscription;
        # Mosquitto sends one per subscription, back to back. The first copy
        # goes into every matching queue, and the identical copies that follow
        # it directly are dropped, so each filter gets the message once
        # either way.
        #
        # Each copy has the QoS of its subscription, min(published, granted),
        # and the copies can come in any order. The highest QoS among them is
        # min(published, highest granted), so min(that, a filter's QoS) is
        # what the broker delivers for that filter. A single copy for
        # overlapping subscriptions has the highest QoS too. Later copies
        # raise the QoS of entries that are still queued.
        key = (message.topic, message.payload, message.retain)
        with self._cond:
            copies, self._duplicates = self._duplicates, None
            if copies is not None and copies.key == key:
                copies.remaining -= 1
                if copies.remaining:
                    self._duplicates = copies
                if message.qos > copies.qos:
                    copies.qos = message.qos
                    self._requeue(copies)
                return
            matched = [
                (topic, queue)
                for topic, queue in self._filters.items()
                if mqtt.topic_matches_sub(topic, message.topic)
            ]
            received = Message(
                topic=message.topic,
                payload=bytes(message.payload),
                qos=message.qos,
                retain=bool(message.retain),
                properties=_properties(message.properties),
                timestamp=time.time(),
            )
            if not matched:
                self._unclaimed.put(received)
            entries = []
            for index, (topic, queue) in enumerate(matched):
                # Its own object and properties per queue, so changing one
                # message cannot change another filter's copy.
                queued = dataclasses.replace(
                    received,
                    qos=min(message.qos, self._qos.get(topic, message.qos)),
                    properties=(
                        copy.deepcopy(received.properties)
                        if index
                        else received.properties
                    ),
                )
                queue.put(queued)
                entries.append([topic, queue, queued])
            if len(matched) > 1:
                self._duplicates = _Copies(key, len(matched) - 1, message.qos, entries)
            self._cond.notify_all()

    def _requeue(self, copies):
        """Give the still-queued entries of ``copies`` the QoS their filter
        gets now that a copy with a higher QoS came. Holds the lock."""
        for entry in copies.entries:
            topic, queue, queued = entry
            qos = min(copies.qos, self._qos.get(topic, copies.qos))
            if qos != queued.qos and queue and queue[-1] is queued:
                entry[2] = queue[-1] = dataclasses.replace(queued, qos=qos)


def _decode(message):
    return message.payload.decode("utf-8")


def _properties(properties):
    """The MQTT 5 properties paho received, as a dict of the ones present.

    Like paho's Properties.json(), but CorrelationData stays bytes.
    """
    if properties is None:
        return {}
    present = {}
    for name in properties.names:
        name = name.replace(" ", "")
        if hasattr(properties, name):
            present[name] = getattr(properties, name)
    return present


def _error_name(rc):
    try:
        return mqtt.MQTTErrorCode(rc).name
    except ValueError:
        return str(rc)
