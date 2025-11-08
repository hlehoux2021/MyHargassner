# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024

### Added

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

- **Dependency Management**
  - Migrated from `requirements.txt` to `pyproject.toml` as single source of truth for dependencies (commit 3dc8787)
  - Upgraded `ha-mqtt-discoverable` from 0.20.1 to >=0.22.0 for improved features and compatibility
  - Updated dependency descriptions for better clarity

### Fixed

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
