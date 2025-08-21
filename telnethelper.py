"""
A client implementation for Telnet communication with a boiler system.
This module provides a robust interface for establishing and managing telnet connections,
with proper error handling and connection management.
"""

# Standard library imports
import logging
import socket
import platform
import time
import re
from typing import Tuple
import psutil

# Project imports
from shared import BUFF_SIZE
from socket_manager import SocketManager

class TelnetClient:
    """
    A class that handles Telnet communication with a boiler system.
    
    This class provides methods for establishing connections, sending/receiving data,
    and managing the connection lifecycle with proper error handling.
    
    Attributes:
        _sock (socket.socket | None): The underlying socket connection
        _connected (bool): Flag indicating if the connection is active
        _addr (bytes): The target address for the connection
        _port (int): The port number for the connection
    """
    _connected: bool = False

    def __init__(self, addr: bytes, dst_iface: bytes, port: int = 0):
        """
        Initialize a new TelnetClient instance.

        Args:
            addr (bytes): The target address for the connection.
            port (int): The port number for the connection. If 0, uses default ports based on platform.
        """
        logging.debug("TelnetClient.__init__ called with addr: %s, port: %d", repr(addr), port)
        self._addr = addr
        self._connected = False
        self._sock: socket.socket | None = None

        if port:
            self._port = port
        else:
            # we assume on Darwin for testing that the port of BoilerSimulator is 24
            if platform.system() == 'Darwin':
                self._port = 24  # port of boiler simulator
            elif platform.system() == 'Linux' and SocketManager.are_same_machines(addr, dst_iface):
                #on linux if the discover ip of boiler is the same as the dst_iface we simulate the boiler to port 24
                self._port = 24  # port of boiler simulator
            else:
                # we assume a connection to a real boiler
                self._port = 23  # default telnet port

    def _get_ip_from_iface(self, iface_bytes: bytes) -> str:
        """
        Convert a network interface name (e.g., b'eth0' or b'en0') to its IPv4 address using psutil.
        Returns the IP as a string, or raises RuntimeError if not found.
        Works on Linux and macOS.
        """
        iface = iface_bytes.decode('utf-8') if isinstance(iface_bytes, bytes) else str(iface_bytes)
        addrs = psutil.net_if_addrs()
        if iface not in addrs:
            raise RuntimeError(f"Interface {iface} not found.")
        for addr in addrs[iface]:
            if addr.family == socket.AF_INET:
                return addr.address
        raise RuntimeError(f"No IPv4 address found for interface {iface}.")

    def connect(self, timeout_sec: float = 2.0) -> None:
        """
        Connect to the boiler using the address specified during initialization.

        Raises:
            RuntimeError: If no address was specified during initialization.
            socket.error: If connection fails. The method will retry after a delay.
        """
        logging.debug("TelnetClient.connect called")
        addr = self._addr
        # If addr looks like an interface name (not an IP), convert it
        try:
            # Accept both bytes and str, check if it's not an IP
            addr_str = addr.decode('utf-8') if isinstance(addr, bytes) else str(addr)

            if not re.match(r"^\d+\.\d+\.\d+\.\d+$", addr_str):
                addr_str = self._get_ip_from_iface(addr)
        except Exception as e:
            logging.error(f"Failed to resolve interface to IP: {e}")
            raise RuntimeError("Invalid address/interface:") from e

        logging.debug('TelnetClient connecting to %s on port %d', repr(addr_str), self._port)
        if not addr_str:
            raise RuntimeError("No address specified")

        logging.info('TelnetClient connecting to %s on port %d', repr(addr_str), self._port)
        while not self._connected:
            try:
                # we will now create the socket
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._sock.settimeout(timeout_sec)
                self._sock.connect((addr_str, self._port))
                self._connected = True
                logging.info('telnet connected to %s on port %d', repr(addr_str), self._port)
            except socket.error as e:
                logging.error('telnet connection error: %s', e)
                if self._sock:
                    self._sock.close()
                self._sock = None
                time.sleep(5)  # Give some time for the connection to stabilize

    def close(self) -> None:
        """
        Close the telnet connection if it's active.
        """
        if self._connected and self._sock:
            try:
                logging.info('telnet closing connection')
                self._sock.close()
            except socket.error as e:
                logging.error('Error closing connection: %s', e)
            finally:
                self._sock = None
                self._connected = False
        else:
            logging.warning('telnet close called but not connected')

    def send(self, data: bytes) -> None:
        """
        Send data over the telnet connection.

        Args:
            data (bytes): The data to send.

        Raises:
            RuntimeError: If the connection is not established.
            socket.error: If sending fails.
        """
        if not self._connected or not self._sock:
            raise RuntimeError("Not connected")
        try:
            self._sock.send(data)
        except socket.error as e:
            logging.error('Error sending data: %s', e)
            self.close()
            raise

    def socket(self) -> socket.socket | None:
        """
        Get the underlying socket object.

        Returns:
            socket.socket | None: The socket object or None if not connected.
        """
        return self._sock

    def recv(self, size: int) -> bytes:
        """
        Receive data from the telnet connection.

        Args:
            size (int): The maximum number of bytes to receive.

        Returns:
            bytes: The received data.

        Raises:
            RuntimeError: If the connection is not established.
            socket.error: If receiving fails.
        """
        if not self._connected or not self._sock:
            raise RuntimeError("Not connected")
        try:
            return self._sock.recv(size)
        except socket.error as e:
            logging.error('Error receiving data: %s', e)
            self.close()
            raise

    def recvfrom(self) -> Tuple[bytes, bytes]:
        """
        Receive data and address information from the telnet connection.

        Returns:
            Tuple[bytes, bytes]: A tuple containing the received data and address.

        Raises:
            RuntimeError: If the connection is not established.
            socket.error: If receiving fails.
        """
        if not self._connected or not self._sock:
            raise RuntimeError("Not connected")
        try:
            return self._sock.recvfrom(BUFF_SIZE)
        except socket.error as e:
            logging.error('Error receiving data: %s', e)
            self.close()
            raise
