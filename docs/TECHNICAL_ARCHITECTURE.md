# Technical Discovery & Analysis - MyHargassner

## 📋 Technical Scope Summary

MyHargassner is a **Python-based gateway service** that sits between a Hargassner pellet boiler and its Internet Gateway (IGW), intercepts their communication, extracts telemetry data, and exposes it via MQTT for home automation integration (Home Assistant/Jeedom). The system also enables bidirectional control by sending commands back to the boiler through MQTT Select/Number entities.

---

## 🏗️ Codebase Architecture Analysis

### **Core Design Pattern: Network Relay with PubSub Communication**

MyHargassner implements a multi-threaded relay architecture where components communicate asynchronously via a PubSub message bus. The application sits between two network interfaces:
- **eth0** (or similar): Connected to home network where the IGW resides
- **eth1** (or similar): Dedicated network for the pellet boiler (requires DHCP server configuration)

For network setup details, see [../NETWORK_SETUP.md](../NETWORK_SETUP.md).

### **Component Architecture**

The system consists of 5 main threaded components that communicate via PubSub channels:

1. **GatewayListenerSender** ([gateway.py](../../myhargassner/gateway.py))
   - Listens on the gateway interface for UDP broadcasts from IGW (port 50000, 50002)
   - Relays packets to the boiler
   - Publishes gateway discovery info (address/port) to "bootstrap" channel

2. **BoilerListenerSender** ([boiler.py](../../myhargassner/boiler.py))
   - Listens on the boiler interface for UDP broadcasts from boiler (port 35601)
   - Relays packets to the gateway
   - Publishes boiler discovery info (address/port) to "bootstrap" channel
   - Analyzes boiler "pm" telemetry buffers sent every second

3. **TelnetProxy** ([telnetproxy.py](../../myhargassner/telnetproxy.py))
   - Acts as a telnet relay between IGW and boiler (port 23)
   - Runs internal telnet server on port 4000 for receiving commands from MqttActuator
   - Subscribes to "bootstrap" channel to discover boiler/gateway addresses
   - Uses `Analyser` to parse telnet request/response dialogs
   - Publishes extracted information (login tokens, keys, parameters) to "info" channel
   - Uses `select()` to multiplex between IGW, boiler, and command sockets

4. **MqttInformer** ([mqtt_informer.py](../../myhargassner/mqtt_informer.py))
   - Subscribes to "info" channel to receive boiler data
   - Implements MQTT Home Assistant Discovery protocol
   - Creates and updates MQTT sensors for boiler parameters
   - Uses `ha-mqtt-discoverable` library for sensor management

5. **MqttActuator** ([mqtt_actuator.py](../../myhargassner/mqtt_actuator.py))
   - Subscribes to "info" channel to receive boiler mode configurations
   - Subscribes to "track" channel for bidirectional state synchronization
   - Creates MQTT Select entities for mode parameters (PR001, PR011, PR012, PR040)
   - Creates MQTT Number entities for numeric setpoints (parameters 4, 5, 7, 8, A6d)
   - Sends telnet "$par set" commands to boiler via TelnetProxy internal interface (port 4000)
   - Implements threaded callbacks for MQTT control messages
   - Currently supports 9 parameters with dynamic discovery system

### **Key Classes and Inheritance**

```
ShutdownAware (mixin)
└── Provides graceful shutdown via _shutdown_requested flag

NetworkData
└── Stores discovered network information (gateway/boiler IP and ports)

ChanelReceiver (extends NetworkData)
└── Adds PubSub subscription and message handling
    └── ListenerSender (extends ChanelReceiver + ShutdownAware)
        └── Abstract base for UDP listener/sender components
            ├── GatewayListener (in gateway.py)
            └── BoilerListener (in boiler.py)

Thread
└── ThreadedListenerSender (abstract base)
    ├── ThreadedGatewayListenerSender
    └── ThreadedBoilerListenerSender

ShutdownAware + MqttBase
├── MqttInformer
└── MqttActuator
```

