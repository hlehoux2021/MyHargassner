# Issue #1 Analysis: Connection Lifecycle Problem with IGW Disconnection

## 🔍 Problem Summary

The issue occurs when the IGW (Internet Gateway) sends specific commands (`$dhcp renew`, `$igw clear`) and then **closes the telnet connection abruptly** to restart a fresh connection dialog. MyHargassner doesn't properly handle this disconnection scenario:
- TelnetProxy tries to restart service1 internally without clearing state
- The caller context is lost (_caller becomes 0 or stale)
- When IGW initiates a new connection (after new UDP broadcast), TelnetProxy is still stuck trying to recover from the previous connection
- This creates a desynchronization between IGW's connection state and MyHargassner's state

## 📋 Complete Log Sequence Analysis

```
09:51:28,858 - WARNING - TelnetProxyService - Analyser received unknown request $dhcp renew - treating as passthrough
09:51:32,578 - WARNING - TelnetProxyService - Analyser received unknown request $igw clear - treating as passthrough
09:51:32,788 - WARNING - TelnetProxyService - New response (passthrough) b'$ack\r\n'
09:51:32,790 - WARNING - TelnetProxyService - Analyser received unknown request $dhcp renew - treating as passthrough
09:51:33,011 - WARNING - TelnetProxyService - New response (passthrough) b'zIP 0.0.0.0\r\nzIP 10.0.0.72\r\npm 1 1.2 7.7 18.8...'

[GAP - IGW closed connection here]

09:52:09,675 - INFO - GatewayListener - HargaWebApp££6    ← IGW sends new UDP broadcast
09:52:09,676 - INFO - GatewayListener - SN: [0039808]
09:52:22,940 - INFO - BoilerListener - HSV discovered
```

**Key observation:** After receiving responses at 09:51:33, there's a **17-second gap** until the next UDP broadcast at 09:52:09. This indicates **IGW closed the telnet connection** and is starting a new connection sequence from scratch.

---

## 🐛 Root Cause Analysis

### **Primary Issue: Connection Lifecycle Management**

#### Current Architecture Flow:
```
[main.py]
  ├── Start GatewayListener thread (continuously listens for UDP)
  ├── Start BoilerListener thread (continuously listens for UDP)
  └── Start TelnetProxy thread (one-time initialization)
        ├── bind/listen on port 23 (service1 for IGW)
        ├── bind/listen on port 4000 (service2 for commands)
        └── accept1() waits for FIRST IGW connection
        └── loop() handles ALL subsequent communication
              └── restart_service1() if connection error
```

**Problem:** TelnetProxy is started **once** by main.py and runs forever. It doesn't have visibility into the IGW connection lifecycle:
- IGW broadcasts UDP "HargaWebApp" before **each** telnet dialog
- GatewayListener **detects** these broadcasts but doesn't signal TelnetProxy
- When IGW closes the connection, TelnetProxy detects it as an error and tries `restart_service1()`
- But restart_service1() doesn't clear the caller state or synchronize with IGW's new connection attempt

### **Secondary Issues**

#### 1. **Passthrough State Persistence** (Acceptable behavior, but could be clearer)

**Location:** [analyser.py:129-130](myhargassner/analyser.py:129-130), [analyser.py:143-144](myhargassner/analyser.py:143-144)

**Current behavior:**
- Unknown commands set `_state = 'passthrough'`
- Requests and responses ARE forwarded correctly (this is good)
- State doesn't explicitly stay as 'passthrough' for multiple responses

**Proposed improvement:**
```python
# In _parse_response_buffer()
if _state == 'passthrough':
    logging.warning('Passthrough response: %s', repr(buffer))
    # Keep state as passthrough since we don't know how many responses will come
    # State will be cleared when next request arrives (which sets a new state)
    return 'passthrough', _login_done  # Explicitly keep state
```

#### 2. **Caller Context Lost on Reconnection**

**Location:** [telnetproxy.py:440-441](myhargassner/telnetproxy.py:440-441), [telnetproxy.py:607](myhargassner/telnetproxy.py:607)

