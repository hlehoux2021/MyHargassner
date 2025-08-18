# HARG (Hargassner Gateway)

## Summary
HARG is a Python-based gateway project designed to interface with Hargassner pellet boilers. It acts as a bridge between the boiler's network communication and MQTT, enabling integration with home automation systems like Home Assistant. The project reuses and builds upon the work of [Jahislove](https://github.com/Jahislove/Hargassner/tree/master) and uses the PubSub library from [Thierry Maillard](https://github.com/Thierry46/pubsub).

## Setup

### Prerequisites
- Raspberry Pi with Raspberry Pi OS
- Two network interfaces:
  - Primary interface (`eth0`) connected to your router (same network as the Hargassner IGW internet gateway)
  - Secondary interface (`eth1`) connected directly to the pellet boiler (typically a Nano.PK)
    - Can be a USB-to-Ethernet adapter
- MQTT broker (configuration in `hargconfig.py`)
- DHCP server for the boiler network (instructions below)

### Network Setup on Raspberry Pi

1. **Install DHCP Server**
   ```bash
   sudo apt-get install dhcpcd
   sudo apt-get install dnsmasq
   ```

2. **Configure Static IP for eth1**
   Edit `/etc/dhcpcd.conf`:
   ```bash
   sudo nano /etc/dhcpcd.conf
   ```
   Add the following:
   ```
   interface eth1
   static ip_address=10.0.0.1
   static routers=10.0.0.1
   nogateway
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
- Main packages:
  - `paho-mqtt`: MQTT client library
  - `ha-mqtt-discoverable`: Home Assistant MQTT discovery integration
  - `pydantic`: Data validation using Python type annotations
  - `annotated_types`: Support for annotated type hints
- Dependencies automatically installed with the above:
  - `typing`
  - `logging`
  - `threading`
  - `socket`
  - `queue`
  - `argparse`
  - `platform`

To install the required packages:
```bash
pip install paho-mqtt ha-mqtt-discoverable pydantic annotated_types
```

### Installation
1. Clone the repository
2. Configure the network interfaces in `main.py`:
   ```python
   GW_IFACE = b'eth0'  # network interface connected to the gateway
   BL_IFACE = b'eth1'  # network interface connected to the boiler
   UDP_PORT = 35601    # destination port to which gateway is broadcasting
   ```
3. Update MQTT settings in `hargconfig.py` with your broker details

## Architecture

The project uses a multi-threaded architecture with several key components:

### Core Components
1. **Gateway Listener/Sender** (`ThreadedGatewayListenerSender`)
   - Listens for IGW internet gateway UDP broadcasts and forwards them to the pellet boiler
   - Forwards information to MQTT Informer
   - Discovers IGW and publishes its address/port to "bootstrap" channel to be used by other components

2. **Boiler Listener/Sender** (`ThreadedBoilerListenerSender`)
   - waits for the IGW network address and port to be published (by the gateway listener)
   - Listens for boiler UDP responses and forwards them back to the IGW
   - Discovers boiler and publishes its address/port to "bootstrap" channel to be used by other components

3. **Telnet Proxy** (`ThreadedTelnetProxy`)
   - waits for the boiler address and port to be discovered (by the boiler listener) 
   - Handles Telnet requests from IGW and forwards them to the pellet boiler
   - Handles Telnet responses from the pellet boiler and forwards them to IGW 
   - Handles Telnet requests from internal components, forwards them to boiler and provide replies to internal component
   - requests the pellet boiler configuration (Modes for the boiler or from different zones) from the boiler 
        sends a "$par get changed " telnet request to the pellet boiler
        publishes the pellet boiler response to the "info" channel"
   - Creates an MqttActuator component as soon as the pellet boiler is discovered
   - requests Analyser() class to analyse telnet requests and responses

4. **Analyser**
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

### Main Settings (`main.py`)
- `LOG_PATH`: Path for log files
- `LOG_LEVEL`: Logging level (DEBUG, INFO, etc.)
- `SOCKET_TIMEOUT`: Socket timeout value
- `BUFF_SIZE`: Buffer size for network operations
- Network interface settings:
  - `GW_IFACE`: Gateway interface
  - `BL_IFACE`: Boiler interface
  - `UDP_PORT`: UDP port

### MQTT Configuration (`hargconfig.py`)
- MQTT broker settings:
  - Host
  - Port
  - Username/Password
  - Other MQTT-specific configurations

### Boiler Parameters
The `hargconfig.py` file contains extensive mapping of boiler parameters including:
- Temperature readings
- System states
- Performance metrics
- Operating hours
- Error codes

You can customize which parameters to monitor by modifying the `wanted` list in `HargConfig` class.