### **PubSub Channel Communication**

The system uses four main channels:

- **"bootstrap"**: Network discovery (BL_ADDR, BL_PORT, GW_ADDR, GW_PORT, GWT_PORT)
- **"info"**: Boiler telemetry and configuration (KEY, TOKEN, pm values, mode configurations)
- **"track"**: Parameter change notifications from Analyser to MqttActuator for bidirectional sync
- **"system"**: System-level messages (e.g., RESTART_REQUESTED)

### **Data Flow Example**

```
IGW sends telnet "$login token" → GatewayListener → TelnetProxy → Boiler
                                                    ↓ (analyzes)
                                                Analyser extracts token
                                                    ↓ (publishes)
                                            "info" channel: "TOKEN££xyz"
                                                    ↓
                                            MqttInformer receives
                                                    ↓
                                        Creates/updates MQTT sensor
```

### **Reconnection & Session Management**

The TelnetProxy implements a multi-trigger reconnection system to handle IGW reconnections:

#### **Reconnection Triggers**

1. **TRIGGER 1: Socket Errors** - Automatic reconnection when network fails
   - Socket read/write errors detected and logged
   - Reconnection attempts with retry logic (up to 20 attempts)

2. **TRIGGER 2: Protocol Violations** - Boiler responses indicating reconnection needed
   - Detection of `$dhcp renew` and `$igw clear` commands
   - These indicate the boiler received reconnection requests from IGW

3. **TRIGGER 3: New HargaWebApp Broadcast** (experimental)
   - Monitor for fresh IGW discovery broadcasts during active session
   - **Current behavior (experimental)**: Wait for IGW to close connection naturally instead of forcing disconnect
   - Rationale: Allows graceful handoff of session control without abruptly terminating the connection
   - Checked periodically via `monitor_for_reconnection()` method

#### **Session State Tracking**

- `_telnet_session_active`: Boolean flag tracking if telnet session is currently active
- `_session_end_requested`: Flag for detecting `$igw clear` commands that request session termination
- `_discovery_complete`: Flag tracking when boiler discovery phase completes

#### **System Restart Orchestration**

The application also implements automatic restart capability:
- Components can request system restart by publishing "RESTART_REQUESTED" to "system" channel
- Main loop (`main.py`) monitors for restart requests via `wait_for_restart_trigger()`
- On restart request, all components are gracefully shutdown via `request_shutdown()` method
- System creates fresh PubSub instance and restarts all components

### **Platform Compatibility**

The codebase supports both Linux and macOS (Darwin):
- **Linux**: Uses network interface names (eth0, eth1)
- **macOS**: Uses IP addresses for interface binding
- `SocketManager` class abstracts platform differences
- Platform detection via `platform.system()`

### **Supporting Modules:**

- **[myhargassner/appconfig.py](../../myhargassner/appconfig.py)** - Configuration management
  - Loads from `myhargassner.ini` file
  - Merges defaults → config file → CLI arguments
  - Provides typed accessors for network, MQTT, and logging settings
- **[myhargassner/hargconfig.py](../../myhargassner/hargconfig.py)** - Boiler parameter definitions
  - Maps 180+ telemetry parameters (c0-c180) to names/units/descriptions
  - Configurable `wanted` list for selective monitoring
  - `commands` list: telnet commands to fetch boiler parameters (PR001, PR011, PR012, PR040, 4, 5, 7, 8, A6d)
- **[myhargassner/socket_manager.py](../../myhargassner/socket_manager.py)** - Cross-platform socket handling (Linux/MacOS)
- **[myhargassner/telnethelper.py](../../myhargassner/telnethelper.py)** - Telnet client utilities
- **[myhargassner/pubsub/](../../myhargassner/pubsub/)** - Internal message bus (from Thierry Maillard)

---

## 🔍 Remaining Areas for Development Work

