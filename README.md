# MyHargassner

> **Hargassner Pellet Boiler Gateway to MQTT for Home Automation**

MyHargassner is a Python-based gateway that bridges Hargassner pellet boilers with MQTT, enabling seamless integration with home automation systems like Home Assistant and Jeedom. It intercepts communication between the Hargassner Internet Gateway (IGW) and the boiler, extracting telemetry data and enabling bidirectional control.

## Features

- **Network Relay Architecture**: Acts as transparent relay between IGW and boiler
- **MQTT Integration**: Full Home Assistant MQTT Discovery support
- **Bidirectional Control**: Control boiler from Home Assistant, changes reflected in Hargassner App
- **Real-time Telemetry**: ~30 sensor values (temperatures, states, performance metrics)
- **Controllable Parameters**: 6 parameters including boiler mode, zone modes, and temperature setpoints
- **Automatic Discovery**: Dynamic parameter discovery system

## Quick Links

- 📋 [Changelog](docs/CHANGELOG.md) - Version history and recent changes
- 🔧 [Network Setup Guide](docs/NETWORK_SETUP.md) - Detailed network configuration
- 🩺 [Troubleshooting](docs/TROUBLESHOOTING.md) - Diagnostic commands (e.g. IGW stuck after `$igw clear`)
- 🐛 [Bug Tracker](https://github.com/hlehoux2021/MyHargassner/issues) - Report issues and request features
- 📖 [Architecture Details](CLAUDE.md) - Technical architecture and development guide

## Known Limitations

- Only Hargassner software version V14.0n3 is currently tested
- Control limited to 6 parameters (PR001, PR011, PR012, PR040, parameter 4, parameter 5)

See [CHANGELOG.md](docs/CHANGELOG.md) for planned features and recent improvements.

## Disclaimer

This is a hobby project, provided free and as-is. There is no professional support included. I work on this project when I have time, mainly during summer holidays. I'm a beginner Python programmer - be kind with my errors!

## Credits

- Based on reverse engineering work by [Jahislove](https://github.com/Jahislove/Hargassner/tree/master)
- Uses PubSub library from [Thierry Maillard](https://github.com/Thierry46/pubsub)

---

## Installation

### Prerequisites

**Hardware:**
- Hargassner pellet boiler (typically a Nano.PK)
- Hargassner Internet Gateway (IGW)
- Raspberry Pi with Raspberry Pi OS
- Two network interfaces (built-in + USB Ethernet adapter)

**Software:**
- Python >= 3.8
- MQTT broker (Mosquitto, Home Assistant's built-in broker, etc.)

**Dependencies:**

This project uses `pyproject.toml` for dependency management. All required dependencies will be automatically installed:
- `paho-mqtt>=2.1.0` - MQTT client library
- `ha-mqtt-discoverable>=0.22.0` - Home Assistant MQTT discovery integration
- `psutil>=7.0.0` - System and process utilities
- `pydantic>=2.11.7` - Data validation using Python type annotations
- `annotated_types>=0.7.0` - Type annotation support

**Network Architecture:**

MyHargassner must sit between the IGW and the boiler on separate network interfaces:
- **eth0**: Connected to home network (same network as IGW)
- **eth1**: Direct connection to boiler (dedicated network with DHCP server)

⚠️ **Important:** The IGW and boiler must be on **separate physical networks**.

📖 **See [Network Setup Guide](docs/NETWORK_SETUP.md) for detailed configuration instructions.**

### Step 1: Network Setup

Complete the network configuration first before installing MyHargassner.

Follow the [Network Setup Guide](docs/NETWORK_SETUP.md) to:
- Configure static IP on eth1
- Install and configure DHCP server
- Verify network connectivity

### Step 2: Install MyHargassner

Clone the repository:
```bash
git clone --recurse-submodules https://github.com/hlehoux2021/MyHargassner.git
cd MyHargassner
```

Install the package:
```bash
sudo pip install --break-system-packages .
```

### Step 3: Configure

Edit `myhargassner.ini` to configure:
- Network interfaces (gw_iface, bl_iface)
- MQTT broker settings (host, port, credentials)
- Logging preferences

Optionally, edit `hargconfig.py` to customize which boiler parameters are monitored (see the `wanted` list in `HargConfig`).

### Step 4: Run

Test the application:
```bash
sudo -E env -S PATH=$PATH python3 -m myhargassner.main
```

**Command-line Arguments:**

Every option of `myhargassner.ini` (except the MQTT password) can be overridden with `--<option> <value>`:
- `--gw_iface` - Interface connected to the IGW (gateway side), e.g. `eth0`
- `--bl_iface` - Interface connected to the boiler, by name (`eth1`) or by IP address (`10.0.0.1`)
- `--udp_port`, `--socket_timeout`, `--buff_size` - Network settings
- `--host`, `--port`, `--username`, `--topic_prefix` - MQTT settings (`--port` is the MQTT broker port)
- `--log_path`, `--log_level` - Logging settings, e.g. `--log_level DEBUG`
- `--loop_timeout`, `--queue_timeout`, `--retry_delay`, `--service_lock_delay` - Timeouts (seconds)

The `-d/--debug`, `-i/--info`, `-w/--warning`, `-e/--error` and `-c/--critical` flags are accepted but currently have no effect: use `--log_level` instead.

### Step 5: Setting up as a System Service (Optional)

You can install and run the gateway as a systemd service using the provided bash script. This will copy the project to `/etc/myhargassner`, install the Python package system-wide, and set up the service to start on boot.

1. Edit `myhargassner.service` if you need to customize the service (default runs as root and uses `/usr/local/bin/myhargassner`).
2. Run the install script as root:
   ```bash
   sudo bash install_system_service.sh
   ```
3. The script will:
   - Copy all project files to `/etc/myhargassner`
   - Install the Python package system-wide
   - Copy the systemd service file to `/etc/systemd/system/`
   - Reload systemd, enable, and start the service

4. To check the service status:
   ```bash
   systemctl status myhargassner
   ```
5. To stop or restart:
   ```bash
   sudo systemctl stop myhargassner
   sudo systemctl restart myhargassner
   ```

To uninstall, use the provided `uninstall_system_service.sh` script.

To debug problems, use:
```bash
journalctl -u myhargassner.service -n 50 --no-pager
```

For more diagnostic commands, see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

---

## Configuration

### Main Configuration File

Edit `myhargassner.ini` to configure all settings:

**Network Settings:**
```ini
[network]
gw_iface = eth0           # Interface connected to IGW (home network)
bl_iface = eth1           # Interface connected to boiler (name, or its IP address e.g. 10.0.0.1)
udp_port = 35601
socket_timeout = 5
buff_size = 4096
```

**MQTT Settings:**
```ini
[mqtt]
host = localhost          # MQTT broker hostname/IP
port = 1883
username = youruser
password = yourpassword
topic_prefix = myhargassner
```

**Logging Settings:**
```ini
[logging]
log_path = /var/log/myhargassner.log
log_level = INFO
```

See comments in `myhargassner.ini` for all available options.

### Boiler Parameters

The `hargconfig.py` file contains mappings for 180+ boiler parameters (temperatures, states, performance metrics, operating hours, error codes).

Customize which parameters to monitor by editing the `wanted` list in the `HargConfig` class.

For parameter details, see [Jahislove's reverse engineering work](https://github.com/Jahislove/Hargassner/tree/master).

---

## Architecture

MyHargassner uses a multi-threaded relay architecture with 5 main components:

1. **GatewayListenerSender** - Listens for IGW UDP broadcasts, relays to boiler
2. **BoilerListenerSender** - Listens for boiler UDP broadcasts, relays to IGW
3. **TelnetProxy** - Relays telnet communication, analyzes protocol
4. **MqttInformer** - Publishes boiler telemetry to MQTT
5. **MqttActuator** - Handles MQTT control commands

Components communicate via a PubSub message bus with 4 channels: `bootstrap`, `info`, `track`, `system`.

For detailed architecture information including class inheritance, data flow diagrams, and implementation details, see [docs/TECHNICAL_ARCHITECTURE.md](docs/TECHNICAL_ARCHITECTURE.md).

