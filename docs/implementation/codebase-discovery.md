# Technical Discovery & Analysis - MyHargassner

## 📋 Technical Scope Summary

MyHargassner is a **Python-based gateway service** that sits between a Hargassner pellet boiler and its Internet Gateway (IGW), intercepts their communication, extracts telemetry data, and exposes it via MQTT for home automation integration (Home Assistant/Jeedom). The system also enables bidirectional control by sending commands back to the boiler through MQTT Select/Number entities.

---

## 🏗️ Codebase Architecture Analysis

### **Core Components Identified:**

1. **[myhargassner/main.py](myhargassner/main.py:85-113)** - Entry point that orchestrates all components
   - Initializes PubSub communication system
   - Starts 4 main threads: TelnetProxy, BoilerListener, GatewayListener, MqttInformer

2. **[myhargassner/appconfig.py](myhargassner/appconfig.py:11-197)** - Configuration management
   - Loads from `myhargassner.ini` file
   - Merges defaults → config file → CLI arguments
   - Provides typed accessors for network, MQTT, and logging settings

3. **[myhargassner/core.py](myhargassner/core.py:1-304)** - Base classes and abstractions
   - `NetworkData` - Stores IGW/boiler addresses/ports
   - `ChanelReceiver` - Base class for components receiving PubSub messages
   - `ListenerSender` - Abstract class for UDP listeners (Gateway/Boiler)

4. **Network Discovery Layer:**
   - **[myhargassner/gateway.py](myhargassner/gateway.py)** - Discovers IGW via UDP broadcasts
   - **[myhargassner/boiler.py](myhargassner/boiler.py)** - Discovers boiler via UDP broadcasts
   - Both publish discovery info to `bootstrap` channel

5. **Communication Layer:**
   - **[myhargassner/telnetproxy.py](myhargassner/telnetproxy.py:181-704)** - Core proxy component
     - Runs 2 telnet services (port 23 for IGW, port 4000 for commands)
     - Uses `select()` to multiplex between IGW, boiler, and command sockets
     - Implements reconnection/restart logic for each service
   - **[myhargassner/analyser.py](myhargassner/analyser.py:16-337)** - Protocol parser
     - Parses telnet requests/responses between IGW and boiler
     - Extracts boiler parameters from `pm` buffers (sent every second)
     - Publishes extracted data to `info` channel

6. **MQTT Integration Layer:**
   - **[myhargassner/mqtt_base.py](myhargassner/mqtt_base.py)** - Base MQTT functionality
   - **[myhargassner/mqtt_informer.py](myhargassner/mqtt_informer.py:61-230)** - Telemetry publisher
     - Creates Home Assistant MQTT Discovery device
     - Creates sensors for ~30 boiler parameters (temps, states, etc.)
     - Updates sensor states when values change
   - **[myhargassner/mqtt_actuator.py](myhargassner/mqtt_actuator.py:27-743)** - Command handler
     - Creates MQTT Select entities for boiler modes (Boiler, Zone 1, Zone 2)
     - Creates MQTT Number entities for temperature setpoints
     - Sends `$par set` commands to boiler via port 4000
     - Parses responses to confirm state changes

7. **Supporting Modules:**
   - **[myhargassner/hargconfig.py](myhargassner/hargconfig.py:5-150)** - Boiler parameter definitions
     - Maps 180+ telemetry parameters (c0-c180) to names/units/descriptions
     - Configurable `wanted` list for selective monitoring
   - **[myhargassner/socket_manager.py](myhargassner/socket_manager.py)** - Cross-platform socket handling (Linux/MacOS)
   - **[myhargassner/telnethelper.py](myhargassner/telnethelper.py)** - Telnet client utilities
   - **[myhargassner/pubsub/](myhargassner/pubsub/)** - Internal message bus (from Thierry Maillard)

---

## 🔍 Key Areas for Development Work

Based on the README's known limitations and the architecture:

### **1. Configuration System** ([appconfig.py](myhargassner/appconfig.py))
- **Current:** Hard-coded path to `myhargassner.ini` in current working directory
- **Issue:** When running as systemd service, config location is unclear
- **Work needed:**
  - Support config file path via CLI argument
  - Search standard locations (`/etc/myhargassner/`, `~/.config/`, etc.)
  - Validate required fields (especially MQTT password)

### **2. Error Handling** ([analyser.py](myhargassner/analyser.py:129-130), [telnetproxy.py](myhargassner/telnetproxy.py:641-644))
- **Current:** Basic logging, some "permission denied" warnings
- **Issue:** "todo: enhance management of error or permission denied responses"
- **Work needed:**
  - Robust error response parsing from boiler
  - Retry logic with backoff
  - User-friendly error reporting via MQTT

### **3. Boiler Control Expansion** ([mqtt_actuator.py](myhargassner/mqtt_actuator.py:392-399))
- **Current:** Only 3 parameters controlled (PR001, PR011, PR012)
- **Issue:** "todo: implement more controls of the boiler"
- **Work needed:**
  - Add more PRxxx parameters (PR040 for buffer, numeric temps, etc.)
  - Generic parameter discovery instead of hard-coding
  - Support for numeric setpoints (already partially implemented)

### **4. Software Version Support** ([README.md](README.md:16))
- **Current:** Only V14.0n3 tested
- **Issue:** "todo: today only Hargassner software version V14.0n3 is supported"
- **Work needed:**
  - Version detection from `$info` response
  - Version-specific protocol adjustments
  - Compatibility matrix documentation

### **5. Struct Exception Bug** ([README.md](README.md:14))
- **Current:** "bug: sometimes a struct.unpack() exception is raised in paho-mqtt"
- **Work needed:**
  - Investigate paho-mqtt integration in [mqtt_informer.py](myhargassner/mqtt_informer.py) and [mqtt_actuator.py](myhargassner/mqtt_actuator.py)
  - Add exception handling around MQTT operations
  - Review payload encoding/decoding (latin1 vs utf-8)

---

## 📐 Existing Patterns and Conventions

### **Architecture Patterns:**

1. **Threading Model**
   - Dedicated thread per major component (TelnetProxy, Boiler, Gateway, MQTT)
   - Pattern: `Threaded<T>` wrapper class (see [mqtt_actuator.py:669-743](myhargassner/mqtt_actuator.py:669-743))
   - Example: `ThreadedTelnetProxy`, `ThreadedBoilerListenerSender`

2. **PubSub Communication**
   - Internal message bus with named channels (`bootstrap`, `info`)
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

**Key improvement areas** align with the README todos:
1. Configuration file handling for system service
2. Error response parsing and handling
3. Extended boiler control parameters
4. Multi-version protocol support
5. MQTT stability fixes

The code follows consistent patterns for threading, messaging, and MQTT integration, making it straightforward to extend with new features.
