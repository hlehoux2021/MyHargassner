# Technical Implementation Strategy: Bug #1 - IGW Reconnection Handling

**Date:** 2025-10-14
**Bug Reference:** [GitHub Issue #1](https://github.com/hlehoux2021/MyHargassner/issues/1)
**Related Documents:**
- [bug-0001-description.md](../../bug-0001-description.md)
- [bug-001-proposal.md](../../bug-001-proposal.md)

---

## Executive Summary

**Objective:** Implement system-wide restart on IGW reconnection to handle connection lifecycle properly.

**Solution:** System-wide restart orchestrated by main.py, triggered by TelnetProxy detecting session end via three mechanisms.

**Implementation Phases:** 5 independent phases with 15 implementation steps

**Estimated Effort:** 3-4 days for implementation + 2 days for testing

---

## Implementation Overview

### Files to Modify

```
myhargassner/
├── main.py                    # Phase 4: Add restart orchestration
├── telnetproxy.py            # Phase 2: Exit on disconnect + restart triggers
├── gateway.py                # Phase 1: Add shutdown support (simplified)
├── boiler.py                 # Phase 1: Add shutdown support
├── mqtt_informer.py          # Phase 1: Add shutdown support
├── mqtt_actuator.py          # Phase 1: Add shutdown support
└── analyser.py               # Phase 3: Detect $igw clear (no change needed)
```

### No New Files Created

All changes are modifications to existing files.

---

## Phase 1: Add Shutdown Support to All Components

### Objective
Enable all threaded components to respond to shutdown requests from main.py.

### Components Requiring Shutdown Support

1. ✅ GatewayListenerSender
2. ✅ BoilerListenerSender
3. ✅ MqttInformer
4. ✅ MqttActuator
5. ✅ TelnetProxy (already partially supported)

---

### Step 1.1: Add Shutdown to GatewayListenerSender

**File:** `myhargassner/gateway.py`

**Changes:**

```python
# Add to GatewayListenerSender class
class GatewayListenerSender(ListenerSender):
    """This class extends ListenerSender class to implement the gateway listener."""

    udp_port: Annotated[int, annotated_types.Gt(0)]
    _shutdown_requested: bool = False  # ← ADD THIS

    def __init__(self, appconfig: AppConfig, communicator: PubSub, delta: int = 0):
        super().__init__(appconfig, communicator, appconfig.gw_iface(), appconfig.bl_iface())
        self.udp_port = self._appconfig.udp_port()
        self.delta = delta
        self._shutdown_requested = False  # ← ADD THIS

    def request_shutdown(self):  # ← ADD THIS METHOD
        """Request graceful shutdown of this component."""
        logging.info("GatewayListener: Shutdown requested by main")
        self._shutdown_requested = True

    def loop(self) -> None:  # ← MODIFY EXISTING METHOD
        """Main loop with shutdown check."""
        data: bytes
        addr: tuple

        if not self.bound:
            logging.error("Cannot start loop - socket not bound yet")
            return

        while not self._shutdown_requested:  # ← CHANGE: Add shutdown check
            if self._msq:
                logging.debug('ChannelQueue size: %d', self._msq.qsize())
            logging.debug('waiting data')
            data = b''
            addr = ('', 0)

            try:
                data, addr = self.listen_manager.receive()
                if data:
                    logging.debug('Received buffer of %d bytes from %s:%d',
                                len(data), addr[0], addr[1])
                    logging.debug('Data: %s', data)

                    if not self.resender_bound:
                        self.handle_first(data, addr)
                    self.handle_data(data, addr)
                    self.send(data)

            except SocketTimeoutError:
                logging.debug('No data received within timeout period')
                continue
            except HargSocketError as e:
                logging.error("Socket error in loop: %s", e)
                break

        logging.info("GatewayListener: Exiting loop")

    # NOTE: handle_data() is SIMPLIFIED - no restart logic
    def handle_data(self, data: bytes, addr: tuple):
        """Handle UDP data - simplified, no restart logic."""
        _str: str = ''
        _subpart: str = ''
        _str_parts: list[str] = []

        logging.debug('handle_data::received %d bytes from %s:%d ==>%s',
                      len(data), addr[0], addr[1], data.decode())

        _str = data.decode()
        _str_parts = _str.split('\r\n')
        for part in _str_parts:
            if part.startswith('HargaWebApp'):
                _subpart = part[13]
                logging.info('HargaWebApp££%s', _subpart)
                # Always publish discovery - TelnetProxy will detect duplicates
                self._com.publish(self._channel, f"HargaWebApp££{_subpart}")

            if part.startswith('SN:'):
                _subpart = part[3:]
                logging.info('SN: [%s]', _subpart)
                self._com.publish(self._channel, f"SN££{_subpart}")
```

**Testing:**
```bash
# Verify shutdown works
python -c "from myhargassner.gateway import GatewayListenerSender; print('Import OK')"
```

---

### Step 1.2: Add Shutdown to BoilerListenerSender

**File:** `myhargassner/boiler.py`

**Changes:**

```python
# Add to BoilerListenerSender class
class BoilerListenerSender(ListenerSender):
    """This class implements the boiler proxy."""

    _shutdown_requested: bool = False  # ← ADD THIS

    def __init__(self, appconfig: AppConfig, communicator: PubSub, delta: int = 0):
        super().__init__(appconfig, communicator, appconfig.bl_iface(), appconfig.gw_iface())
        self.delta = delta
        self._shutdown_requested = False  # ← ADD THIS

    def request_shutdown(self):  # ← ADD THIS METHOD
        """Request graceful shutdown of this component."""
        logging.info("BoilerListener: Shutdown requested by main")
        self._shutdown_requested = True

    # NOTE: discover() should also check shutdown flag
    def discover(self):
        """Discover the gateway ip address and port."""
        logging.info('BoilerListenerSender discovering gateway')
        self._msq = self._com.subscribe(self._channel, self.name())

        while self.gw_port == 0 and not self._shutdown_requested:  # ← ADD shutdown check
            self.handle()

        if self._shutdown_requested:
            logging.info('BoilerListenerSender: Shutdown during discovery')
            return

        logging.info('BoilerListenerSender received gateway information %s:%d',
                    self.gw_addr, self.gw_port)
        logging.debug('BoilerListenerSender unsubscribe from channel %s', self._channel)
        self._com.unsubscribe(self._channel, self._msq)
        self._msq = None

    # Inherit loop() from ListenerSender, but ensure it checks _shutdown_requested
    # The parent class loop() needs to be updated (see Step 1.6)
```

**Note:** BoilerListenerSender inherits `loop()` from `ListenerSender`. We need to ensure the parent class checks `_shutdown_requested` flag (Step 1.6).

---

### Step 1.3: Add Shutdown to MqttInformer

**File:** `myhargassner/mqtt_informer.py`

**Changes:**

```python
# Find the MqttInformer class and add shutdown support
class MqttInformer(ChanelReceiver, MqttBase, Thread):
    """This class implements the MqttInformer."""

    _shutdown_requested: bool = False  # ← ADD THIS

    def __init__(self, appconfig: AppConfig, communicator: PubSub):
        Thread.__init__(self, name='MqttInformer')
        ChanelReceiver.__init__(self, communicator)
        MqttBase.__init__(self, appconfig)
        self._shutdown_requested = False  # ← ADD THIS

    def request_shutdown(self):  # ← ADD THIS METHOD
        """Request graceful shutdown of this component."""
        logging.info("MqttInformer: Shutdown requested by main")
        self._shutdown_requested = True

    def start(self) -> None:  # ← MODIFY EXISTING METHOD
        """This method runs the MqttInformer, waiting for message on _info_queue."""
        _stage: str = ''

        self._msq = self._com.subscribe(self._channel, self.name())

        while not self._shutdown_requested:  # ← CHANGE: Add shutdown check
            try:
                logging.debug('MqttInformer: waiting for messages')
                iterator = self._msq.listen(timeout=3)
                try:
                    _message = next(iterator)
                except StopIteration:
                    logging.debug('StopIteration: No message received, continuing...')
                    continue

                if not _message:
                    logging.debug('MqttInfomer no message received')
                    continue

                msg = _message['data']
                logging.debug('MqttInformer: received %s', msg)
                _str_parts = msg.split('££')

                if not _str_parts or len(_str_parts) < 2:
                    logging.warning('MqttInformer: invalid message format %s', msg)
                    continue

                if _stage == 'device_info_ok':
                    # ... existing processing ...
                    pass

                # ... rest of existing logic ...

            except Exception as e:
                logging.error('MqttInformer error: %s', str(e))
                if self._shutdown_requested:
                    break
                continue

        logging.info("MqttInformer: Exiting")
```

---

### Step 1.4: Add Shutdown to MqttActuator

**File:** `myhargassner/mqtt_actuator.py`

**Changes:**

```python
# Add to MqttActuator class
class MqttActuator(ChanelReceiver, MqttBase):
    """MqttActuator is a class for controlling devices via MQTT."""

    _shutdown_requested: bool = False  # ← ADD THIS
    _main_client: Optional[Client] = None
    # ... existing attributes ...

    def __init__(self, appconfig: AppConfig, communicator: PubSub,
                 device_info: DeviceInfo, src_iface: bytes,
                 lock: threading.Lock) -> None:
        logging.debug("MqttActuator instantiated")
        ChanelReceiver.__init__(self, communicator)
        MqttBase.__init__(self, appconfig)
        self.src_iface = src_iface
        self._device_info = device_info
        self._service_lock = lock
        self._client = TelnetClient(self.src_iface, b'',
                                   buffer_size=self._appconfig.buff_size(), port=4000)
        self._shutdown_requested = False  # ← ADD THIS

    def request_shutdown(self):  # ← ADD THIS METHOD
        """Request graceful shutdown of this component."""
        logging.info("MqttActuator: Shutdown requested")
        self._shutdown_requested = True
        # Disconnect MQTT client
        if self._main_client:
            try:
                self._main_client.disconnect()
            except Exception as e:
                logging.warning("Error disconnecting MQTT client: %s", e)

    def service(self) -> None:  # ← MODIFY EXISTING METHOD
        """Start and run the MQTT actuator service."""
        logging.debug("MqttActuator.service called")

        # Discover the boiler configuration
        self.discover()

        if self._shutdown_requested:
            logging.info("MqttActuator: Shutdown during discovery")
            return

        # Connect to the boiler
        self._get_client().connect()

        # Create all subscribers first
        self.create_subscribers()

        try:
            logging.info("Starting MQTT loop - waiting for messages...")
            logging.debug("self._main_client is: %r", self._main_client)

            if not self._main_client:
                raise RuntimeError("No MQTT client available")

            # Use loop_start() instead of loop_forever() for better shutdown control
            self._main_client.loop_start()

            # Monitor for shutdown request
            while not self._shutdown_requested:
                time.sleep(1)

            logging.info("MqttActuator: Shutdown requested, stopping MQTT loop")
            self._main_client.loop_stop()

        except KeyboardInterrupt:
            logging.info("Shutting down MQTT Actuator...")
            if self._main_client:
                self._main_client.disconnect()
            for select in self._selects.values():
                select.mqtt_client.disconnect()
        except Exception as e:
            logging.critical("Error in MQTT loop: %s", str(e))
            if self._main_client:
                self._main_client.disconnect()
            for select in self._selects.values():
                select.mqtt_client.disconnect()
            logging.critical("MQTT Actuator encountered a critical error and terminated.")
            raise
```

---

### Step 1.5: Update TelnetProxy Shutdown Support

**File:** `myhargassner/telnetproxy.py`

**Changes:**

```python
# TelnetProxy already has some shutdown logic, enhance it
class TelnetProxy(ChanelReceiver, MqttBase):
    """This class implements the TelnetProxy."""

    _shutdown_requested: bool = False  # ← ADD THIS (if not already present)
    _restart_requested: bool = False   # ← ADD THIS

    def __init__(self, appconfig: AppConfig, communicator: PubSub, port, lock: Lock):
        ChanelReceiver.__init__(self, communicator)
        MqttBase.__init__(self, appconfig)
        self.src_iface = self._appconfig.gw_iface()
        self.dst_iface = self._appconfig.bl_iface()
        self.port = port
        self._analyser = Analyser(communicator)
        self._service1 = TelnetService(self.src_iface, self._appconfig.buff_size())
        self._service2 = TelnetService(self.src_iface, self._appconfig.buff_size())
        self._service_lock = lock
        self._active_sockets = set()
        self._shutdown_requested = False  # ← ADD THIS
        self._restart_requested = False   # ← ADD THIS

    def request_shutdown(self):  # ← ADD THIS METHOD
        """Request graceful shutdown of this component."""
        logging.info("TelnetProxy: Shutdown requested by main")
        self._shutdown_requested = True

    # Note: More changes in Phase 2
```

---

### Step 1.6: Update ListenerSender Base Class Loop

**File:** `myhargassner/core.py`

**Changes:**

```python
# Update the loop() method in ListenerSender class
class ListenerSender(ChanelReceiver, ABC):
    """This class extends ChanelReceiver class with a socket to listen and resend data."""

    # ... existing attributes ...
    _shutdown_requested: bool = False  # ← ADD THIS (if not inherited)

    def loop(self) -> None:  # ← MODIFY EXISTING METHOD
        """This method is the main loop of the class."""
        data: bytes
        addr: tuple

        if not self.bound:
            logging.error("Cannot start loop - socket not bound yet")
            return

        while not self._shutdown_requested:  # ← CHANGE: Add shutdown check
            if self._msq:
                logging.debug('ChannelQueue size: %d', self._msq.qsize())
            logging.debug('waiting data')
            data = b''
            addr = ('', 0)

            try:
                data, addr = self.listen_manager.receive()
                if data:
                    logging.debug('Received buffer of %d bytes from %s:%d',
                                len(data), addr[0], addr[1])
                    logging.debug('Data: %s', data)

                    if not self.resender_bound:
                        self.handle_first(data, addr)
                    self.handle_data(data, addr)
                    self.send(data)

            except SocketTimeoutError:
                logging.debug('No data received within timeout period')
                continue
            except HargSocketError as e:
                logging.error("Socket error in loop: %s", e)
                break

        logging.info("%s: Exiting loop", self.name())
```

---

## Phase 2: Modify TelnetProxy to Exit on Disconnect

### Objective
Make TelnetProxy exit cleanly when IGW disconnects, and add restart request mechanism.

---

### Step 2.1: Add Restart Request Method

**File:** `myhargassner/telnetproxy.py`

**Changes:**

```python
class TelnetProxy(ChanelReceiver, MqttBase):
    """This class implements the TelnetProxy."""

    # Add new attributes
    _session_end_requested: bool = False
    _restart_requested: bool = False
    _discovery_complete: bool = False

    def __init__(self, appconfig: AppConfig, communicator: PubSub, port, lock: Lock):
        # ... existing init ...
        self._session_end_requested = False
        self._restart_requested = False
        self._discovery_complete = False

    def _request_restart(self, reason: str):
        """Request restart only once per session."""
        if not self._restart_requested:
            logging.info('TelnetProxy requesting restart: %s', reason)
            self._com.publish('system', 'RESTART_REQUESTED')
            self._restart_requested = True
        else:
            logging.debug('Restart already requested, ignoring: %s', reason)
```

---

### Step 2.2: Modify discover() to Stay Subscribed

**File:** `myhargassner/telnetproxy.py`

**Changes:**

```python
def discover(self):
    """Wait for the boiler address and port to be discovered."""
    self._msq = self._com.subscribe(self._channel, self.name())

    while (self.bl_port == 0) or (self.bl_addr == b''):
        logging.debug('waiting for the discovery of the boiler address and port')
        self.handle()

    logging.info('TelnetProxy discovered boiler %s:%d', self.bl_addr, self.bl_port)
    self._discovery_complete = True

    # CRITICAL CHANGE: Don't unsubscribe!
    # Stay subscribed to detect duplicate discovery (Trigger 3)
    logging.info('TelnetProxy: Discovery complete, monitoring for reconnection signals')
    # OLD CODE (remove these lines):
    # logging.info('TelnetProxy unsubscribe from channel %s', self._channel)
    # self._com.unsubscribe(self._channel, self._msq)
    # self._msq = None

    # redistribute BL info to the mq Queue for further use
    self._analyser.push('BL_ADDR', str(self.bl_addr, 'ascii'))
    self._analyser.push('BL_PORT', str(self.bl_port))
```

---

### Step 2.3: Add Reconnection Monitoring

**File:** `myhargassner/telnetproxy.py`

**Changes:**

```python
def monitor_for_reconnection(self) -> bool:
    """Check for reconnection signals (non-blocking).

    Returns:
        bool: True if reconnection detected, False otherwise
    """
    if not self._msq or not self._discovery_complete:
        return False

    try:
        # Non-blocking check for new discovery messages
        iterator = self._msq.listen(timeout=0.01)  # Very short timeout
        message = next(iterator)

        if message:
            msg = message['data']

            # Check for new "HargaWebApp" broadcast during active session
            if 'HargaWebApp' in msg:
                logging.warning('Received new HargaWebApp during active session')
                self._request_restart('new_HargaWebApp_during_session')
                return True

    except StopIteration:
        pass  # No message, continue

    return False
```

---

### Step 2.4: Modify loop() to Handle Disconnect and Monitor Reconnection

**File:** `myhargassner/telnetproxy.py`

**Changes:**

```python
def loop(self) -> None:
    """Main loop waiting for requests and replies, handling all active sockets."""
    _sock: socket.socket
    _data: bytes
    _addr: tuple
    read_sockets: list[socket.socket] = []
    write_sockets: list[socket.socket] = []
    error_sockets: list[socket.socket] = []
    _state: str = ''
    _buffer: bytes = b''
    _mode: str = ''
    _caller: int = 0

    # Initialize active sockets
    service1_socket = self._service1.socket()
    if service1_socket is not None:
        self._active_sockets.add(service1_socket)
        logging.debug('Added service1 socket to active set')
    service2_socket = self._service2.socket()
    if service2_socket is not None:
        self._active_sockets.add(service2_socket)
        logging.debug('Added service2 socket to active set')
    if self._client is not None:
        client_socket = self._client.socket()
        if client_socket is not None:
            self._active_sockets.add(client_socket)
            logging.debug('Added client socket to active set')

    logging.debug('Active sockets: %d', len(self._active_sockets))

    while self._active_sockets and not self._shutdown_requested:
        # Periodically check for reconnection signals (Trigger 3)
        if self.monitor_for_reconnection():
            logging.info('Reconnection detected, closing connections and exiting')
            if self._client:
                self._client.close()
            return

        if self._msq:
            logging.debug('TelnetProxy ChannelQueue size: %d', self._msq.qsize())

        try:
            read_sockets, write_sockets, error_sockets = select.select(
                list(self._active_sockets), [], [], 1.0
            )
        except select.error as err:
            logging.error("Select error: %s", str(err))
            continue
        except Exception as err:
            logging.error("Unexpected error in select: %s", str(err))
            continue

        for _sock in read_sockets:
            if _sock == self._service1.socket():
                # Only process service1 if lock is not held
                if self._service_lock.locked():
                    logging.debug('Service1 socket is paused/locked, skipping processing')
                    time.sleep(1)
                    continue

                try:
                    _data = self._service1.recv()
                    if not _data:
                        # TRIGGER 2: IGW closed connection
                        logging.info('service1: IGW closed connection')
                        self._request_restart('connection_closed')
                        # Close boiler connection
                        if self._client:
                            self._client.close()
                        # Exit loop
                        return

                    logging.debug('service1 received request %d bytes ==>%s',
                                len(_data), repr(_data))
                    _caller = 1

                    # Parse request
                    _state = self._analyser.parse_request(_data)
                    logging.debug('_state-->%s', _state)

                    # TRIGGER 1: Check for $igw clear
                    if _state == '$igw clear':
                        logging.info('$igw clear detected, will close after response')
                        self._session_end_requested = True

                    # Forward request to boiler
                    logging.debug('service1 resending %d bytes to %s:%d',
                                len(_data), repr(self.bl_addr), self.port)
                    try:
                        self._client.send(_data)
                    except Exception as e:
                        logging.error("Error sending request to boiler: %s", str(e))

                except socket.error as err:
                    # TRIGGER 2: Socket error
                    logging.error("Socket error in service1 recv: %s", str(err))
                    self._request_restart('socket_error')
                    sock = self._service1.socket()
                    if sock is not None:
                        try:
                            sock.close()
                            self._active_sockets.discard(sock)
                        except Exception as close_err:
                            logging.error("Error closing service1 socket: %s", str(close_err))
                    # Close boiler and exit
                    if self._client:
                        self._client.close()
                    return

                except Exception as err:
                    logging.critical("Unexpected error in service1 recv: %s", type(err))
                    self._request_restart('unexpected_error')
                    sock = self._service1.socket()
                    if sock is not None:
                        try:
                            sock.close()
                            self._active_sockets.discard(sock)
                        except Exception:
                            pass
                    # Close boiler and exit
                    if self._client:
                        self._client.close()
                    return

            if _sock == self._service2.socket():
                # ... existing service2 handling (no changes needed) ...
                try:
                    _data = self._service2.recv()
                    if not _data:
                        logging.warning('service2 received empty request')
                        continue
                    logging.debug('service2 received request %d bytes ==>%s',
                                len(_data), repr(_data))
                    _caller = 2
                    logging.debug('service2 resending %d bytes to %s:%d',
                                len(_data), repr(self.bl_addr), self.port)
                    self._client.send(_data)
                except socket.error as err:
                    logging.error("Socket error in service2 recv: %s", str(err))
                    sock = self._service2.socket()
                    if sock is not None:
                        try:
                            sock.close()
                            self._active_sockets.discard(sock)
                        except Exception as close_err:
                            logging.error("Error closing service2 socket: %s", str(close_err))
                    raise socket.error(f"service2: {str(err)}")
                except Exception as err:
                    logging.critical("Unexpected error in service2 recv: %s", type(err))
                    if self._service2.socket() is not None:
                        try:
                            sock = self._service2.socket()
                            if sock is not None:
                                sock.close()
                                self._active_sockets.discard(sock)
                        except Exception as close_err:
                            logging.error("Error closing service2 socket: %s", str(close_err))
                    raise socket.error(f"service2: {str(err)}")

            if _sock == self._client.socket():
                # Receive response from boiler
                try:
                    _data = self._client.recv()
                except Exception as err:
                    logging.critical("Exception on client telnet socket: %s", type(err))
                    if self._client is not None:
                        self._client.close()
                    raise

                if not _data:
                    logging.warning('client received empty response')
                    if self._client is not None:
                        self._client.close()
                    raise socket.error("Empty response from client")

                if not _data.startswith(b'pm'):
                    logging.debug('telnet received response %d bytes ==>%s',
                                len(_data), repr(_data))
                else:
                    logging.debug('telnet received pm response %d bytes', len(_data))

                try:
                    # Send data back to the caller
                    _sent = 0
                    logging.debug('telnet sending response to caller %d', _caller)
                    if _data.startswith(b'pm'):
                        if self._service1.socket() is not None:
                            logging.debug('telnet sending pm response to service1')
                            _sent = self._service1.send(_data)
                        else:
                            logging.debug('Received a pm response but no service1 socket')
                    else:
                        if _caller == 1:
                            _sent = self._service1.send(_data)
                        elif _caller == 2:
                            logging.debug('telnet sending response to service2')
                            _sent = self._service2.send(_data)
                        else:
                            logging.warning('Received response with unregistered caller %d',
                                          _caller)
                    logging.debug('telnet sent back response to client')
                except Exception as err:
                    logging.critical("Exception: %s", type(err))
                    raise

                # TRIGGER 1: Check if session should end after $igw clear
                if self._session_end_requested and _state == '$igw clear':
                    if b'$ack' in _data:
                        logging.info('$igw clear complete')
                        self._request_restart('igw_clear_command')
                        # Close boiler connection
                        if self._client:
                            self._client.close()
                        # Exit loop
                        return

                # Analyse response
                _login_done: bool = False
                _buffer, _mode, _state, _login_done = self._analyser.analyse_data_buffer(
                    _data, _buffer, _mode, _state
                )
                if _login_done:
                    logging.info('login done, call get_boiler_config')
                    self.get_boiler_config()

    logging.info("TelnetProxy loop exiting cleanly")
```

---

### Step 2.5: Remove Restart Logic from service()

**File:** `myhargassner/telnetproxy.py`

**Changes:**

```python
def service(self) -> None:
    """Main service - run once per IGW connection session."""
    logging.debug('TelnetProxy::service starting')

    # Initial setup
    if not self.restart_client():
        raise RuntimeError("Failed initial client connection")

    # Run the main loop for this connection session
    logging.info('TelnetProxy: Running main loop')
    self.loop()

    # Clean exit (no restart attempts)
    logging.info('TelnetProxy: Connection ended, exiting service')
    # Note: No while True loop, no restart_service1/2 calls
    # Let main.py handle restart
```

**Remove these methods (or mark as deprecated):**
- `restart_service1()`
- `restart_service2()`

These are no longer needed since we don't restart internally.

---

### Step 2.6: Update ThreadedTelnetProxy to Handle MqttActuator Cleanup

**File:** `myhargassner/telnetproxy.py`

**Changes:**

```python
class ThreadedTelnetProxy(Thread):
    """This class implements a Thread to run the TelnetProxy."""

    # ... existing attributes ...

    def request_shutdown(self):
        """Request shutdown of TelnetProxy and MqttActuator."""
        logging.info("ThreadedTelnetProxy: Shutdown requested")
        self.tp.request_shutdown()
        # Also shutdown MqttActuator if running
        if self._ma:
            self._ma.request_shutdown()

    def run(self) -> None:
        """Run the TelnetProxy in a separate thread."""
        _ts: Thread | None = None
        logging.info('telnet proxy started: %s , %s', self.tp.src_iface, self.tp.dst_iface)

        try:
            # Discover the boiler
            self.tp.discover()

            # Create and start MqttActuator
            if not self._ma:
                logging.debug("Creating ThreadedMqttActuator")
                self.tp.init_device_info(self.tp.bl_addr.decode('ascii'))
                self._ma = ThreadedMqttActuator(
                    self._appconfig, self._com,
                    self.tp.device_info(),
                    self._src_iface,
                    self._service_lock
                )
                self._ma.start()

            # Bind, listen, accept
            self.tp.bind1()
            self.tp.bind2()
            self.tp.listen1()
            self.tp.listen2()

            # Create separate threads for accepting connections
            _accept1_thread = Thread(target=self.tp.accept1, name='AcceptService1')
            _accept2_thread = Thread(target=self.tp.accept2, name='AcceptService2')
            _accept1_thread.start()
            _accept2_thread.start()

            # Service thread
            _ts = Thread(target=self.tp.service, name='TelnetProxyService')
            _ts.start()

            # Wait for service to exit (IGW disconnect)
            _ts.join()
            _accept1_thread.join(timeout=2)
            _accept2_thread.join(timeout=2)

        finally:
            # Always cleanup MqttActuator when TelnetProxy exits
            logging.info("TelnetProxy exiting, shutting down MqttActuator...")
            if self._ma:
                self._ma.request_shutdown()
                self._ma.join(timeout=5)
                if self._ma.is_alive():
                    logging.warning("MqttActuator did not exit cleanly")
                self._ma = None

            logging.info("ThreadedTelnetProxy: Run completed")
```

---

## Phase 3: Add Restart Trigger Detection

### Objective
Detect `$igw clear` in analyser (already done, no code changes needed).

---

### Step 3.1: Verify analyser.py Handles `$igw clear`

**File:** `myhargassner/analyser.py`

**Verification:**

Check that `parse_request()` already handles `$igw clear`:

```python
# Verify this code exists in analyser.py
def parse_request(self, data: bytes) -> str:
    # ... existing code ...

    # This should already be present (around line 129-130)
    # If not, add it:
    elif _part.startswith('$igw clear'):
        logging.info('$igw clear detected')
        _state = '$igw clear'

    # ... existing code ...
    else:
        logging.warning('Analyser received unknown request %s - treating as passthrough', _part)
        _state = 'passthrough'

    return _state
```

**Action:** If `$igw clear` handling is missing, add it. Otherwise, no changes needed.

---

## Phase 4: Implement Main Loop Restart Logic

### Objective
Add restart orchestration to main.py.

---

### Step 4.1: Add wait_for_restart_trigger() Function

**File:** `myhargassner/main.py`

**Changes:**

```python
# Add this function BEFORE main()
def wait_for_restart_trigger(pub: PubSub) -> str:
    """
    Wait for restart request from any component via PubSub.

    Args:
        pub: PubSub instance to subscribe to system channel

    Returns:
        str: Reason for restart
    """
    # Subscribe to system channel for restart messages
    system_queue = pub.subscribe('system', 'MainRestartMonitor')

    try:
        while True:
            try:
                # Wait for restart request message
                iterator = system_queue.listen(timeout=1.0)
                message = next(iterator)

                if message and message['data'] == 'RESTART_REQUESTED':
                    logging.info("Restart request received via PubSub")
                    return "System_Restart_Request"

            except StopIteration:
                # No message received, continue waiting
                continue

    finally:
        # Cleanup subscription
        pub.unsubscribe('system', system_queue)
```

---

### Step 4.2: Modify main() to Add Restart Loop

**File:** `myhargassner/main.py`

**Changes:**

```python
def main():
    """Main entry point with restart orchestration."""
    # Keep existing app_config initialization
    # app_config = AppConfig() is already defined globally

    restart_count = 0
    max_restarts = 1000  # Safety limit to prevent infinite restart loops

    while restart_count < max_restarts:
        restart_count += 1
        logging.info("=" * 60)
        logging.info("System session starting (session #%d)", restart_count)
        logging.info("=" * 60)

        try:
            # Create fresh PubSub for this session
            pub = PubSub(max_queue_in_a_channel=9999)

            # Create all components
            pln = PubSubListener('test', 'PubSubListener', pub)
            mi = MqttInformer(app_config, pub)
            bls = ThreadedBoilerListenerSender(app_config, pub, delta=100)
            gls = ThreadedGatewayListenerSender(app_config, pub, delta=100)
            tln = ThreadedTelnetProxy(app_config, pub, port=23)

            # Start all threads
            logging.info("Starting all components...")
            pln.start()
            bls.start()
            gls.start()
            tln.start()
            mi.start()

            # Wait for restart request from any component
            logging.info("System running, waiting for restart request...")
            restart_reason = wait_for_restart_trigger(pub)
            logging.info("Restart requested: %s", restart_reason)

            # Orchestrate graceful shutdown of ALL components
            logging.info("Orchestrating shutdown of all components...")

            # Request shutdown via request_shutdown() method
            gls.request_shutdown()
            bls.request_shutdown()
            tln.request_shutdown()
            mi.request_shutdown()
            pln.request_shutdown()

            # Wait for all threads to exit cleanly (with timeout)
            logging.info("Waiting for threads to exit...")
            gls.join(timeout=5)
            bls.join(timeout=5)
            tln.join(timeout=5)
            mi.join(timeout=5)
            pln.join(timeout=5)

            # Check for zombie threads
            if gls.is_alive():
                logging.warning("GatewayListener did not exit cleanly")
            if bls.is_alive():
                logging.warning("BoilerListener did not exit cleanly")
            if tln.is_alive():
                logging.warning("TelnetProxy did not exit cleanly")
            if mi.is_alive():
                logging.warning("MqttInformer did not exit cleanly")

            logging.info("All components stopped")
            logging.info("Waiting for next IGW connection...")
            time.sleep(2)  # Brief pause before restart

        except KeyboardInterrupt:
            logging.info("Keyboard interrupt, exiting...")
            break
        except Exception as e:
            logging.error("Unexpected error: %s", e, exc_info=True)
            time.sleep(5)  # Wait before retry on error

    logging.info("System exiting after %d sessions", restart_count)


if __name__ == '__main__':
    main()
```

---

## Phase 5: Testing & Validation

### Objective
Verify the implementation works correctly for all scenarios.

---

### Step 5.1: Unit Testing

Create test scenarios for each component:

**Test File:** `tests/test_bug_001_restart.py` (create new file)

```python
"""Unit tests for Bug #1 restart functionality."""
import unittest
import time
from threading import Thread
from myhargassner.pubsub.pubsub import PubSub
from myhargassner.gateway import GatewayListenerSender
from myhargassner.boiler import BoilerListenerSender
from myhargassner.appconfig import AppConfig


class TestRestartMechanism(unittest.TestCase):
    """Test restart mechanism for all components."""

    def setUp(self):
        """Set up test fixtures."""
        self.app_config = AppConfig()
        self.pub = PubSub(max_queue_in_a_channel=100)

    def test_gateway_listener_shutdown(self):
        """Test GatewayListener responds to shutdown request."""
        gls = GatewayListenerSender(self.app_config, self.pub, delta=0)

        # Verify shutdown flag is False initially
        self.assertFalse(gls._shutdown_requested)

        # Request shutdown
        gls.request_shutdown()

        # Verify shutdown flag is set
        self.assertTrue(gls._shutdown_requested)

    def test_boiler_listener_shutdown(self):
        """Test BoilerListener responds to shutdown request."""
        bls = BoilerListenerSender(self.app_config, self.pub, delta=0)

        # Verify shutdown flag is False initially
        self.assertFalse(bls._shutdown_requested)

        # Request shutdown
        bls.request_shutdown()

        # Verify shutdown flag is set
        self.assertTrue(bls._shutdown_requested)

    def test_restart_request_pubsub(self):
        """Test restart request is published to PubSub."""
        # Subscribe to system channel
        system_queue = self.pub.subscribe('system', 'TestMonitor')

        # Publish restart request
        self.pub.publish('system', 'RESTART_REQUESTED')

        # Verify message received
        iterator = system_queue.listen(timeout=1.0)
        message = next(iterator)

        self.assertIsNotNone(message)
        self.assertEqual(message['data'], 'RESTART_REQUESTED')

        # Cleanup
        self.pub.unsubscribe('system', system_queue)


if __name__ == '__main__':
    unittest.main()
```

**Run tests:**
```bash
python -m pytest tests/test_bug_001_restart.py -v
```

---

### Step 5.2: Integration Testing

Test complete restart cycle:

**Test Scenario 1: Normal `$igw clear` Flow**

```
1. Start system
2. IGW connects
3. IGW sends commands
4. IGW sends "$igw clear"
5. Boiler responds "$ack"
6. TelnetProxy requests restart
7. main.py shuts down all components
8. System restarts
9. Verify all components running again
```

**Test Scenario 2: Connection Closed Flow**

```
1. Start system
2. IGW connects
3. IGW closes connection abruptly
4. TelnetProxy detects empty recv
5. TelnetProxy requests restart
6. main.py shuts down all components
7. System restarts
8. Verify all components running again
```

**Test Scenario 3: Duplicate Discovery Flow**

```
1. Start system
2. IGW connects
3. System running normally
4. IGW broadcasts new "HargaWebApp"
5. GatewayListener publishes discovery
6. TelnetProxy detects duplicate discovery
7. TelnetProxy requests restart
8. main.py shuts down all components
9. System restarts
10. Verify all components running again
```

---

### Step 5.3: Manual Testing Checklist

- [ ] System starts correctly
- [ ] All components initialize properly
- [ ] IGW connection works
- [ ] Normal commands work
- [ ] `$igw clear` triggers restart
- [ ] Connection close triggers restart
- [ ] Duplicate "HargaWebApp" triggers restart
- [ ] All components shutdown cleanly
- [ ] System restarts successfully
- [ ] No zombie threads after restart
- [ ] No memory leaks after multiple restarts
- [ ] Logs show correct restart reason
- [ ] MQTT devices reconnect after restart
- [ ] Boiler connection works after restart

---

## Testing Strategy Summary

### Unit Tests
✅ Test individual component shutdown
✅ Test PubSub restart messages
✅ Test restart trigger detection

### Integration Tests
✅ Test complete restart cycle for each trigger
✅ Test multiple restart cycles
✅ Test rapid reconnection scenarios

### Manual Tests
✅ Test with real IGW hardware
✅ Test all three restart triggers
✅ Verify logs and behavior

---

## Rollback Plan

If implementation fails:

1. **Keep git commit history clean** - One commit per phase
2. **Revert commits in reverse order** - Phase 4 → Phase 3 → Phase 2 → Phase 1
3. **Restore from backup** - Keep copy of original files

**Rollback Command:**
```bash
git log --oneline  # Find commit hash before changes
git revert <commit-hash>  # Revert specific commit
```

---

## Future Enhancements (Out of Scope)

### Enhancement 1: Restart Metrics
- Track restart count, frequency, duration
- Publish to MQTT for monitoring
- Alert if restart frequency exceeds threshold

### Enhancement 2: Graceful Degradation
- If restart fails repeatedly, enter safe mode
- Disable non-critical features
- Maintain basic telnet proxy functionality

### Enhancement 3: Manual Restart Command
- Add MQTT command to trigger restart
- Useful for debugging and maintenance

### Enhancement 4: Faster Restart
- Cache boiler configuration
- Skip discovery if network addresses unchanged
- Reduce restart time from 30s to 10s

---

## Conclusion

This technical strategy provides a complete, step-by-step implementation plan for fixing Bug #1.

**Key Principles:**
- ✅ Coherent design with single restart mechanism
- ✅ Clear separation of concerns
- ✅ Comprehensive testing strategy
- ✅ Safe rollback plan

**Estimated Timeline:**
- Phase 1: 1 day (6 steps)
- Phase 2: 1.5 days (6 steps)
- Phase 3: 0.5 days (1 step)
- Phase 4: 0.5 days (2 steps)
- Phase 5: 2 days (testing)
- **Total: 5-6 days**

Ready for implementation!
