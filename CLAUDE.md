# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MyHargassner is a Python-based gateway that bridges Hargassner pellet boilers with MQTT for home automation integration. It positions itself between the Hargassner Internet Gateway (IGW) and the pellet boiler (typically a Nano.PK), intercepting and analyzing their communication while providing MQTT-based control and monitoring.

## Development Commands

For user installation and setup instructions, see [README.md](README.md).

### Development Environment Setup

```bash
# Install in development mode with dev dependencies
pip install -e ".[dev]"
```

This installs the package in editable mode, allowing you to make changes without reinstalling.

### Running the Application

```bash
# Run directly from source (requires sudo for network interface access)
sudo -E env -S PATH=$PATH python3 -m myhargassner.main
```

For command-line arguments, see [README.md](README.md#4-run).

### Testing

```bash
# Run PubSub tests
python3 -m pytest myhargassner/pubsub/tests/

# Run specific test file
python3 -m pytest myhargassner/pubsub/tests/test_PubSub.py

# Use client simulators for testing without hardware
python3 clients/gateway-simple.py
python3 clients/boiler-simple.py
```

### Code Quality

```bash
# Run pylint on all Python files
python3 -m pylint myhargassner/

# Check specific file
python3 -m pylint myhargassner/main.py
```

### System Service Management

For production deployment as a systemd service, see [README.md](README.md#setting-up-as-a-system-service).

Quick reference:
```bash
systemctl status myhargassner                      # Check status
journalctl -u myhargassner.service -n 50 --no-pager  # View logs
sudo systemctl restart myhargassner                # Restart service
```

## Architecture

For detailed architecture documentation including component diagrams, class inheritance, PubSub channels, data flow examples, and restart orchestration, see [docs/TECHNICAL_ARCHITECTURE.md](docs/TECHNICAL_ARCHITECTURE.md).

### Quick Overview

MyHargassner uses a multi-threaded relay architecture with 5 main components:

1. **GatewayListenerSender** - Listens for IGW UDP broadcasts, relays to boiler
2. **BoilerListenerSender** - Listens for boiler UDP broadcasts, relays to IGW
3. **TelnetProxy** - Relays telnet communication, analyzes protocol
4. **MqttInformer** - Publishes boiler telemetry to MQTT
5. **MqttActuator** - Handles MQTT control commands

Components communicate via a PubSub message bus with 4 channels: `bootstrap`, `info`, `track`, `system`.

## Configuration

### Main Configuration File: myhargassner.ini

All network, MQTT, and logging settings are in `myhargassner.ini`:
- Network interfaces and ports
- MQTT broker settings (host, port, username, password)
- Logging configuration

Configuration is loaded via `AppConfig` class in `appconfig.py` which supports:
- INI file parsing
- Command-line argument overrides
- Environment variable support

### Boiler Parameters: hargconfig.py

`HargConfig` class defines:
- `wanted`: List of parameter IDs to monitor (e.g., 'c0', 'c3', 'TOKEN', 'KEY')
- `desc`: Dictionary mapping parameter IDs to human-readable descriptions and units
- `map`: Mapping between position in "pm" buffer and parameter names

Based on reverse engineering work from https://github.com/Jahislove/Hargassner

## Important Implementation Notes

### Socket Management

- Uses `SocketManager` class for platform-agnostic socket operations
- Implements custom exceptions: `HargSocketError`, `SocketBindError`, `InterfaceError`, `SocketTimeoutError`
- UDP sockets use `SO_BROADCAST` and `SO_REUSEADDR`
- Telnet uses standard TCP sockets with `select()` for non-blocking I/O

### Thread Safety

- All threaded components inherit from `threading.Thread`
- Use `ShutdownAware` mixin for coordinated shutdown
- PubSub queues handle inter-thread communication safely
- Avoid direct shared state between threads

### Error Handling

- Components should catch and log exceptions without crashing threads
- Use `try/except` blocks in main loops to allow recovery
- Socket errors trigger automatic reconnection with retry logic (up to 20 attempts)
- Boiler error responses (`$err`, `$permission denied`, `zERR`) are detected and logged but not yet properly handled as failures

### Telnet Protocol

The boiler uses a custom telnet protocol with commands like:
- `$login token` / `$login key` - Authentication
- `$daq desc` / `$daq start` - Data acquisition
- `$par get <param>` / `$par set "<param>;<value>"` - Parameter read/write
- `$info` - System information
- Response format: `$<response>` or `$ack`

See comments in `telnetproxy.py` for full command reference.

### MQTT Discovery

Uses Home Assistant MQTT Discovery protocol via `ha-mqtt-discoverable>=0.22.0`:
- Device info created with boiler IP as identifier
- Sensors created with unique_id format: `<param_id>/<boiler_ip>`
- Select entities for controllable parameters (mode parameters)
- Number entities for numeric setpoints (temperature, percentages)
- State updates published automatically
- Bidirectional state sync via "track" channel

## Known Limitations

- Only supports Hargassner software version V14.0n3 (tested version)
- Control limited to 6 parameters: PR001 (boiler mode), PR011 (zone 1), PR012 (zone 2), PR040 (buffer startup), parameter 4 (day temp), parameter 5 (reduced temp)

## Development Environment

- Python >= 3.8 required
- Uses `pyproject.toml` for modern Python packaging
- `setup.py` exists for backward compatibility
- Virtual environments recommended: `.venv/` directory
- Type hints used throughout codebase
- Pylint configuration in `pylintrc` with relaxed line length rules

## Code Style Conventions

### Encoding and Character Handling
- **Protocol encoding**: Use `latin1` for telnet protocol to handle special characters (é, ï, etc.)
- **String decoding**: When decoding bytes from telnet, use `latin1` to avoid UnicodeDecodeError

### Naming Conventions
- **Private attributes**: Prefix with single underscore (e.g., `_client`, `_msq`, `_com`)
- **Protected methods**: Single underscore prefix
- **Thread names**: Use descriptive names (e.g., `TelnetProxy`, `AcceptService1`)
- **Thread wrapper classes**: Pattern `Threaded<ComponentName>` (e.g., `ThreadedTelnetProxy`)

### Type Annotations
- Use Pydantic-style annotations with `annotated_types`:
  ```python
  port: Annotated[int, annotated_types.Gt(0)]
  addr: Annotated[bytes, annotated_types.MaxLen(15)]
  ```

### Docstrings and Logging
- Use Google-style docstrings with Args/Returns/Raises sections
- Extensive debug logging with `logging.debug()` throughout for troubleshooting
- Error handling: Use try/except with logging, raise specific custom exceptions

### Threading Patterns
- All threaded components inherit from `threading.Thread`
- Use `ShutdownAware` mixin for graceful shutdown
- Pattern: Create wrapper class `Threaded<T>` that manages the thread lifecycle
- Example: `ThreadedTelnetProxy`, `ThreadedMqttInformer`

## Testing Strategy

- PubSub library has comprehensive tests in `myhargassner/pubsub/tests/`
- Test load scenarios and priority queues
- Run tests with pytest
- Main application components lack unit tests - integration testing done via system service
- **Client simulators** available in `clients/` directory for testing without physical hardware:
  - `gateway-simple.py` - Simulates IGW behavior
  - `boiler-simple.py` - Simulates boiler behavior
  - `gateway-client-ai.py` / `boiler-client-ai.py` - Advanced simulators

## Areas for Improvement

For detailed status tracking of development work, see [docs/TECHNICAL_ARCHITECTURE.md](docs/TECHNICAL_ARCHITECTURE.md).

For user-facing version history and recent changes, see [docs/CHANGELOG.md](docs/CHANGELOG.md).

Key areas identified for future development:

1. **Configuration System**
   - Support config file path via CLI argument
   - Search standard locations (`/etc/myhargassner/`, `~/.config/`)
   - Better validation of required fields

2. **Error Handling**
   - Properly handle boiler error responses (`$err`, `$permission denied`, `zERR`) - currently detected but not treated as failures
   - User-friendly error reporting via MQTT (expose error states as sensors)

3. **Boiler Control Expansion**
   - Add more PRxxx parameters beyond current 6 (PR001, PR011, PR012, PR040, 4, 5)
   - Implement automatic parameter discovery from `$daq desc` response
   - Support for additional numeric setpoints as needed by users

4. **Software Version Support**
   - Version detection from `$info` response
   - Version-specific protocol adjustments
   - Compatibility matrix documentation

5. **Testing and Documentation**
   - Add unit tests for main application components (currently only PubSub has tests)
   - Test with additional firmware versions beyond V14.0n3
   - Document compatibility matrix for different boiler models and firmware versions
