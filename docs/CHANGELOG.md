# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **IGW blocked after `$igw clear`** - After the in-process restart, the IGW kept sending `get services` every 20 s without ever receiving the boiler reply (branch fix-igw-clear)
  - The boiler replies by unicast to the port the request came from, which is shared by the gateway resender and the boiler listener. The resender is now connected to `<broadcast>`, so the kernel never delivers anything to it and replies always reach the boiler listener
  - The first packet is relayed to the boiler only once the boiler listener is bound (the boiler replies within a few ms)
  - UDP sockets use `SO_REUSEADDR` instead of `SO_REUSEPORT` on Linux, which load-balanced unicast datagrams between sockets sharing a port
  - All sockets are closed explicitly at the end of a session: UDP sockets, telnet listening sockets (ports 23 and 4000), MqttInformer MQTT clients
  - Telnet `accept()` no longer blocks forever, and TelnetProxy no longer binds its ports when shutdown is requested during discovery
- **bl_iface** - Can be set either to the interface name (`eth1`) or to its IP address (`10.0.0.1`), with the same socket configuration (`SO_BINDTODEVICE` always applied on Linux)

## [1.0.0] - 2024

### Added

- **Issue #5** - Upgraded ha-mqtt-discoverable from 0.20.1 to >=0.22.0 (PR #10, merged 2025-11-08)
  - Removed deprecated user-data usage in callbacks
  - Migrated to modern callback approach without user_data parameter
  - Improved compatibility with latest ha-mqtt-discoverable features
- **Claude Code GitHub Integration** - Added GitHub Actions workflow for AI-assisted development (PR #9, merged 2025-11-07)
  - Enables @claude mentions in PR and issue comments
  - Automated code reviews, bug fixes, and improvements
  - Secure integration with repository access controls
- **Issue #7** - Added pubsub communication between telnetproxy/analyser and mqtt_actuator (feature-007 branch, PR #8)
  - Implemented subscribe and unsubscribe functionality
  - Added "track" channel with dedicated queue for internal communication
  - Enhanced handling of numeric parameters in `_handle_message`
  - Improved MQTT client reconnect handling
- **Bidirectional communication** - Added relay of changes back to IGW, enabling real-time updates in the Hargassner App when making changes through MQTT (commit 04557c5)
- Support for 6 controllable parameters:
  - PR001 (boiler mode)
  - PR011 (zone 1 mode)
  - PR012 (zone 2 mode)
  - PR040 (buffer startup)
  - Parameter 4 (day temperature)
  - Parameter 5 (reduced temperature)
- Dynamic parameter discovery system - no longer hardcoded
- MQTT Number entities for numeric setpoints (temperature, percentages)

### Changed

- **Dependency Management** (PR #10)
  - Migrated from `requirements.txt` to `pyproject.toml` as single source of truth for dependencies (commit 3dc8787)
  - Updated dependency descriptions for better clarity
- **Documentation** (PR #10)
  - Reorganized and updated project documentation
  - Updated README to reflect recent changes, evolutions, and bug fixes

### Fixed

- **Boiler Discovery** - Fixed incorrect validation check in `_boiler-config` discovery process (PR #10, commit 3af5d58)
- **Issue #2** - Fixed critical `struct.error` crash in paho-mqtt caused by MQTT dual-loop race condition (PR #3, commit 3714075)
  - Removed redundant `client.loop()` call from MainThread
  - Rely solely on ha-mqtt-discoverable's background thread
- **Issue #1** - Fixed mishandling of `$dhcp renew` and `$igw clear` commands (commits 3822d8c and a52c019)
- **Issue #4** - Resolved via PR #6
- **Issue #7** - Enhanced error handling on sockets (commits ba00390, f4c7ab8)
- Fixed import errors and corrected requirements dependencies (commit ffd2c61)
- Fixed `parse_parameter_response` function (commit 9cdf3a9)

### Improved

- **Code Quality**
  - Removed pylint warnings across the codebase (commit 5af3d00)
  - Improved logging: moved verbose output to debug level for cleaner production logs
  - Added comprehensive debug logging for troubleshooting
  - Enhanced error handling throughout the application

## Known Issues

See [GitHub Issues](https://github.com/hlehoux2021/MyHargassner/issues) for current bugs and feature requests.

## Planned Features

- Implement more controls for the boiler beyond current 6 parameters
- Additional software version support beyond V14.0n3
- Automatic parameter discovery from `$daq desc` response

[1.0.0]: https://github.com/hlehoux2021/MyHargassner/releases/tag/v1.0.0
