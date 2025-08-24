"""
 This module contains core classes for boiler, gateway and telnetproxy
"""

# Standard library imports
import logging
from queue import Empty
import socket
import platform
from typing import Annotated, Union, Optional, Callable, Tuple
from abc import ABC, abstractmethod

# Third party imports
import annotated_types

from myhargassner.pubsub.pubsub import PubSub, ChanelQueue, ChanelPriorityQueue

# Project imports
from myhargassner.appconfig import AppConfig
from myhargassner.socket_manager import SocketManager, HargSocketError, SocketBindError, InterfaceError, SocketTimeoutError

#class HargInfo():
#    """ a data class to store the HargInfo"""
#    gw_webapp: str = ''  # HargaWebApp version eg 6.4.1
#    gw_sn: str = ''       # IGW serial number


class NetworkData():
    """
    This class is used to register network data about the IGW internet gateway and the real boiler.
    The gateway and boiler (addr,port) are discovered by listening to UDP broadcast messagesocket.
    The gateway will <broadcast> to port 35601 from port 50000, and to port 50001 from port 50002.
    The Boiler will <broadcast> to port 50000 from port 35601 and to port 50002 from port 50001.
    """
    gw_port: Annotated[int, annotated_types.Gt(0)]
    bl_port: Annotated[int, annotated_types.Gt(0)]
    gw_addr: Annotated[bytes, annotated_types.MaxLen(15)]
    bl_addr: Annotated[bytes, annotated_types.MaxLen(15)]
    gwt_port: Annotated[int, annotated_types.Gt(0)]

    def __init__(self):
        self.gw_port = 0    # source port from which gateway is sending
        self.gw_addr= b''   # to save the gateway ip adress when discovered
        self.bl_addr= b''   # to save the boiler ip address when discovered
        self.bl_port= 0     # destination port to which boiler is listening
        self.gwt_port = 0    # source telnet port from which gateway is sending

    def name(self):
        """ Return the class name for logging purposes. """
        return self.__class__.__name__

    def decode_message(self, msg: str):
        """ Decode a message string to extract gateway and boiler addresses and ports.
        The message format is expected to be 'GW_ADDR:<addr>', 'GW_PORT:<port>', 'BL_ADDR:<addr>', 'BL_PORT:<port>'.
        """
        logging.debug('decode_message called with %s', msg)
        if msg.startswith('GW_ADDR:'):
            self.gw_addr = bytes(msg.split(':')[1], 'ascii')
            logging.debug('decode_message: gw_addr=%s', self.gw_addr)
        elif msg.startswith('GW_PORT:'):
            self.gw_port = int(msg.split(':')[1])
            logging.debug('decode_message: gw_port=%d', self.gw_port)
        elif msg.startswith('BL_ADDR:'):
            self.bl_addr = bytes(msg.split(':')[1], 'ascii')
            logging.debug('decode_message: bl_addr=%s', self.bl_addr)
        elif msg.startswith('BL_PORT:'):
            self.bl_port = int(msg.split(':')[1])
            logging.debug('decode_message: bl_port=%d', self.bl_port)
        elif msg.startswith('GWT_PORT:'):
            self.gwt_port = int(msg.split(':')[1])
            logging.debug('decode_message: gwt_port=%d', self.gwt_port)
        else:
            logging.warning('decode_message: unknown message %s', msg)

class ChanelReceiver(NetworkData, ABC):
    """
    This class extends NetworkData class with the possibility to receive messages on a ChanelQueue.
    It defines a method to handle received messages.
    """
    _channel= "bootstrap" # Channel to exchange bootstrap information about boiler and gateway, addr, port, etc
    _com: PubSub # every data receiver should have a PubSub communicator
    _msq: Union[ChanelQueue, ChanelPriorityQueue, None] = None # Message queue for receiving data

    def __init__(self, communicator: PubSub) -> None:  # Remove Optional since we require it
        super().__init__()
        self._com = communicator

    def handle(self, message_handler: Optional[Callable[[str], None]] = None) -> None:
        """
        This method handles received messages from the queue.
        We expect to receive messages to populate the NetworkData class.

        Args:
            message_handler (callable, optional): A function to handle the message.
                If not provided, defaults to self.decode_message.
                The function should accept a string argument.
        """
        logging.debug("handle called on %s with channel %s message_handler=%s",
                     self.name(), self._channel, message_handler)
        if not self._msq:
            logging.error('handle: No message queue available')
            return
        try:
            logging.debug('handle: attempting to get next message')
            # Use non-blocking listen with timeout
            iterator = self._msq.listen(timeout=10.0)
            try:
                _message = next(iterator)
                logging.debug('handle: received message from queue: %s', _message)
            except StopIteration:
                logging.debug('handle: no message available')
                return
            if not _message or 'data' not in _message:
                logging.debug('handle: invalid message format received')
                return
            msg = _message['data']
            if isinstance(msg, bytes):
                msg = msg.decode('latin-1')  # Use latin-1 to avoid UnicodeDecodeError
            logging.debug('handle: decoded message: %s', msg)
            # Use the provided message handler if available, otherwise use decode_message
            handler = message_handler if message_handler is not None else self.decode_message
            logging.debug('handle: calling handler %s with message',
                          handler.__name__ if hasattr(handler, '__name__') else str(handler))
            try:
                handler(msg)
                logging.debug('handle: handler completed successfully')
            except Exception as e:
                logging.error('handle: error in message handler: %s', str(e), exc_info=True)
                raise
        except Empty:
            logging.debug('handle: Empty message received')
        except Exception as e:
            logging.error('handle: unexpected error: %s', str(e), exc_info=True)
            raise
        logging.debug('handle: end of method')

