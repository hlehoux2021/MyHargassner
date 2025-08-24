# MyHargassner (Hargassner Gateway to MQTT)

## Summary
MyHargassner is a Python-based  project designed to interface with Hargassner pellet boilers. It acts as a bridge between the boiler's network communication and MQTT, enabling integration with home automation systems like Jeedom or Home Assistant. The project reuses and builds upon the work of [Jahislove](https://github.com/Jahislove/Hargassner/tree/master) and uses the PubSub library from [Thierry Maillard](https://github.com/Thierry46/pubsub).

## Disclaimer
This is a hobby project, provided free and as-is. There is no professional support included
I work on this project when i have time, mainly during summer holidays
I'm a beginner python programmer, be kind with my errors

## known limitations and bugs
- many, many !
- todo: implement a configuration file when installed as a system service
- bug: sometimes a "struct.unpack() excpetion is raised in paho-mqtt
- limit: when you use the project, the information in the IGW, and on the Hargassner App is not updated with what you do
- todo: today only Hargassner software version V14.0n3 is supported
- todo: implement more controls of the boiler (today only Boiler mode, and Zone 1 & 2 Mode)
- todo: enhance management of "error" or "permission denied" responses from the boiler

## Setup

### Prerequisites
- An Hargassner pellet boiler (typically a NanoPK), *and* the internet gateway (IGW) from the vendor
- Raspberry Pi with Raspberry Pi OS
- Two network interfaces:
  - Primary interface (`eth0`) connected to your router (same network as the Hargassner IGW internet gateway)
  - Secondary interface (`eth1`) connected directly to the pellet boiler (typically a Nano.PK)
    - Can be a USB-to-Ethernet adapter
- MQTT broker (configuration in `hargconfig.py`)
- DHCP server for the boiler network (instructions below)

### Network Setup on Raspberry Pi
The project relies on being deployed on a Raspberry PI between the IGW and the NanoPK. 
I will establish connections with both and act as a relay between them, while getting necessary information.
The IGW and the NanoPK *must* be on seperate network interfaces connected to your Raspberry

Typically, your PI will be on the home network connected (through eth0) to your router, like the IGW.
The pellet boiler will be connected directly to your Raspberry (through a second ethernet card on eth1)

1. **Install DHCP Server**
   ```bash
   sudo apt-get install dnsmasq
   ```

2. **Configure Static IP for eth1**
   Using Network Manager
   ```
   sudo nmcli con add type ethernet ifname eth1 con-name eth1-static ipv4.method manual ipv4.addresses 10.0.0.1/24 ipv4.gateway ""
   sudo nmcli con mod eth1-static ipv4.dns ""
   sudo nmcli con up eth1-static

   ```

3. **Configure DHCP Server**
   Edit `/etc/dnsmasq.conf`:
   ```bash
   sudo nano /etc/dnsmasq.conf
   ```
   Add the following:
   ```
   interface=eth1
   port=0
   dhcp-range=10.0.0.10,10.0.0.99,24h
   dhcp-authoritative
   ```

4. **Apply Changes**
   ```bash
   sudo reboot
   ```

5. **Verify Setup**
   - Check network interfaces:
     ```bash
     ifconfig eth1
     ```
     Should show:
     ```
     eth1: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
     inet 10.0.0.1  netmask 255.255.255.0  broadcast 10.0.0.255
     ```
   - Check routing table:
     ```bash
     route
     ```
     Should show a routing table comparable with the following:
     ```
    Kernel IP routing table
    Destination     Gateway         Genmask         Flags Metric Ref    Use Iface
    default         box             0.0.0.0         UG    1002   0        0 eth0
    10.0.0.0        0.0.0.0         255.0.0.0       U     1003   0        0 eth1 // The network 10.0.0.0 on eth1 to service the pellet boiler
    192.168.100.0   0.0.0.0         255.255.255.0   U     1002   0        0 eth0 // The network of your internet router
     
     ```
   - Verify DHCP lease (after boiler connects):
     ```bash
     cat /var/lib/misc/dnsmasq.leases
     ```
     Should show the boiler's MAC address and assigned IP
     ```
     1724017448 00:24:bd:04:3f:6c 10.0.0.72 HSV1 01:00:24:bd:04:3f:6c
     ```
 
Note: The secondary interface (eth1) will only be active when the Ethernet cable is physically connected. You may need to reboot both the Raspberry Pi and the Nano.PK to establish the connection.

### Required Python Packages

Main dependencies (see `setup.py`):
- `paho-mqtt`
- `ha-mqtt-discoverable`
- `psutil`
- `pydantic`
- `annotated_types`