When IGW disconnects and TelnetProxy calls `restart_service1()`:
- The old service1 socket is closed
- A new socket is created and `accept1()` waits for new connection
- **BUT** the `loop()` method continues running with stale `_caller` and `_state` variables
- When responses arrive from boiler (or IGW reconnects), caller is 0 or stale

---

## 💡 Proposed Solution: Connection-Driven Lifecycle

### **Core Architectural Change**

**Make GatewayListener directly responsible for TelnetProxy lifecycle.**

**Rationale:** GatewayListener already detects when IGW wants to connect (via "HargaWebApp" UDP broadcast). Instead of signaling through PubSub to a coordinator, GatewayListener should directly manage the TelnetProxy lifecycle since:
- It has the context about IGW state
- It's a 1-to-1 relationship (one IGW discovery → one TelnetProxy)
- Direct management is simpler and more efficient
- Avoids unnecessary thread and message passing overhead

**Flow:**

1. **GatewayListener detects UDP "HargaWebApp" broadcast** → IGW wants to start new dialog
2. **GatewayListener checks if TelnetProxy is currently running:**
   - If not running → Start new ThreadedTelnetProxy
   - If running → Request graceful shutdown of existing TelnetProxy, wait briefly, then start fresh
3. **TelnetProxy runs for the duration of ONE IGW connection session:**
   - Accept connection from IGW on port 23 (service1)
   - Handle all requests/responses
   - When IGW disconnects (empty recv or socket error) → Exit cleanly
   - **Don't try to restart internally** - let GatewayListener handle next connection
4. **Next UDP broadcast triggers new TelnetProxy instance with completely clean state**

**Key insight:** The UDP broadcast is the **signal** that IGW wants to connect. We don't need an intermediary coordinator - GatewayListener can manage this directly.

---

## 📐 Implementation Design

### **Change 1: GatewayListener Directly Manages TelnetProxy**

**File:** [myhargassner/gateway.py](myhargassner/gateway.py)

Add TelnetProxy lifecycle management directly in GatewayListenerSender:

```python
from typing import Optional
from myhargassner.telnetproxy import ThreadedTelnetProxy

class GatewayListenerSender(ListenerSender):
    """This class extends ListenerSender class to implement the gateway listener."""

    _current_telnet: Optional[ThreadedTelnetProxy] = None

    def __init__(self, appconfig: AppConfig, communicator: PubSub, delta: int = 0):
        super().__init__(appconfig, communicator, appconfig.gw_iface(), appconfig.bl_iface())
        self.udp_port = self._appconfig.udp_port()
        self.delta = delta
        self._current_telnet = None  # Track the current TelnetProxy instance

    def _manage_telnet_lifecycle(self):
        """Manage TelnetProxy lifecycle when IGW wants to connect."""
        logging.info('GatewayListener: IGW initiating connection, managing TelnetProxy')

        # If TelnetProxy is running, request shutdown
        if self._current_telnet and self._current_telnet.is_alive():
            logging.info('GatewayListener: Stopping existing TelnetProxy')
            self._current_telnet.tp.request_shutdown()
            self._current_telnet.join(timeout=3.0)  # Wait max 3s for clean exit
            if self._current_telnet.is_alive():
                logging.warning('GatewayListener: TelnetProxy did not exit cleanly')

        # Start fresh TelnetProxy for this new IGW connection
        logging.info('GatewayListener: Starting new TelnetProxy')
        self._current_telnet = ThreadedTelnetProxy(self._appconfig, self._com, port=23)
        self._current_telnet.start()

    def handle_data(self, data: bytes, addr: tuple):
        """handle udp data"""
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
                logging.info('HargaWebApp££%s - IGW initiating connection', _subpart)
                self._com.publish(self._channel, f"HargaWebApp££{_subpart}")

                # ← NEW: Directly manage TelnetProxy lifecycle
                self._manage_telnet_lifecycle()

            if part.startswith('SN:'):
                _subpart = part[3:]
                logging.info('SN: [%s]', _subpart)
                self._com.publish(self._channel, f"SN££{_subpart}")
```

### **Change 2: TelnetProxy Handles Clean Shutdown**

