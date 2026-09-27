"""One MQTT connection: the paho client, its message queues and the state
that keywords wait on.

paho runs the network loop in a background thread (``loop_start()``), so the
callbacks below run on that thread while keywords run on Robot Framework's
main thread. Everything the two share is guarded by ``self._cond``, one
``threading.Condition`` per connection. Callbacks only update state and
notify; they never log, because Robot Framework ignores log messages from
other threads. Keyword-side methods never call into paho while holding
``self._cond``: paho takes its own locks around callbacks, so doing so could
deadlock.
"""

import collections
import logging
import re
import threading
import time

import paho.mqtt.client as mqtt
from robot.api import logger

# The most messages a queue holds. When a queue is full the oldest message is
# dropped, and the next Listen on that filter warns. The unclaimed queue holds
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


class _Queue(collections.deque):
    """A bounded message queue that counts the messages it dropped."""

    def __init__(self, messages=()):
        super().__init__(messages, maxlen=QUEUE_LIMIT)
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
    ):
        self.alias = alias
        self.host = host
        self.port = port
        self.client_id = client_id
        self.protocol = mqtt.MQTTv311
        self.keepalive = keepalive
        self.timeout = timeout
        self.address = "%s:%s" % (host, port)

        self._cond = threading.Condition()
        self._filters = {}
        self._unclaimed = _Queue()
        self._duplicates = None
        self._acks = {}
        self._abandoned = {}
        self._connack = None
        self._disconnect_reason = None
        self._thread = None

        # reconnect_on_failure must be False: with the background loop and
        # paho's default, a refused connection retries forever instead of
        # failing the keyword. paho raises ValueError here for an empty
        # client id with clean_session=False; that message is the keyword
        # failure.
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            clean_session=clean_session,
            protocol=self.protocol,
            reconnect_on_failure=False,
        )
        self.client.enable_logger(PAHO_LOGGER)
        # Bounds the TCP connect in client.connect(), so an unreachable host
        # fails within the same timeout as everything else.
        self.client.connect_timeout = timeout
        if username:
            self.client.username_pw_set(username, password)

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
            "client_id": self.client_id,
            "protocol": self.protocol.name,
            "keepalive": self.keepalive,
            "connected": self._connected,
        }

    def open(self):
        """Connect, start the network loop and wait for CONNACK."""
        try:
            self.client.connect(self.host, self.port, self.keepalive)
        except (OSError, UnicodeError) as exc:
            # OSError covers refused, unreachable and unresolvable hosts.
            # UnicodeError comes from the IDNA encoding of a malformed name
            # such as 172..0.0.1.
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
        connection was lost before or during the disconnect.
        """
        confirmed = True
        if self._connected:
            self.client.disconnect()
            with self._cond:
                confirmed = self._cond.wait_for(
                    lambda: self._disconnect_reason is not None, self.timeout
                )
        stopped = self._stop()
        reason = self._disconnect_reason
        if reason is not None and reason.is_failure:
            raise RuntimeError("The client disconnected unexpectedly: %s" % reason)
        return confirmed and stopped

    def publish(self, topic, payload, qos, retain):
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

    def listen(self, topic, timeout, limit):
        """Return up to ``limit`` of the oldest messages on ``topic``.

        Waits until ``limit`` messages are queued, the connection is lost, or
        ``timeout`` elapses. With ``limit`` 0, waits the whole timeout and
        returns everything. Returns None if ``topic`` is not a registered
        filter. Fails if the connection is lost and nothing is queued.
        """
        with self._cond:
            queue = self._filters.get(topic)
            if queue is None:
                return None

            def lost():
                return self._disconnect_reason is not None

            if limit > 0:
                self._cond.wait_for(lambda: len(queue) >= limit or lost(), timeout)
            else:
                self._cond.wait_for(lost, timeout)
            self._warn_dropped(topic, queue)
            if not queue and lost():
                raise RuntimeError("Listen on %s failed%s" % (topic, self._lost()))
            count = len(queue) if limit == 0 else min(limit, len(queue))
            # Decode before taking, so an undecodable message does not take
            # the good ones with it.
            messages = []
            for index in range(count):
                try:
                    messages.append(_decode(queue[index]))
                except UnicodeDecodeError as exc:
                    del queue[index]
                    raise RuntimeError(
                        "Dropped a message on %s that is not "
                        "valid UTF-8: %s" % (topic, exc)
                    ) from None
            for _ in range(count):
                queue.popleft()
            return messages

    def validate(self, topic, pattern, timeout):
        """Take messages from ``topic`` until one matches ``pattern``.

        Returns True on a match. Returns False if none arrives within
        ``timeout``, and raises AssertionError if the connection is lost
        first. Messages that do not match, including ones that are not valid
        UTF-8, are consumed.
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
                if self._disconnect_reason is not None:
                    raise AssertionError(
                        "The expected payload didn't arrive "
                        "in the topic%s" % self._lost()
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)

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
            queue = self._filters[topic] = _Queue()
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
            if keep_messages and queue:
                # The returned messages are the oldest, so when the unclaimed
                # queue is full the oldest go, as with any other overflow.
                messages = list(queue) + list(self._unclaimed)
                overflow = max(0, len(messages) - QUEUE_LIMIT)
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
                "were queued" % (queue.dropped, where, QUEUE_LIMIT)
            )
            queue.dropped = 0

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
            self._connack = reason_code
            self._cond.notify_all()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        with self._cond:
            self._disconnect_reason = reason_code
            self._cond.notify_all()

    def _on_ack(self, client, userdata, mid, reason_codes, properties):
        with self._cond:
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
        key = (message.topic, message.payload, message.retain)
        with self._cond:
            duplicates, self._duplicates = self._duplicates, None
            if duplicates is not None and duplicates[0] == key:
                if duplicates[1] > 1:
                    self._duplicates = (key, duplicates[1] - 1)
                return
            matched = [
                queue
                for topic, queue in self._filters.items()
                if mqtt.topic_matches_sub(topic, message.topic)
            ]
            for queue in matched:
                queue.put(message)
            if not matched:
                self._unclaimed.put(message)
            if len(matched) > 1:
                self._duplicates = (key, len(matched) - 1)
            self._cond.notify_all()


def _decode(message):
    return message.payload.decode("utf-8")


def _error_name(rc):
    try:
        return mqtt.MQTTErrorCode(rc).name
    except ValueError:
        return str(rc)