Install with:
```bash
pip install paho-mqtt ha-mqtt-discoverable psutil pydantic annotated_types
```

### Installation
1. Clone the repository:
   ```bash
   git clone --recurse-submodules https://github.com/hlehoux2021/MyHargassner.git
   cd MyHargassner
   ```

2. Install dependencies:
   ```bash
   pip install .
   # or, if you prefer:
   # pip install -r requirements.txt
   ```


3. Configure your system:
   - Edit `myhargassner.ini` for all network, MQTT, and logging settings. This file is the main configuration file for the application.
   - Optionally, edit `hargconfig.py` if you want to customize which boiler parameters are monitored (see the `wanted` list in `HargConfig`).

### Run the programm
   ```bash
   sudo -E env -S PATH=$PATH python3 -m myhargassner.main
   ```
The following command line arguments are accepted:
-g --GW_IFACE  Source interface
-b --BL_IFACE  Destination interface
-p --port      Source port
-d --debug     Enable debug logging
-i --info'     info logging level
-w --warning   warning logging level
-e --error     error logging level
-c --critical  critical logging level

### Setting up as a System Service

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

---


### File Structure

```
MyHargassner/
├── analyser.py
├── appconfig.py
├── boiler.py
├── clients/
│   ├── boiler-client-ai.py
│   ├── boiler-simple.py
│   ├── gateway-client-ai.py
│   ├── gateway-simple.py
│   └── shared_simulator.py
├── core.py
├── gateway.py
├── hargconfig.py
├── install_system_service.sh
├── main.py
├── mqtt_actuator.py
├── mqtt_base.py
├── mqtt_informer.py
├── myhargassner.service
├── myhargassner.ini         # Main configuration file (edit this for your setup)
├── parse.py
├── pubsub/
│   ├── __init__.py
│   ├── pubsub.py
│   └── tests/
│       ├── test_PubSub.py
│       ├── test_PubSub_load.py
│       └── test_pubsub_priority.py
├── pylintrc
├── README.md
├── setup.py
├── shared.py
├── socket_manager.py
├── telnethelper.py
├── telnetproxy.py
├── uninstall_system_service.sh
└── ...
```

**Note:**
- The `myhargassner.ini` file is the main configuration file. Copy and edit this file to match your environment.
- The `clients/` and `pubsub/tests/` folders contain example scripts and tests.
- Some files may be omitted above for brevity; see the repository for the full structure.
   - Analyses telnet requests from IGW and responses from pellet boiler (through the Analyser class) and pushes key information to the "info" channel
   - Analyses specific "pm ..." telnet buffer sent every second by pellet boiler,  maps it to valuable data and publishes it to the "info" channel


5. **MQTT Informer** (`MqttInformer`)
   - Receives data from other components on the "info" channel
   - Maintains a dictionary of pellet boiler information received (from TelnetProxy)
   - when key boiler information has been received (at least network addr), 
        creates a device info for the boiler and publishes it to MQTT for discovery
        creates Sensor information for each key mandatory information ("HargaWebApp", "Login Token" and "Login key")
        creates Sensor information for regular boiler data we want (configured in hargconfig.py)
   - when regular boiler data changes, publish it to MQTT

5. **MQTT Actuator** (`MqttActuator`)
   - waits for the pellet boiler configuration (Modes for the boiler and the different zones) to be published on the "info" channel
   - creates a Select MQTT subscriber for each Mode discovered
   -  implements a callback() thread for each Select
        when callback() received, implement a telnet command "$par set " and send it to the pellet boiler through TelnetProxy (internal)

## Configuration


### Main Settings (`myhargassner.ini`)
All main settings are configured in the `myhargassner.ini` file. Example:

```ini
[network]
gw_iface = eth0
bl_iface = eth1
udp_port = 35601
socket_timeout = 5
buff_size = 4096

[logging]
log_path = /var/log/myhargassner.log
log_level = INFO
```

See the comments in `myhargassner.ini` for more details on each option.


### MQTT Configuration (`myhargassner.ini`)
MQTT broker settings are also configured in the `myhargassner.ini` file:

```ini
[mqtt]
host = localhost
port = 1883
username = youruser
password = yourpassword
topic_prefix = myhargassner
```

You can override any of these values using command-line arguments if needed.

### Boiler Parameters
The `hargconfig.py` file contains extensive mapping of boiler parameters including:
- Temperature readings
- System states
- Performance metrics
- Operating hours
- Error codes

You can customize which parameters to monitor by modifying the `wanted` list in `HargConfig` class.
Please refer to https://github.com/Jahislove/Hargassner/tree/master for details on the parameters sent by the Hargassner pellet boiler