**File:** [myhargassner/telnetproxy.py](myhargassner/telnetproxy.py)

Modify TelnetProxy to handle graceful shutdown and exit on IGW disconnection:

```python
class TelnetProxy(ChanelReceiver, MqttBase):
    """This class implements the TelnetProxy."""

    _shutdown_requested: bool = False

    def request_shutdown(self):
        """Request graceful shutdown of this TelnetProxy instance."""
        logging.info("TelnetProxy: Shutdown requested")
        self._shutdown_requested = True

    def loop(self) -> None:
        """Main loop waiting for requests and replies, handling all active sockets."""
        _data: bytes
        _addr: tuple
        read_sockets: list[socket.socket] = []
        _state: str = ''
        _buffer: bytes = b''
        _mode: str = ''
        _caller: int = 1  # Default to service1

        logging.debug('Active sockets: %d', len(self._active_sockets))

        while self._active_sockets and not self._shutdown_requested:  # ← CHANGED: Check shutdown flag
            if self._msq:
                logging.debug('TelnetProxy ChannelQueue size: %d', self._msq.qsize())
            try:
                read_sockets, write_sockets, error_sockets = select.select(
                    list(self._active_sockets), [], [], 1.0
                )
            except select.error as err:
                logging.error("Select error: %s", str(err))
                continue

            for _sock in read_sockets:
                if _sock == self._service1.socket():
                    # ... existing service1 handling ...
                    try:
                        _data = self._service1.recv()
                        if not _data:
                            logging.info('service1: IGW closed connection gracefully')
                            # ← CHANGED: Don't raise error, just exit loop cleanly
                            self._shutdown_requested = True
                            break
                        # ... rest of processing ...
                    except socket.error as err:
                        logging.error("Socket error in service1: %s", str(err))
                        # ← CHANGED: Don't try to restart, exit gracefully
                        self._shutdown_requested = True
                        break
                # ... handle other sockets ...

        logging.info("TelnetProxy loop exiting cleanly")

    def service(self) -> None:
        """Main service - run once per IGW connection."""
        logging.debug('TelnetProxy::service starting')

        # Initial setup
        if not self.restart_client():
            raise RuntimeError("Failed initial client connection")

        # Run the main loop for this connection session
        logging.info('TelnetProxy: Waiting for IGW connection on service1')
        self.loop()

        # Clean exit (no restart attempts)
        logging.info('TelnetProxy: Connection ended, exiting service')
```

### **Change 3: Simplify Main - Remove TelnetProxy Initialization**

**File:** [myhargassner/main.py](myhargassner/main.py)

Since GatewayListener now manages TelnetProxy lifecycle, remove the TelnetProxy initialization from main:

```python
def main():
    """Main entry point for the application."""

    pln = PubSubListener('test', 'PubSubListener', pub)
    pln.start()

    # MqttInformer will receive info on the mq queue
    mi = MqttInformer(app_config, pub)

    # create a BoilerListener
    bls = ThreadedBoilerListenerSender(app_config, pub, delta=100)

    # create a gateway listener
    # ← CHANGED: GatewayListener now manages TelnetProxy lifecycle internally
    gls = ThreadedGatewayListenerSender(app_config, pub, delta=100)

    # ← REMOVED: No longer start TelnetProxy here
    # tln = ThreadedTelnetProxy(app_config, pub, port=23)
    # tln.start()

    bls.start()
    gls.start()  # GatewayListener will start TelnetProxy when IGW broadcasts
    mi.start()
```

**Key changes:**
- Remove `ThreadedTelnetProxy` initialization from main
- GatewayListener creates and manages TelnetProxy when it detects "HargaWebApp" broadcast
- Simpler startup - no coordinator needed

---

## 📝 Additional Minor Improvements

### **Improvement 1: Keep Passthrough State Explicitly**

**File:** [myhargassner/analyser.py](myhargassner/analyser.py)

In `_parse_response_buffer()` around line 143:

