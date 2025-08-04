#!/usr/bin/env python3

import socket
import time
import threading
import re
import platform
from shared_simulator import SharedSimulator

class BoilerSimulator(SharedSimulator):

    def __init__(self, serial_number="0039808", version="6.4.1", interface=None, delta=0):
        """Initialize the boiler simulator
        
        Args:
            serial_number (str): Device serial number
            version (str): Software version
            interface (str): Network interface name to use (e.g., "en0" on macOS, "eth0" on Linux). If None, will bind to all interfaces.
        """
        super().__init__(serial_number, version, interface)
        
        # Create telnet server socket
        self.telnet_server = self.create_telnet_socket()

        ports_to_listen = [35601+delta, 50001+delta]
        for port in ports_to_listen:
            sock = self.create_udp_socket(port)
            if sock:
                self.udp_sockets[port] = sock

    def start(self):
        # Create listener threads for each port
        threads = []
        for port, sock in self.udp_sockets.items():
            thread = threading.Thread(target=self.listen_for_broadcasts, args=(port, sock))
            thread.daemon = True
            thread.start()
            threads.append(thread)

        # Start telnet server thread
        telnet_thread = threading.Thread(target=self.handle_telnet_connections)
        telnet_thread.daemon = True
        telnet_thread.start()
        threads.append(telnet_thread)

        try:
            # Keep main thread alive
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def handle_get_services(self, sock, addr):
        # Reply with HSV services list as seen in Wireshark capture
        response = (
            b"HSV/CL etc *.cgi\n"
            b"HSV0\n"
            b"HSV1\n"
            b"HSV2\n"
            b"HSV3\n"
            b"HSV4\n"
            b"HSV5\n"
            b"HSV6\n"
            b"HSV7\n"
            b"HSV8\n"
            b"HSV9"
        )
        sock.sendto(response, addr)
        print(f"Sent services list to {addr}")

    def handle_diagnostics_request(self, sock, addr):
        # Reply with diagnostics info
        response = (
            f"hargassner.diagnostics\n"
            f"serialnr:{self.serial_number}\n"
            f"software:{self.version}\n"
            f"bootloader:5.00\n"
            f"type:info\n"
            f"message:running"
        ).encode()
        sock.sendto(response, addr)
        print(f"Sent diagnostics to {addr}")

    def listen_for_broadcasts(self, port, sock):
        while self.running:
            try:
                data, addr = sock.recvfrom(1024)
                print(f"Received on port {port} from {addr}: |{data.decode()}|")

                # Handle different message types
                if b"get services" in data:
                    self.handle_get_services(sock, addr)
                elif b"hargassner.diagnostics.request" in data:
                    self.handle_diagnostics_request(sock, addr)
                elif b"HargaWebApp" in data:
                    print("Received gateway announcement")
                else:
                    print("Received unknown message:", data.decode())
            except socket.timeout:
                continue
            except socket.error as e:
                print(f"Error on port {port}: {e}")

    def handle_telnet_connections(self):
        """Handle incoming telnet connections and their commands"""
        while self.running:
            try:
                client, addr = self.telnet_server.accept()
                print(f"New telnet connection from {addr}")
                client_thread = threading.Thread(target=self.handle_telnet_client, args=(client,))
                client_thread.daemon = True
                client_thread.start()
            except socket.timeout:
                continue
            except socket.error as e:
                print(f"Telnet connection error: {e}")

    def handle_telnet_client(self, client):
        """Handle individual telnet client commands"""
        try:
            self.handle_telnet_connection(client)
        except socket.error as e:
            print(f"Error handling telnet client: {e}")
        finally:
            client.close()

    def stop(self):
        super().stop()
        if self.telnet_server:
            self.telnet_server.close()

if __name__ == "__main__":
    # Specify the network interface name (e.g., "en0" on macOS, "eth0" on Linux)
    interface = None  # Change this to use a specific interface, e.g., "en0"
    boiler = BoilerSimulator(delta=100)
    print("Starting Boiler Simulator...")
    print("Listening for gateway broadcasts...")
    boiler.start()
