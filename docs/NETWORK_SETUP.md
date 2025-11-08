# Network Setup Guide

This guide covers the network configuration required for MyHargassner to operate as a relay between the Hargassner Internet Gateway (IGW) and the pellet boiler.

## Architecture Overview

MyHargassner must be deployed on a Raspberry Pi positioned between the IGW and the boiler (typically a Nano.PK). It establishes connections with both devices and acts as a relay, intercepting and analyzing their communication.

**Important:** The IGW and the pellet boiler **must** be on separate network interfaces connected to your Raspberry Pi.

### Typical Setup

- **eth0** (Primary interface): Connected to your home network/router (same network as the IGW)
- **eth1** (Secondary interface): Connected directly to the pellet boiler via Ethernet cable (can be a USB-to-Ethernet adapter)

## Prerequisites

- Raspberry Pi with Raspberry Pi OS
- Two network interfaces (built-in + USB Ethernet adapter)
- Direct Ethernet cable connection to the pellet boiler
- The pellet boiler and IGW should NOT be on the same physical network

## Step-by-Step Configuration

### 1. Install DHCP Server

The secondary interface (eth1) needs to provide DHCP service to the boiler:

```bash
sudo apt-get install dnsmasq
```

### 2. Configure Static IP for eth1

Using Network Manager:

```bash
sudo nmcli con add type ethernet ifname eth1 con-name eth1-static ipv4.method manual ipv4.addresses 10.0.0.1/24 ipv4.gateway ""
sudo nmcli con mod eth1-static ipv4.dns ""
sudo nmcli con up eth1-static
```

### 3. Configure DHCP Server

Edit the dnsmasq configuration:

```bash
sudo nano /etc/dnsmasq.conf
```

Add the following lines:

```
interface=eth1
port=0
dhcp-range=10.0.0.10,10.0.0.99,24h
dhcp-authoritative
```

**Configuration explanation:**
- `interface=eth1` - Only serve DHCP on eth1
- `port=0` - Disable DNS service (we only need DHCP)
- `dhcp-range=...` - Assign IPs from 10.0.0.10 to 10.0.0.99 with 24-hour lease
- `dhcp-authoritative` - Be authoritative for this network

### 4. Apply Changes

Reboot the Raspberry Pi to apply all network changes:

```bash
sudo reboot
```

## Verification

### Check eth1 Configuration

After reboot, verify the eth1 interface has the correct IP:

```bash
ifconfig eth1
```

Expected output:
```
eth1: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
inet 10.0.0.1  netmask 255.255.255.0  broadcast 10.0.0.255
```

### Check Routing Table

Verify the routing table is correct:

```bash
route
```

Expected output (example):
```
Kernel IP routing table
Destination     Gateway         Genmask         Flags Metric Ref    Use Iface
default         box             0.0.0.0         UG    1002   0        0 eth0
10.0.0.0        0.0.0.0         255.0.0.0       U     1003   0        0 eth1
192.168.100.0   0.0.0.0         255.255.255.0   U     1002   0        0 eth0
```

**Key points:**
- `10.0.0.0` network is on eth1 (for the boiler)
- `192.168.100.0` (or your home network) is on eth0
- Default gateway goes through eth0

### Verify DHCP Lease

After connecting the boiler and allowing it to boot, check the DHCP lease:

```bash
cat /var/lib/misc/dnsmasq.leases
```

Expected output (example):
```
1724017448 00:24:bd:04:3f:6c 10.0.0.72 HSV1 01:00:24:bd:04:3f:6c
```

This shows the boiler has successfully obtained an IP address from the DHCP server.

## Troubleshooting

### eth1 Interface Not Active

The secondary interface (eth1) will only be active when the Ethernet cable is physically connected to the boiler. If the interface shows as DOWN, check:

1. Cable is properly connected to both the Raspberry Pi and the boiler
2. The boiler is powered on
3. Try rebooting both the Raspberry Pi and the boiler

### Boiler Not Getting IP Address

If the boiler doesn't appear in the DHCP leases:

1. Check dnsmasq is running: `systemctl status dnsmasq`
2. Check dnsmasq logs: `journalctl -u dnsmasq -n 50`
3. Verify eth1 configuration: `ip addr show eth1`
4. Restart dnsmasq: `sudo systemctl restart dnsmasq`

### Network Conflicts

If you experience routing issues:

1. Ensure the boiler network (10.0.0.0/24) doesn't conflict with your home network
2. Verify the IGW is on the home network (eth0), not directly connected to eth1
3. Check firewall rules aren't blocking traffic: `sudo iptables -L`

## Advanced Configuration

### Using Different IP Ranges

If 10.0.0.0/24 conflicts with your network, you can use a different range:

1. Update nmcli command with new IP (e.g., 192.168.99.1/24)
2. Update dnsmasq.conf with new range (e.g., 192.168.99.10-192.168.99.99)
3. Reboot and verify

### Multiple Network Interfaces

If you have more than two interfaces, ensure:
- Primary interface (connected to home network) is correctly specified in `myhargassner.ini` (gw_iface)
- Secondary interface (connected to boiler) is correctly specified in `myhargassner.ini` (bl_iface)

See the main [README.md](../README.md) for configuration file details.

## Security Considerations

- The boiler network (eth1) is isolated from your home network by default
- No routing between eth1 and eth0 is configured (no IP forwarding)
- MyHargassner application acts as an application-level relay only
- DHCP server only responds on eth1 interface

## Next Steps

Once network setup is complete:

1. Return to [README.md](../README.md) to complete MyHargassner installation
2. Configure `myhargassner.ini` with correct interface names
3. Test the application: `sudo -E env -S PATH=$PATH python3 -m myhargassner.main`