```python
if _state == 'passthrough':
    logging.debug('Passthrough response: %s', repr(buffer[:100]))  # Log first 100 bytes
    # Keep state as passthrough since we don't know how many responses will arrive
    # State will be cleared only when a new request arrives (which sets a new state)
    # This is intentional - just pass through and wait for next request
    return 'passthrough', False  # Explicitly return passthrough state
```

### **Improvement 2: Add Known Commands (Optional)**

If you want to explicitly handle these commands instead of passthrough:

**File:** [myhargassner/analyser.py](myhargassner/analyser.py)

```python
# In parse_request() around line 85
elif _part.startswith('$igw clear'):
    logging.debug('$igw clear detected')
    _state = '$igw clear'
elif _part.startswith('$dhcp renew'):
    logging.debug('$dhcp renew detected')
    _state = '$dhcp renew'

# In _parse_response_buffer() around line 260
elif _state == '$dhcp renew':
    # Responses can be: $ack, zIP 0.0.0.0, zIP <new_ip>, or pm buffer
    if '$ack' in _part or _part.startswith('zIP'):
        logging.debug('$dhcp renew response: %s', _part)
        # Keep state until we see end marker or next request
        if '$ack' in _part:
            _state = ''
elif _state == '$igw clear':
    if '$ack' in _part:
        logging.debug('$igw clear acknowledged')
        _state = ''
```

---

## 📊 Implementation Priority

### ⭐ High Priority - Core Architectural Fix
**Connection-Driven Lifecycle:** Implement TelnetCoordinator and connection-based TelnetProxy lifecycle
- **Why:** Fixes the root cause - synchronization between IGW connection state and MyHargassner state
- **Impact:** Prevents all "caller 0" errors and restart loops
- **Risk:** Medium - requires architectural change but clear separation of concerns

### ⚠️ Medium Priority - Clarity Improvements
**Explicit Passthrough State Handling:** Make passthrough behavior explicit and well-documented
- **Why:** Clarifies intended behavior, prevents confusion
- **Impact:** Better logging, easier debugging
- **Risk:** Low - documentation and minor code change

### ℹ️ Low Priority - Optional Enhancement
**Add Explicit Command Handlers:** Add `$dhcp renew` and `$igw clear` handlers
- **Why:** More explicit control over these commands
- **Impact:** Slightly better logging of these specific commands
- **Risk:** Low - but not strictly necessary if passthrough works

---

## 🧪 Testing Strategy

### Phase 1: Basic Connection Lifecycle
1. Start MyHargassner
2. Trigger IGW to send HargaWebApp broadcast
3. Verify TelnetCoordinator starts TelnetProxy
4. Verify IGW establishes telnet connection
5. Send normal commands, verify they work

### Phase 2: Disconnection Handling
1. Trigger IGW to send `$dhcp renew` and `$igw clear`
2. Verify responses are forwarded correctly
3. Verify IGW closes connection
4. Verify TelnetProxy exits cleanly (no restart attempts)
5. Check logs for clean shutdown messages

### Phase 3: Reconnection
1. Trigger IGW to send new HargaWebApp broadcast
2. Verify TelnetCoordinator starts fresh TelnetProxy
3. Verify new connection established successfully
4. Send commands, verify full functionality restored

### Phase 4: Rapid Reconnection
1. Trigger multiple disconnect/reconnect cycles
2. Verify no "caller 0" errors
3. Verify no restart loops
4. Verify clean state each time

---

## 📚 Related Code References

- **GatewayListener:** [myhargassner/gateway.py:127-150](myhargassner/gateway.py:127-150)
- **TelnetProxy loop:** [myhargassner/telnetproxy.py:428-622](myhargassner/telnetproxy.py:428-622)
- **TelnetProxy run:** [myhargassner/telnetproxy.py:735-774](myhargassner/telnetproxy.py:735-774)
- **Main coordination:** [myhargassner/main.py:85-113](myhargassner/main.py:85-113)
- **Service restart logic:** [myhargassner/telnetproxy.py:623-673](myhargassner/telnetproxy.py:623-673)
- **Analyser passthrough:** [myhargassner/analyser.py:129-130](myhargassner/analyser.py:129-130), [analyser.py:143-145](myhargassner/analyser.py:143-145)