Based on the README's known limitations and current codebase state:

### **1. Configuration System** ([appconfig.py](myhargassner/appconfig.py))
- **Status:** ✅ **WORKING AS DESIGNED**
- **Current Implementation:**
  - Loads `myhargassner.ini` from current working directory (line 66)
  - When run from CLI: searches in the directory where command is executed
  - When run as systemd service: uses `/etc/myhargassner` (configured in `myhargassner.service` WorkingDirectory)
  - Merges configuration: defaults → INI file → CLI arguments
  - MQTT password validation in main.py:40-42

### **2. Error Handling** ([mqtt_actuator.py](myhargassner/mqtt_actuator.py:721-845))
- **Status:** ⚠️ **PARTIALLY IMPLEMENTED**
- **Implemented features:**
  - ✅ Socket error handling with automatic reconnection
  - ✅ Retry logic: max 20 attempts with exponential backoff
  - ✅ Exit reason tracking: 'success', 'max_tries', 'reconnect_failed', 'unexpected_error'
  - ✅ Input validation: parameter IDs, option values, numeric ranges
  - ✅ Comprehensive logging at all error points
- **Remaining work:**
  - ⚠️ Boiler error response detection exists but not properly handled: `$err`, `$permission denied`, `zERR` are detected and logged but treated as success
  - Need to set proper exit_reason when boiler returns error responses
  - Consider exposing error states via MQTT sensors for user visibility

### **3. Boiler Control Expansion** ([mqtt_actuator.py](myhargassner/mqtt_actuator.py))
- **Status:** ✅ **COMPLETED**
- **Implemented features:**
  - ✅ Dynamic parameter discovery - no longer hardcoded
  - ✅ Supports 9 parameters: PR001, PR011, PR012, PR040, parameter 4, parameter 5, parameter 7, parameter 8, parameter A6d
  - ✅ Generic parameter parsing via `_parse_parameter_response()`
  - ✅ Dual entity type support: Select (for modes) and Number (for numeric values)
  - ✅ Automatic MQTT entity creation based on parameter format
  - ✅ Bidirectional sync: receives parameter changes from boiler via "track" channel
  - ✅ Parameter command list centralized in `HargConfig.commands` for easy maintenance

### **4. Software Version Support** ([hargconfig.py](myhargassner/hargconfig.py:245))
- **Status:** ⚠️ **NOT ADDRESSED**
- **Current:** Only V14.0n3 tested
- **Work needed:**
  - Version detection from `$info` response (SWV field)
  - Version-specific pm buffer mappings
  - Compatibility matrix documentation
  - Test with other firmware versions (if hardware available)

