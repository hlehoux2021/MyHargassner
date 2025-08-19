"""
A client implementation for Telnet communication with a boiler system.
This module provides a robust interface for establishing and managing telnet connections,
with proper error handling and connection management.
"""

import socket as s
import logging
import platform
import time
from typing import Tuple

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
        self._sock: s.socket | None = None

        if port:
            self._port = port
        else:
            # we assume on Darwin for testing that the port of BoilerSimulator is 24 
            if platform.system() == 'Darwin':
                self._port = 24  # port of boiler simulator
            elif platform.system() == 'Linux' and SocketManager.are_same_machines(addr, dst_iface):
                #on linux if the discover ip of boiler is the same as the dst_iface then we simulate the boiler to port 24
                self._port = 24  # port of boiler simulator
            else:
                # we assume a connection to a real boiler  
                self._port = 23  # default telnet port

    def connect(self) -> None:
        """
        Connect to the boiler using the address specified during initialization.

        Raises:
            RuntimeError: If no address was specified during initialization.
            socket.error: If connection fails. The method will retry after a delay.
        """
        logging.debug("TelnetClient.connect called")
        logging.debug('TelnetClient connecting to %s on port %d', repr(self._addr), self._port)
        if not self._addr:
            raise RuntimeError("No address specified")
            
        logging.info('TelnetClient connecting to %s on port %d', repr(self._addr), self._port)
        while not self._connected:
            try:
                # we will now create the socket
                self._sock = s.socket(s.AF_INET, s.SOCK_STREAM)
                self._sock.setsockopt(s.SOL_SOCKET, s.SO_REUSEPORT, 1)
                self._sock.setsockopt(s.SOL_SOCKET, s.SO_REUSEADDR, 1)
                self._sock.connect((self._addr, self._port))
                self._connected = True
                logging.info('telnet connected to %s on port %d', repr(self._addr), self._port)
            except s.error as e:
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
            except s.error as e:
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
        except s.error as e:
            logging.error('Error sending data: %s', e)
            self.close()
            raise

    def socket(self) -> s.socket | None:
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
        except s.error as e:
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
        except s.error as e:
            logging.error('Error receiving data: %s', e)
            self.close()
            raise
