#!/usr/bin/env python3

import socket
import time
import threading
import re
from shared_simulator import SharedSimulator

class GatewaySimulator(SharedSimulator):
    def __init__(self, serial_number="0039808", version="6.4.1", interface=None, delta=0):
        super().__init__(serial_number, version, interface)
        self.discovered_devices = set()  # Track devices that respond to broadcasts
        self.sending_telnet = False  # Flag to control UDP broadcasts during telnet
        self.delta = delta  # delta to modify destination ports

    def start(self):
        # Start UDP broadcasting in a separate thread
        udp_thread = threading.Thread(target=self.udp_broadcast)
        udp_thread.start()
        
        # Wait for the UDP thread to complete
        udp_thread.join()

    def udp_broadcast(self):
        # Define all the different types of messages from the capture
        # Format: (message, src_port, dst_port, wait_for_reply, reply_pattern, reply_timeout)
        messages = [
            # HargaWebApp announcement
            (f"HargaWebApp v{self.version}\r\nSN:{self.serial_number}", 50000, 35601, False, None, None),
            
            # Diagnostics info
#            (f"hargassner.diagnostics\n"
#             f"serialnr:{self.serial_number}\n"
#             f"software:{self.version}\n"
#             f"bootloader:5.00\n"
#             f"type:info\n"
#             f"message:running", 50001, 50002, False, None, None),
            
            # Diagnostics request
            ("hargassner.diagnostics.request", 50002, 50001, False, None, None),
            
            # Services request - wait for reply from device
            ("get services", 50000, 35601, True, b"HSV", 5.0)  # Wait up to 5 seconds for reply containing "HSV"
        ]

        while self.running:
            # Skip broadcasting if we're in a telnet sequence
            if self.sending_telnet:
                time.sleep(5)  # Sleep briefly and check again
                continue
                
            for message, src_port, dst_port, wait_reply, reply_pattern, timeout in messages:
                try:
                    # Encode string messages to bytes
                    message_bytes = message.encode() if isinstance(message, str) else message
                    result = self.send_udp_broadcast(message_bytes, src_port, dst_port+ self.delta, 
                                                   wait_reply, reply_pattern, timeout)
                    
                    # Handle successful service discovery
                    if result and reply_pattern == b"HSV":
                        data, addr = result
                        self.discovered_devices.add(addr[0])
                        telnet_thread = threading.Thread(
                            target=self.initiate_telnet_connection,
                            args=(addr[0],)
                        )
                        time.sleep(5) # wait telnet server to be ready
                        telnet_thread.daemon = True
                        telnet_thread.start()

                except socket.error as e:
                    print(f"Error in UDP broadcast: {e}")

                time.sleep(3)  # Small delay between messages

    def initiate_telnet_connection(self, host):
        """Initiate a Telnet connection to a discovered device"""
        telnet_client = None
        self.sending_telnet = True  # Stop UDP broadcasts
        try:
            # Create and connect socket
            telnet_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            telnet_client.settimeout(5.0)
            telnet_client.connect((host, 23))
            print(f"Connected to {host} on port 23")

            # Process each message in sequence
            while True:
                print(f"Starting telnet sequence with {host}")
                for cmd in self.commands:
                    print(f"Sending: {cmd['send_msg'].decode().strip()}")
                    telnet_client.send(cmd['send_msg'])
        
                    if cmd['expect_pattern']:  # If we expect a response
                        try:
                            data = telnet_client.recv(1024)
                            if data:
                                decoded_data = data.decode().strip()
                                print(f"Received: {decoded_data}")
                            
                                if not re.search(cmd['expect_pattern'], decoded_data):
                                    print(f"Error: Response '{decoded_data}' does not match expected pattern '{cmd['expect_pattern']}'")
                                else:
                                    print(f"Response matches expected pattern: '{cmd['expect_pattern']}'")
                        except socket.timeout:
                            print(f"Timeout waiting for response to {cmd['send_msg'].decode().strip()}")
                        except UnicodeDecodeError as e:
                            print(f"Error decoding response: {e}")
                    time.sleep(2)  # Wait specified delay before next message
                print(f"Completed telnet sequence with {host}")

        except socket.error as e:
            print(f"Telnet connection error with {host} on port 23: {e}")
        finally:
            if telnet_client:
                try:
                    telnet_client.close()
                except socket.error:
                    pass  # Ignore errors during close
            self.sending_telnet = False  # Resume UDP broadcasts

if __name__ == "__main__":
    gateway = GatewaySimulator(delta=00)
    print("Starting Gateway Simulator...")
    print("Broadcasting UDP on port 50000 -> 35601")
    try:
        gateway.start()
    except KeyboardInterrupt:
        print("\nShutting down Gateway Simulator...")
    finally:
        gateway.stop()
