#!/usr/bin/env python3

import socket
import time
import threading
import re

# Add socket constants that might not be defined on all systems
if not hasattr(socket, 'SO_BINDTODEVICE'):
    socket.SO_BINDTODEVICE = 25  # From Linux <socket.h>
if not hasattr(socket, 'IP_BOUND_IF'):
    socket.IP_BOUND_IF = 25  # From macOS <netinet/in.h>

class SharedSimulator:
    """Base class for Hargassner device simulators with common networking functionality"""

    # Define the unified command patterns, messages, responses and delays
    commands = [
        # Login sequence
        {
            'pattern': r'^\$login token\r\n?$',
            'send_msg': b"$login token\r\n",
            'response': b"$3313C1F2\r\n",
            'expect_pattern': r"\$3313C1",
            'delay': 0.1
        },
        {
            'pattern': r'^\$login key .*\r\n?$',
            'send_msg': b"$login key 3313C1\r\n",
            'response': b"zclient login (7421)\r\n$ack\r\n",
            'expect_pattern': r"zclient login",
            'delay': 0.1
        },
        
        # API and setup
        {
            'pattern': r'^\$apiversion\r\n?$',
            'send_msg': b"$apiversion\r\n",
            'response': b"$1.0.1\r\n",
            'expect_pattern': r"\$1\.0",
            'delay': 0.1
        },
        {
            'pattern': r'^\$setkomm\r\n?$',
            'send_msg': b"$setkomm\r\n",
            'response': b"$2225410 ack\r\n",
            'expect_pattern': r"\$2225410",
            'delay': 0.1
        },
        {
            'pattern': r'^\$asnr get\r\n?$',
            'send_msg': b"$asnr get\r\n",
            'response': b"$\r\n",
            'expect_pattern': r"\$.*",
            'delay': 0.1
        },
        {
            'pattern': r'^\$igw set \d+\r\n?$',
            'send_msg': b"$igw set 0039808\r\n",
            'response': b"$ack\r\n",
            'expect_pattern': r"ack",
            'delay': 0.1
        },
        
        # DAQ commands
        {
            'pattern': r'^\$daq stop\r\n?$',
            'send_msg': b"$daq stop\r\n",
            'response': b"$daq stopped\r\n",
            'expect_pattern': r"\$daq stopped",
            'delay': 0.1
        },
        {
            'pattern': r'^\$daq start\r\n?$',
            'send_msg': b"$daq start\r\n",
            'response': b"$daq started\r\n",
            'expect_pattern': r"\$daq started",
            'delay': 0.1
        },
        {
            'pattern': r'^\$daq desc\r\n?$',
            'send_msg': b"$daq desc\r\n",
            'response': b"$<<<DAQPRJ><ANALOG>"
                       b"<CHANNEL id='0' name='ZK' dop='0'/>"
                       b"<CHANNEL id='1' name='O2' unit='%'/>"
                       b"<CHANNEL id='2' name='O2soll' unit='%'/>"
                       b"<CHANNEL id='3' name='TK' unit='C'/>"
                       b">>\r\n",
            'expect_pattern': r"DAQPRJ.*",
            'delay': 0.5  # Longer timeout for XML response
        },
        
        # Logging commands
        {
            'pattern': r'^\$logging disable\r\n?$',
            'send_msg': b"$logging disable\r\n",
            'response': b"$logging disabled\r\n",
            'expect_pattern': r"disabled",
            'delay': 0.1
        },
        {
            'pattern': r'^\$logging enable\r\n?$',
            'send_msg': b"$logging enable\r\n",
            'response': b"$logging enabled\r\n",
            'expect_pattern': r"enabled",
            'delay': 0.1
        },
        
        # System information
        {
            'pattern': r'^\$bootversion\r\n?$',
            'send_msg': b"$bootversion\r\n",
            'response': b"$V2.18\r\n",
            'expect_pattern': r"\$V2.*",
            'delay': 0.1
        },
        {
            'pattern': r'^\$info\r\n?$',
            'send_msg': b"$info\r\n",
            'response': b"$KT: 'Nano.2(.3) 15'\r\n"
                       b"$SWV: 'V14.0n3'\r\n"
                       b"$FWV I/O: 'V1.2.8'\r\n"
                       b"$SN I/O: '2581475'\r\n"
                       b"$SN BCE: '2727152'\r\n",
            'expect_pattern': r"\$KT:.*",
            'delay': 0.1
        },
        {
            'pattern': r'^\$uptime\r\n?$',
            'send_msg': b"$uptime\r\n",
            'response': b"$666151\r\n",
            'expect_pattern': r"\$\d+",
            'delay': 0.1
        },
        
        # Dynamic responses
        {
            'pattern': r'^\$rtc get\r\n?$',
            'send_msg': b"$rtc get\r\n",
            'response': lambda: f"${time.strftime('%Y-%m-%d %H:%M:%S')}\r\n".encode(),
            'expect_pattern': r"\$\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}",
            'delay': 0.1
        },
        
        # Parameter and monitoring
        {
            'pattern': r'^\$par get changed.*\r\n?$',
            'send_msg': b"$par get changed \"2023-11-12 18:21:37\"\r\n",
            'response': b"$PR001;6;1;4;1;0;0;0;Mode;Manu;Arr;Ballon;Auto;Arr combustion;\r\n$PR011;6;0;5;1;0;0;0;Zone 1 Mode;Arr;Auto;R\xe9duire;Confort;1x Confort;Refroid.;\r\n$--\r\n",
            'expect_pattern': r"\$PR.*",
            'delay': 0.1
        },
        {
            'pattern': r'^get pm\r\n?$',
            'send_msg': b"get pm\r\n",
            'response': b"pm 9 20.0 7.7 65.7 0 60.3 32 11 110.3 67 68 70.0 120 34.1 68 5 0 0 0 70 0 0 30 100 85 85 72 84.8 85 1 0 13 3 0 0 0 9 21 0 566 1956 1133 8.00 13.58 589 -5.3 24190 140.0 108.8 33 -20.0 -20.0 0.0 11.4 10.1 0 -20.0 0 20.0 20.0 0 1\r\n",
            'expect_pattern': r"pm\s+.*",
            'delay': 1.0
        },
        {
            'pattern': r'^get em\r\n?$',
            'send_msg': b"get em\r\n",
            'response': b"em 9 20.0 7.7 65.7 0 60.3 32 11 110.3 67 68 70.0 120 34.1 \r\n",
            'expect_pattern': r"em\s+.*",
            'delay': 1.0
        },
        {
            'pattern': r'^get dm\r\n?$',
            'send_msg': b"get dm\r\n",
            'response': b"dm 9 20.0 7.7 65.7 0 60.3 32 11 110.3 67 68 70.0 120 34.1 \r\n",
            'expect_pattern': r"dm\s+.*",
            'delay': 1.0
        }
    ]

    def __init__(self, serial_number="0039808", version="6.4.1", interface=None):
        self.serial_number = serial_number
        self.version = version
        self.interface = interface
        self.running = True
        self.udp_sockets = {}
    
    def _is_ip_address(self, ip):
        """Check if a string is a valid IPv4 address"""
        try:
            parts = ip.split('.')
            return len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts)
        except (AttributeError, TypeError, ValueError):
            return False
    
    def create_udp_socket(self, port, bind=True):
        """Create a UDP socket with common settings"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.2)
        
        if bind and self.interface:
            try:
                import platform
                if platform.system() == 'Linux':
                    # Linux: use SO_BINDTODEVICE
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self.interface.encode())
                    sock.bind(('', port))
                elif platform.system() == 'Darwin':
                    # On macOS, bind directly to the interface IP
                    ip = self.interface
                    if not self._is_ip_address(ip):
                        print(f"On macOS, please provide the IP address directly instead of the interface name")
                        print(f"For example: use '192.168.1.100' instead of 'en4'")
                        return None
                    try:
                        sock.bind((ip, port))
                        print(f"Using IP {ip}")
                    except Exception as e:
                        print(f"Error binding to IP {ip}: {e}")
                        return None
                print(f"Listening on UDP port {port} on interface {self.interface}")
            except OSError as e:
                print(f"Could not bind to port {port}: {e}")
                return None
        else:
            try:
                sock.bind(('', port))
                print(f"Listening on UDP port {port}")
            except OSError as e:
                print(f"Could not bind to port {port}: {e}")
                return None
                
        return sock
    
    def create_telnet_socket(self, port=23):
        """Create a TCP socket for telnet with common settings"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            if self.interface:
                import platform
                if platform.system() == 'Linux':
                    # Linux: use SO_BINDTODEVICE
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self.interface.encode())
                    sock.bind(('', port))
                elif platform.system() == 'Darwin':
                    # On macOS, bind directly to the interface IP
                    ip = self.interface
                    if not self._is_ip_address(ip):
                        print("On macOS, please provide the IP address directly instead of the interface name")
                        print("For example: use '192.168.1.100' instead of 'en4'")
                        return None
                    try:
                        sock.bind((ip, port))
                        print(f"Using IP {ip}")
                    except OSError as e:
                        print(f"Error binding to IP {ip}: {e}")
                        return None
            else:
                sock.bind(('', port))
            sock.listen(1)
            print(f"Listening on telnet port {port}" + (f" on interface {self.interface}" if self.interface else ""))
            return sock
        except OSError as e:
            print(f"Could not bind to port {port}: {e}")
            return None

    def handle_telnet_command(self, command):
        """Process a telnet command against the command patterns"""
        # Don't strip() the command - we need to keep \r\n for pattern matching
        for cmd in self.commands:
            match = re.match(cmd['pattern'], command)
            if match:
                response = cmd['response']
                if callable(response):
                    return response()
                return response
        
        print(f"Unknown command: {command}")
        return None

    def handle_telnet_connection(self, client, commands_list=None):
        """Handle an individual telnet client connection"""
        try:
            while self.running:
                try:
                    data = client.recv(1024)
                    if not data:
                        break

                    command = data.decode()
                    print(f"Received command: {command.strip()}")

                    response = self.handle_telnet_command(command)
                    if response:
                        try:
                            print(f"Sending response: {response.decode().strip()}")
                        except Exception as e:
                            print(f"Error decoding response: {e}")

                        client.send(response)

                except socket.timeout:
                    continue

        except socket.error as e:
            print(f"Error handling telnet client: {e}")
        finally:
            client.close()

    def send_udp_broadcast(self, message, src_port, dst_port, expect_reply=False, reply_pattern=None, reply_timeout=None, delta=0):
        """Send a UDP broadcast and optionally wait for a reply"""
        if src_port not in self.udp_sockets:
            sock = self.create_udp_socket(src_port)
            if not sock:
                return None
            self.udp_sockets[src_port] = sock

        sock = self.udp_sockets[src_port]
        
        try:
            print(f"Broadcasting from port {src_port} to {dst_port}: {message.decode()}")
            sock.sendto(message, ('<broadcast>', dst_port))

            if expect_reply and reply_pattern and reply_timeout:
                print(f"Waiting for reply containing {reply_pattern}...")
                start_time = time.time()
                sock.settimeout(reply_timeout)

                while time.time() - start_time < reply_timeout:
                    try:
                        data, addr = sock.recvfrom(1024)
                        if reply_pattern in data:
                            print(f"Received reply from {addr}: {data.decode()}")
                            return data, addr
                    except socket.timeout:
                        continue
                    except socket.error as e:
                        print(f"Error receiving reply: {e}")
                        break

                sock.settimeout(0.2)  # Reset timeout

        except socket.error as e:
            print(f"Error broadcasting from {src_port} to {dst_port}: {e}")

        return None

    def stop(self):
        """Clean shutdown of all sockets"""
        self.running = False
        for sock in self.udp_sockets.values():
            sock.close()