### **5. Struct Exception Bug** ([mqtt_actuator.py](myhargassner/mqtt_actuator.py))
- **Status:** ✅ **RESOLVED** (PR #3, commit 3714075)
- **Root cause identified:**
  - Dual-loop race condition: Both MainThread and background thread processing MQTT messages
  - struct.error crash in paho-mqtt when both threads accessed internal buffers simultaneously
- **Solution implemented:**
  - ✅ Removed redundant `client.loop()` call from MainThread
  - ✅ Rely solely on ha-mqtt-discoverable's background thread (started by library)
  - ✅ Added extensive comments explaining why NOT to call loop() manually
  - ✅ Verified stable operation over extended testing period

---

## 📐 Existing Patterns and Conventions

### **Architecture Patterns:**

1. **Threading Model**
   - Dedicated thread per major component (TelnetProxy, Boiler, Gateway, MQTT)
   - Pattern: `Threaded<T>` wrapper class (see [mqtt_actuator.py:669-743](myhargassner/mqtt_actuator.py:669-743))
   - Example: `ThreadedTelnetProxy`, `ThreadedBoilerListenerSender`

2. **PubSub Communication**
   - Internal message bus with named channels (`bootstrap`, `info`, `track`, `system`)
   - **Channels:**
     - `bootstrap`: Network discovery (gateway/boiler addresses)
     - `info`: Boiler telemetry and configuration data
     - `track`: Parameter change notifications (Analyser → MqttActuator)
     - `system`: System-level messages (RESTART_REQUESTED)
   - Publishers use `communicator.publish(channel, data)`
   - Subscribers use `communicator.subscribe(channel, name)` → get iterator
   - Pattern: Non-blocking with timeout (e.g., `listen(timeout=3)`)

3. **Network Discovery**
   - UDP broadcast listening on specific ports
   - First packet triggers binding of sender socket
   - Discovery info published to `bootstrap` channel
   - Pattern: `handle_first()` → `publish_discovery()` → `handle_data()` → `send()`

4. **Configuration Management**
   - Three-tier precedence: Defaults → INI file → CLI args
   - Centralized in `AppConfig` class
   - Typed accessor methods (e.g., `gw_iface()`, `mqtt_port()`)

5. **MQTT Integration**
   - Uses `ha-mqtt-discoverable` library for Home Assistant auto-discovery
   - Device-first approach: Create `DeviceInfo` then attach sensors/selects
   - Pattern: `MySensor` extends base Sensor with custom initialization
   - Callbacks use `user_data` parameter to pass context (param_id)

### **Code Style Conventions:**

- **Encoding:** `latin1` for telnet protocol (to handle special characters like é, ï)
- **Logging:** Extensive debug logging with `logging.debug()` throughout
- **Error Handling:** Try/except with logging, raise specific exceptions (`HargSocketError`, `SocketBindError`)
- **Type Hints:** Pydantic-style annotations using `Annotated[int, annotated_types.Gt(0)]`
- **Docstrings:** Google-style docstrings with Args/Returns/Raises sections
- **Naming:**
  - Private attributes: `_client`, `_msq`, `_com`
  - Protected methods: Single underscore prefix
  - Thread names: Descriptive (`TelnetProxy`, `AcceptService1`)

### **Testing/Deployment Patterns:**

- **Client Simulators:** Available in `clients/` directory for testing without hardware
- **System Service:** Install script + systemd unit file for production deployment
- **Cross-Platform:** Platform detection (`platform.system()`) for Linux/MacOS differences
- **Configuration:** INI format with comments explaining each option

---

## 🎯 Summary

The codebase is well-structured with clear separation of concerns:
- Network layer handles UDP/TCP communication
- Protocol layer (Analyser) parses Hargassner telnet protocol
- Integration layer exposes data via MQTT
- Configuration is centralized and extensible

**Remaining improvement areas:**
1. Configuration file handling for system service ⚠️ (not addressed)
2. Boiler error response handling ⚠️ (detection exists but not treated as failures)
3. Multi-version protocol support ⚠️ (not addressed)

**Completed improvements:**
1. ✅ Socket error handling with reconnection and retry logic (completed)
2. ✅ Extended boiler control parameters (dynamic discovery implemented - 6 parameters)
3. ✅ MQTT stability fixes (dual-loop bug resolved)
4. ✅ ha-mqtt-discoverable library upgraded to >=0.22.0
5. ✅ Bidirectional state synchronization via "track" channel (PR #8)

The code follows consistent patterns for threading, messaging, and MQTT integration, making it straightforward to extend with new features.

**Recent progress:**
- ✅ 2 out of 5 major development areas completed (Boiler Control, MQTT Stability)
- ✅ Dynamic parameter system now supports 9 parameters with extensibility (up from 6)
- ✅ Extended Zone 2 temperature monitoring (parameters 7, 8, A6d)
- ✅ Centralized parameter configuration in HargConfig.commands
- ✅ Logging optimizations to reduce production noise
- ✅ Bidirectional sync: Changes made via IGW/physical controls now reflected in Home Assistant
- ✅ Socket-level error handling with reconnection completed
- ⚠️ 3 areas remain: Configuration system, boiler error response handling, and multi-version support
