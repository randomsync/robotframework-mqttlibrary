"""One MQTT connection: the paho client, its message queues and the state
that keywords wait on.

paho runs the network loop in a background thread (``loop_start()``), so the
callbacks below run on that thread while keywords run on Robot Framework's
main thread. Everything the two share is guarded by ``self._cond``, one
``threading.Condition`` per connection. Callbacks only update state and
notify; they never log, because Robot Framework ignores log messages from
other threads.
"""

import collections
import re
import threading
import time

import paho.mqtt.client as mqtt

# Messages that match no registered filter wait here until a Subscribe claims
# them. This keeps persistent-session messages that the broker delivers
# between CONNACK and SUBSCRIBE. The bound stops a connection that nobody
# reads from growing without limit; the oldest messages are dropped first.
UNCLAIMED_LIMIT = 10000


def _decode(message):
    return message.payload.decode('utf-8')


class _Connection(object):

    def __init__(self, alias, host, port, client_id, clean_session,
                 keepalive, timeout, username=None, password=None):
        self.alias = alias
        self.host = host
        self.port = port
        self.keepalive = keepalive
        self.timeout = timeout
        self.address = '%s:%s' % (host, port)

        self._cond = threading.Condition()
        self._filters = {}
        self._unclaimed = collections.deque(maxlen=UNCLAIMED_LIMIT)
        self._acks = {}
        self._connack = None
        self._disconnect_reason = None
        self._connected = False
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
            reconnect_on_failure=False,
        )
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

    # Keyword-side operations, called from Robot Framework's thread.

    def open(self):
        """Connect, start the network loop and wait for CONNACK."""
        try:
            self.client.connect(self.host, self.port, self.keepalive)
        except (OSError, UnicodeError) as exc:
            # OSError covers refused, unreachable and unresolvable hosts.
            # UnicodeError comes from the IDNA encoding of a malformed name
            # such as 172..0.0.1.
            raise RuntimeError('Connection to %s failed: %s'
                               % (self.address, exc)) from None
        self.client.loop_start()
        self._thread = self.client._thread

        with self._cond:
            self._cond.wait_for(
                lambda: (self._connack is not None
                         or self._disconnect_reason is not None),
                self.timeout)
            connack = self._connack
            reason = self._disconnect_reason
        if connack is not None and not connack.is_failure and reason is None:
            return

        if connack is not None and connack.is_failure:
            reason = connack
        elif reason is None:
            reason = 'no CONNACK within %s seconds' % self.timeout
        # Closes the socket if it is still open, for example after a timeout.
        self.client.disconnect()
        self._stop()
        raise RuntimeError('Connection to %s failed: %s'
                           % (self.address, reason))

    def close(self):
        """Disconnect and stop the network loop.

        Returns False if the broker did not confirm the disconnect within the
        timeout. Raises if the connection was lost before or during the
        disconnect.
        """
        with self._cond:
            connected = self._connected
        confirmed = True
        if connected:
            self.client.disconnect()
            with self._cond:
                confirmed = self._cond.wait_for(
                    lambda: self._disconnect_reason is not None,
                    self.timeout)
        self._stop()
        reason = self._disconnect_reason
        if reason is not None and reason.is_failure:
            raise RuntimeError('The client disconnected unexpectedly: %s'
                               % reason)
        return confirmed

    def publish(self, topic, payload, qos, retain):
        info = self.client.publish(topic, payload, qos, retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError('Publish to %s failed: %s%s'
                               % (topic, _error_name(info.rc), self._lost()))
        info.wait_for_publish(self.timeout)
        if not info.is_published():
            raise RuntimeError('Publish to %s not acknowledged within %s '
                               'seconds%s' % (topic, self.timeout,
                                              self._lost()))

    def subscribe(self, topic, qos):
        """Register ``topic`` as a filter, subscribe and wait for SUBACK."""
        created = self.register(topic)
        try:
            rc, mid = self.client.subscribe(topic, qos)
            if rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError('Subscribe to %s failed: %s%s'
                                   % (topic, _error_name(rc), self._lost()))
            codes = self._wait_ack(mid)
            if codes is None:
                raise RuntimeError('Subscribe to %s not acknowledged within '
                                   '%s seconds%s'
                                   % (topic, self.timeout, self._lost()))
            failures = [code for code in codes if code.is_failure]
            if failures:
                raise RuntimeError('Subscribe to %s failed: %s'
                                   % (topic, failures[0]))
        except Exception:
            if created:
                self.unregister(topic)
            raise

    def unsubscribe(self, topic):
        """Unsubscribe and drop the filter's queue.

        Returns False if the broker did not send UNSUBACK within the timeout.
        """
        try:
            rc, mid = self.client.unsubscribe(topic)
            if rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError('Unsubscribe from %s failed: %s%s'
                                   % (topic, _error_name(rc), self._lost()))
            return self._wait_ack(mid) is not None
        finally:
            self.unregister(topic)

    def listen(self, topic, timeout, limit):
        """Return up to ``limit`` of the oldest messages on ``topic``.

        Waits until ``limit`` messages are queued or ``timeout`` elapses. With
        ``limit`` 0, waits the whole timeout and returns everything. Returns
        None if ``topic`` is not a registered filter.
        """
        with self._cond:
            queue = self._filters.get(topic)
            if queue is None:
                return None
            if limit > 0:
                self._cond.wait_for(lambda: len(queue) >= limit, timeout)
            else:
                self._cond.wait_for(lambda: False, timeout)
            count = len(queue) if limit == 0 else min(limit, len(queue))
            return [_decode(queue.popleft()) for _ in range(count)]

    def validate(self, topic, pattern, timeout):
        """Take messages from ``topic`` until one matches ``pattern``.

        Returns True on a match, False if none arrives within ``timeout``.
        Messages that do not match are consumed.
        """
        deadline = time.monotonic() + timeout
        with self._cond:
            queue = self._filters[topic]
            while True:
                while queue:
                    if re.match(pattern, _decode(queue.popleft())):
                        return True
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
            queue = self._filters[topic] = collections.deque()
            unclaimed = collections.deque()
            for message in self._unclaimed:
                if mqtt.topic_matches_sub(topic, message.topic):
                    queue.append(message)
                else:
                    unclaimed.append(message)
            self._unclaimed.clear()
            self._unclaimed.extend(unclaimed)
            return True

    def unregister(self, topic):
        with self._cond:
            self._filters.pop(topic, None)

    # Internals.

    def _wait_ack(self, mid):
        """Wait for the SUBACK or UNSUBACK of ``mid``.

        Returns its reason codes, or None on timeout or a lost connection.
        """
        with self._cond:
            self._cond.wait_for(
                lambda: (mid in self._acks
                         or self._disconnect_reason is not None),
                self.timeout)
            return self._acks.pop(mid, None)

    def _lost(self):
        reason = self._disconnect_reason
        if reason is None:
            return ''
        return ' (connection lost: %s)' % reason

    def _stop(self):
        """Stop the network loop and wait for its thread to end."""
        self.client.loop_stop()
        # paho clears its own thread reference when the loop ends by itself,
        # for example after a refused CONNACK, so join the one kept at
        # loop_start() to be sure it has finished.
        if self._thread is not None:
            self._thread.join(self.timeout)
            self._thread = None

    # paho callbacks, called from the network thread.

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        with self._cond:
            self._connack = reason_code
            self._connected = not reason_code.is_failure
            self._cond.notify_all()

    def _on_disconnect(self, client, userdata, flags, reason_code,
                       properties):
        with self._cond:
            self._connected = False
            self._disconnect_reason = reason_code
            self._cond.notify_all()

    def _on_ack(self, client, userdata, mid, reason_codes, properties):
        with self._cond:
            self._acks[mid] = reason_codes
            self._cond.notify_all()

    def _on_message(self, client, userdata, message):
        with self._cond:
            matched = False
            for topic, queue in self._filters.items():
                if mqtt.topic_matches_sub(topic, message.topic):
                    queue.append(message)
                    matched = True
            if not matched:
                self._unclaimed.append(message)
            self._cond.notify_all()


def _error_name(rc):
    try:
        return mqtt.MQTTErrorCode(rc).name
    except ValueError:
        return str(rc)
