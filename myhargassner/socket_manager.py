"""
Common socket management utilities and exceptions for the HARG project.
"""

# Standard library imports
import logging
import socket
import platform
from typing import Tuple, Union, Optional

# Project imports
from myhargassner.appconfig import AppConfig

class HargSocketError(Exception):
    """Base exception for socket operations."""
    pass

class SocketTimeoutError(HargSocketError):
    """Exception raised when a socket operation times out."""
    pass

class SocketBindError(HargSocketError):
    """Exception raised when socket binding fails."""
    pass

class SocketSendError(HargSocketError):
    """Exception raised when sending data fails."""
    pass

class SocketReceiveError(HargSocketError):
    """Exception raised when receiving data fails."""
    pass

class InterfaceError(HargSocketError):
    """Exception raised when interface configuration is invalid."""
    pass

class SocketManager:
    """
    Common socket management functionality for HARG project.
    Handles platform-specific binding and error management.
    
    The class provides methods for:
    - Creating and configuring sockets for UDP communication
    - Platform-specific binding (Linux/macOS differences)
    - Error handling for socket operations
    - Timeout management for non-blocking operations
    - Detection of same-machine scenarios for port adjustment
    """

    appconfig: AppConfig

    def __init__(self, appconfig: AppConfig,
                 src_iface: Union[str, bytes],
                 dst_iface: Union[str, bytes],
                 is_broadcast: bool = False) -> None: #pylint: disable=line-too-long
        """
        Initialize the socket manager.

        Args:
            src_iface: Network src_iface name (Linux) or IP address (macOS)
            dst_iface: Network dst_iface name (Linux) or IP address (macOS)
            is_broadcast: Whether the socket needs broadcast capability

        Raises:
            InterfaceError: If src_iface specification is invalid for the platform
            ValueError: If src_iface is not bytes or str
        """
        self.appconfig = appconfig
        if isinstance(src_iface, bytes):
            self.src_iface = src_iface.decode('utf-8')
        elif isinstance(src_iface, str):
            self.src_iface = src_iface
        else:
            raise ValueError("src_iface must be either bytes or str")
        if isinstance(dst_iface, bytes):
            self.dst_iface = dst_iface.decode('utf-8')
        elif isinstance(dst_iface, str):
            self.dst_iface = dst_iface
        else:
            raise ValueError("dst_iface must be either bytes or str")

        self.is_broadcast = is_broadcast
        self._socket: Optional[socket.socket] = None
        self._validate_interface()

    def _validate_interface(self) -> None:
        """
        Validate interface specification based on platform.

        Raises:
            InterfaceError: If interface specification is invalid
        """
        if platform.system() == 'Darwin' and not self.is_valid_ip(self.src_iface):
            raise InterfaceError(
                f"MacOS requires IP address, got interface name: {self.src_iface}. "
                "Please provide IP address instead of interface name."
            )
        if platform.system() == 'Darwin' and not self.is_valid_ip(self.dst_iface):
            raise InterfaceError(
                f"MacOS requires IP address, got interface name: {self.dst_iface}. "
                "Please provide IP address instead of interface name."
            )

    @staticmethod
    def is_valid_ip(ip: str) -> bool:
        """
        Check if a string is a valid IPv4 address.
        
        Args:
            ip: String to validate as IPv4 address
            
        Returns:
            bool: True if string is a valid IPv4 address, False otherwise
        
        Example:
            >>> SocketManager.is_valid_ip("192.168.1.1")
            True
            >>> SocketManager.is_valid_ip("256.1.2.3")
            False
            >>> SocketManager.is_valid_ip("eth0")
            False
        """
        try:
            parts = ip.split('.')
            return len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts)
        except (AttributeError, TypeError, ValueError):
            return False

    def create_socket(self) -> socket.socket:
        """
        Create and configure a new socket.

        Returns:
            socket.socket: Configured socket

        Raises:
            SocketBindError: If socket creation fails
        """
        try:
            logging.debug('SocketManager: Creating UDP socket')
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            logging.debug('SocketManager: Set SO_REUSEPORT')
            if self.is_broadcast:
                self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                logging.debug('SocketManager: Set SO_BROADCAST')
            timeout = self.appconfig.socket_timeout()
            self._socket.settimeout(timeout)
            logging.debug('SocketManager: Set socket timeout to %s', timeout)
            if platform.system() == 'Linux' and not self.is_valid_ip(self.src_iface):
                # On Linux, bind to interface name
                # SO_BINDTODEVICE = 25 from Linux <socket.h>
                self._socket.setsockopt(
                    socket.SOL_SOCKET,
                    25,  # SO_BINDTODEVICE
                    self.src_iface.encode('utf-8')
                )
                logging.debug('SocketManager: Set SO_BINDTODEVICE to %s', self.src_iface)
            # On MacOS, binding to IP is done during bind() call
            logging.debug('SocketManager: Socket created successfully')
            return self._socket
        except socket.error as e:
            logging.error('SocketManager: Failed to create socket: %s', str(e))
            raise SocketBindError(f"Failed to create socket: {str(e)}") from e

    def bind(self, port: int, specific_ip: Optional[str] = None) -> None:
        """
        Bind the socket to an address.

        Args:
            port: Port number to bind to
            specific_ip: Specific IP address to bind to (optional)

        Raises:
            SocketBindError: If binding fails
        """
        if not self._socket:
            logging.error('SocketManager: Cannot bind, socket not created')
            raise SocketBindError("Socket not created")
        try:
            # On MacOS or when specific IP is provided
            if platform.system() == 'Darwin' or specific_ip:
                bind_ip = specific_ip or self.src_iface
                logging.debug('SocketManager: Binding to IP %s, port %d', bind_ip, port)
                self._socket.bind((bind_ip, port))
            else:
                # On Linux, we've already bound to interface, so bind to all interfaces
                logging.debug('SocketManager: Binding to all interfaces, port %d', port)
                self._socket.bind(('', port))
            logging.debug('SocketManager: Bind successful')
        except socket.error as e:
            logging.error('SocketManager: Failed to bind socket: %s', str(e))
            raise SocketBindError(f"Failed to bind socket: {str(e)}") from e

    def bind_with_delta(self, port: int, delta: int = 0, broadcast: bool = False) -> None:
        """
        Bind socket with platform-specific handling and port delta adjustment.
        When delta is negative, it means we need to bind to a lower port than
        the target port (e.g., bind to 49900 when gateway is on 50000).
        
        Args:
            port: Base port number (e.g. 50000)
            delta: Port adjustment (e.g. -100 to bind to 49900)
            
        Raises:
            SocketBindError: If binding fails
            InterfaceError: If interface specification is invalid
        """
        if not self._socket:
            logging.error('SocketManager: Cannot bind_with_delta, socket not created')
            raise SocketBindError("Socket not created")
        try:
            # Platform-specific binding with port adjustment
            if self.is_same_machine():
                adjusted_port = port + delta # the caller tells what delta to use if same machine
                logging.debug('SocketManager: Same machine detected, adjusting port from %d to %d (delta: %d)',
                                  port, adjusted_port, delta)
            else:
                adjusted_port = port
            # choose binding address based on platform (Linux/MacOS) and broadcast parameter
            if platform.system() == 'Darwin':
                # On MacOS, we decide based on broadcast parameter
                if broadcast:
                    logging.debug('SocketManager: Binding to all on port %d (original port %d with delta %d)',
                          adjusted_port, port, delta)
                    self._socket.bind(('', adjusted_port))
                else:
                    logging.debug('SocketManager: Binding to %s on port %d (original port %d with delta %d)',
                          self.src_iface, adjusted_port, port, delta)
                    self._socket.bind((self.src_iface, adjusted_port))
            else:
                # assuming we're on Linux, we bind to any because we have set SO_BINDTODEVICE
                logging.debug('SocketManager: Binding to all on port %d (original port %d with delta %d)',
                          adjusted_port, port, delta)
                self._socket.bind(('', adjusted_port))
            logging.debug('SocketManager: bind_with_delta successful')
        except socket.error as e:
            logging.error('SocketManager: Failed to bind_with_delta: %s', str(e))
            raise SocketBindError(f"Failed to bind socket: {str(e)}") from e

    def send_with_delta(self, data: bytes, port: int, delta: int = 0, dest: str = '<broadcast>') -> None:
        """
        Send data with platform-specific handling and port delta adjustment.
        When delta is negative, it means we need to send to a lower port than
        the target port (e.g., send to 49900 when gateway is on 50000).
        
        Args:
            data: Data to send
            port: Base port number (e.g. 50000)
            delta: Port adjustment (e.g. -100 to send to 49900)
            dest: Destination address (defaults to broadcast)
            
        Raises:
            SocketSendError: If sending fails
            SocketTimeoutError: If send times out
            InterfaceError: If interface specification is invalid
        """

        logging.debug('SocketManager: send_with_delta called port=%d, delta=%d, dest=%s', port, delta, dest)
        logging.debug('SocketManager: src_iface %s dst_iface %s', self.src_iface, self.dst_iface)
        if not self._socket:
            logging.error('SocketManager: Cannot send_with_delta, socket not created')
            raise SocketSendError("Socket not created")
        platform_type = platform.system()
        if platform_type == 'Darwin' and not self.is_valid_ip(self.src_iface):
            # Validate IP on MacOS
            logging.error('SocketManager: Invalid source IP for MacOS: %s', self.src_iface)
            raise InterfaceError(f"Invalid source IP for MacOS: {self.src_iface}")
        try:
            # Platform-specific address handling
            # Calculate final port (e.g. 50000 + (-100) = 49900)
            if self.is_same_machine():
                adjusted_port = port + delta # the caller tells what delta to use if same machine
                logging.debug('SocketManager: Same machine detected, adjusting port from %d to %d (delta: %d)',
                                  port, adjusted_port, delta)
            else:
                adjusted_port = port

            logging.debug('SocketManager: Sending from %s to %s on port %d',
                          self.src_iface, dest, adjusted_port)
            self._socket.sendto(data, (dest, adjusted_port))
            logging.debug('SocketManager: send_with_delta successful')
        except socket.timeout as e:
            logging.error('SocketManager: Send operation timed out')
            raise SocketTimeoutError("Send operation timed out") from e
        except socket.error as e:
            logging.error('SocketManager: Failed to send data: %s', str(e))
            raise SocketSendError(f"Failed to send data: {str(e)}") from e

    def send(self, data: bytes, address: Tuple[str, int]) -> None:
        """
        Basic send operation with timeout handling.
        Consider using send_with_delta for platform-specific handling.

        Args:
            data: Data to send
            address: (host, port) tuple

        Raises:
            SocketSendError: If sending fails
            SocketTimeoutError: If send times out
        """
        if not self._socket:
            raise SocketSendError("Socket not created")

        try:
            self._socket.sendto(data, address)
        except socket.timeout as e:
            raise SocketTimeoutError("Send operation timed out") from e
        except socket.error as e:
            raise SocketSendError(f"Failed to send data: {str(e)}") from e

    def receive(self) -> Tuple[bytes, Tuple[str, int]]:
        """
        Receive data with timeout handling.

        Args:
            buffer_size: Size of receive buffer

        Returns:
            Tuple of (data, address)

        Raises:
            SocketReceiveError: If receiving fails
            SocketTimeoutError: If receive times out
        """
        if not self._socket:
            logging.error('SocketManager: Cannot receive, socket not created')
            raise SocketReceiveError("Socket not created")
        try:
            #logging.debug('SocketManager: Waiting to receive data (buffer size %d)', buffer_size)
            result = self._socket.recvfrom(
                self.appconfig.buff_size()
            )
            logging.debug('SocketManager: Received %d bytes from %s:%d', len(result[0]), result[1][0], result[1][1])
            return result
        except socket.timeout as e:
            #logging.debug('SocketManager: Receive operation timed out')
            raise SocketTimeoutError("Receive operation timed out") from e
        except socket.error as e:
            logging.error('SocketManager: Failed to receive data: %s', str(e))
            raise SocketReceiveError(f"Failed to receive data: {str(e)}") from e

    def close(self) -> None:
        """Close the socket if it exists."""
        if self._socket:
            self._socket.close()
            self._socket = None

    def __del__(self) -> None:
        """Ensure socket is closed on deletion."""
        self.close()

    @staticmethod
    def are_same_machines(addr1: str|bytes, addr2: str|bytes) -> bool:
        """
        Check if two IP addresses belong to the same machine.

        Args:
            addr1: First IP address
            addr2: Second IP address

        Returns:
            bool: True if addresses belong to same machine
        """
        if addr1 == addr2:
            return True
        # Check if either is localhost
        localhost = {'127.0.0.1', 'localhost', '::1'}
        return addr1 in localhost and addr2 in localhost

    def is_same_machine(self) -> bool:
        """
        Check if the source interface is the same as the destination interface.
        
        Returns:
            bool: True if source and destination interfaces are the same
        """
        return self.are_same_machines(self.src_iface, self.dst_iface)