class ListenerSender(ChanelReceiver, ABC):
    """
    This class extends ChanelReceiver class with a socket to listen
    and a socket to resend data.
    """
    listen: socket.socket
    resend: socket.socket
    src_iface: bytes
    dst_iface: bytes
    dst_ip: str
    bound: bool = False
    resender_bound: bool = False
    _appconfig: AppConfig

    @staticmethod
    def _is_ip_address(ip: str) -> bool:
        """Check if a string is a valid IPv4 address"""
        try:
            parts = ip.split('.')
            return len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts)
        except (AttributeError, TypeError, ValueError):
            return False

    def __init__(self, appconfig: AppConfig, communicator: PubSub, src_iface: bytes, dst_iface: bytes) -> None:
        """
        Initialize the ListenerSender with source and destination interfaces.

        Args:
            communicator: PubSub instance for communication
            src_iface: Source interface for listening (name on Linux, IP on MacOS)
            dst_iface: Destination interface for sending (name on Linux, IP on MacOS)

        Raises:
            HargSocketError: If socket initialization fails
            InterfaceError: If interface specification is invalid for the platform
        """
        self._appconfig = appconfig
        super().__init__(communicator)
        self.src_iface = src_iface  # network interface where to listen
        self.dst_iface = dst_iface  # network interface where to resend
        self.bound = False
        self.resender_bound = False

        try:
            # Initialize listener socket
            self.listen_manager = SocketManager(self._appconfig, src_iface, dst_iface, is_broadcast=True)
            self.listen = self.listen_manager.create_socket()

            # Initialize sender socket
            self.send_manager = SocketManager(self._appconfig, dst_iface, src_iface, is_broadcast=True)
            self.resend = self.send_manager.create_socket()

            logging.debug('Sockets initialized on system: %s', platform.system())

            if platform.system() == 'Darwin':
                # Store IP for MacOS binding
                self.src_ip = src_iface.decode('utf-8')
                self.dst_ip = dst_iface.decode('utf-8')

                # Validate IPs
                if not self.listen_manager.is_valid_ip(self.src_ip):
                    raise InterfaceError(f"Invalid source IP for MacOS: {self.src_ip}")
                if not self.send_manager.is_valid_ip(self.dst_ip):
                    raise InterfaceError(f"Invalid destination IP for MacOS: {self.dst_ip}")

                logging.debug('Configured source IP: %s, destination IP: %s', self.src_ip, self.dst_ip)
        except (HargSocketError, InterfaceError) as e:
            logging.error('Failed to initialize sockets: %s', str(e))
            raise

    def handle_first(self, data: bytes, addr: Tuple[str, int]) -> None: # pylint: disable=unused-argument
        """
        This method handles the discovery of caller's ip address and port.
        """
        logging.debug('first packet, resender not bound yet')
        self.publish_discovery(addr)  # Call the method to publish discovery

        # first time we receive a packet, bind the resender
        if self.resender_bound:
            logging.debug('resender already bound, skipping bind operation')
        else:
            try:
                # Get base port from child class
                port, delta = self.get_resender_port()
                # Use send_manager to handle platform-specific binding
                self.send_manager.bind_with_delta(
                    port=port,
                    delta=delta
                )
                self.resender_bound = True
                logging.debug('resender bound to port %d', port)
            except (SocketBindError, InterfaceError) as e:
                logging.error('Failed to bind resender: %s', str(e))
                raise

    @abstractmethod
    def get_resender_port(self) -> Tuple[int, int]:
        """
        Get the base port number for the resender socket.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def send(self, data: bytes) -> None:
        """
        This method resends received data to the destination.
        Must be implemented in the child class.
        """
        pass

    @abstractmethod
    def handle_data(self, data: bytes, addr: Tuple[str, int]) -> None:
        """
        This method handles received data.
        Must be implemented in the child class.
        """
        pass

    @abstractmethod
    def publish_discovery(self, addr: Tuple[str, int]) -> None:
        """
        This method publishes the discovery of the Listener (gateway or boiler) to the Channel Queue.
        It sends the gateway/boiler address and port to the shared queue.
        Must be implemented in the child class.
        """
        pass

    def loop(self) -> None:
        """
        This method is the main loop of the class.
        """
        data: bytes
        addr: tuple

        if not self.bound:
            logging.error("Cannot start loop - socket not bound yet")
            return
        while True:
            if self._msq:
                logging.debug('ChannelQueue size: %d', self._msq.qsize())
            logging.debug('waiting data')
            # Initialize with empty values
            data = b''  # Initialize as empty bytes instead of None
            addr = ('', 0)

            try:
                # Use socket manager to receive data with built-in timeout
                data, addr = self.listen_manager.receive()
                if data:  # Only process if we actually got data
                    logging.debug('Received buffer of %d bytes from %s:%d', len(data), addr[0], addr[1])
                    logging.debug('Data: %s', data)

                    # If destination is not yet discovered, handle first packet and bind the resend socket
                    if not self.resender_bound:
                        self.handle_first(data, addr)
                    self.handle_data(data, addr)
                    self.send(data)

            except SocketTimeoutError:
                # This is normal - just continue the loop
                logging.debug('No data received within timeout period')
                continue
            except HargSocketError as e:
                # This is an actual error from our socket manager
                logging.error("Socket error in loop: %s", e)
                break
