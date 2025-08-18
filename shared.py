"""
 This module contains classes shared by boiler, gateway and telnetproxy
"""
from queue import Empty
import socket
import platform
import logging
from typing import Annotated, Union, Optional, Callable, Tuple

import annotated_types

from pubsub.pubsub import PubSub, ChanelQueue, ChanelPriorityQueue

#----------------------------------------------------------#
BUFF_SIZE = 1024
UDP_LISTENER_TIMEOUT = 5  # Timeout for UDP listener

# Runtime check and setting with warning suppressions
if not hasattr(socket, 'SO_BINDTODEVICE'):
    socket.SO_BINDTODEVICE = 25  # type: ignore[attr-defined] # pylint: disable=attribute-defined-outside-init
#----------------------------------------------------------#

class HargInfo():
    """ a data class to store the HargInfo"""
    gw_webapp: str = ''  # HargaWebApp version eg 6.4.1
    gw_sn: str = ''       # IGW serial number


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


class ChanelReceiver(NetworkData):
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
            iterator = self._msq.listen(timeout=3.0)  # 1 second timeout
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
                msg = msg.decode('utf-8')
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

    def loop(self) -> None:
        """
        This method is the main loop of the class.
        It should be overridden in subclasses to implement specific behavior.
        """
        logging.error("loop() not implemented in %s", self.name())
        raise NotImplementedError("Subclasses must implement this method")

class ListenerSender(ChanelReceiver):
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

    @staticmethod
    def _is_ip_address(ip: str) -> bool:
        """Check if a string is a valid IPv4 address"""
        try:
            parts = ip.split('.')
            return len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts)
        except (AttributeError, TypeError, ValueError):
            return False

    def __init__(self, communicator: PubSub, src_iface: bytes, dst_iface: bytes) -> None:
        super().__init__(communicator)
        self.src_iface = src_iface  # network interface where to listen
        self.dst_iface = dst_iface  # network interface where to resend
        self.bound = False
        self.resender_bound = False

        # Initialize sockets without type annotations
        self.listen = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.listen.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.listen.settimeout(UDP_LISTENER_TIMEOUT)  # Set a timeout for the listener
        logging.debug('system=%s', platform.system())

        # Configure listen socket
        if platform.system() == 'Linux':
            # Linux: use SO_BINDTODEVICE
            self.listen.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, src_iface) # type: ignore[attr-defined]
            logging.debug('listen to device %s', src_iface)
        elif platform.system() == 'Darwin':
            # macOS: bind to interface IP
            src_ip: str
            src_ip = src_iface.decode('utf-8')
            if not self._is_ip_address(src_ip):
                logging.error("On macOS, please provide the IP address instead of interface name")
                logging.error("For example: use '192.168.1.100' instead of 'en4'")
                raise ValueError(f"Invalid IP address for macOS interface: {src_ip}")
            self.src_ip = src_ip  # Store for later binding
            logging.debug('configured listen IP %s', src_ip)

        # Configure resend socket
        self.resend = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.resend.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.resend.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        if platform.system() == 'Linux':
            # Linux: use SO_BINDTODEVICE
            self.resend.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, dst_iface) # type: ignore[attr-defined]
        elif platform.system() == 'Darwin':
            # macOS: bind to interface IP
            dst_ip: str
            dst_ip = dst_iface.decode('utf-8')
            if not self._is_ip_address(dst_ip):
                logging.error("On macOS, please provide the IP address instead of interface name")
                logging.error("For example: use '192.168.1.100' instead of 'en4'")
                raise ValueError(f"Invalid IP address for macOS interface: {dst_ip}")
            self.dst_ip = dst_ip  # Store for later binding
            logging.debug('configured resend IP %s', dst_ip)

    def handle_first(self, data: bytes, addr: Tuple[str, int]) -> None:
        """
        This method handles the discovery of caller's ip address and port.
        """
        logging.debug('first packet, resender not bound yet')
        self.publish_discovery(addr)  # Call the method to publish discovery

        # first time we receive a packet, bind from the source port
        if self.resender_bound:
            logging.debug('resender already bound, skipping bind operation')
        else:
            try:
                self.resend.bind(self.get_resender_binding())
                self.resender_bound = True
                logging.debug('resender bound')
            except OSError as e:
                logging.error('Failed to bind resender: %s', str(e))
                raise

    def get_resender_binding(self) -> Tuple[str, int]:
        """
        This method returns the binding details for the resender.
        """
        logging.error("get_resender_binding() not implemented in %s", self.name())
        raise NotImplementedError("Subclasses must implement this method")

    def send(self, data: bytes) -> None:
        """
        This method resends received data to the destination.
        This method must be implemented in the child class.
        """
        logging.error("send() not implemented in %s", self.name())
        raise NotImplementedError("Subclasses must implement this method")

    def handle_data(self, data: bytes, addr: Tuple[str, int]) -> None:
        """
        This method handles received data.
        This method must be implemented in the child class.
        """
        logging.error("handle_data() not implemented in %s", self.name())
        raise NotImplementedError("Subclasses must implement this method")

    def publish_discovery(self, addr: Tuple[str, int]) -> None:
        """
        This method publishes the discovery of the Listener (gateway or boiler) to the Channel Queue.
        It sends the gateway/boiler address and port to the shared queue.
        """
        logging.error("publish_discovery() not implemented in %s", self.name())
        raise NotImplementedError("Subclasses must implement this method")

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
                # Set socket timeout
                self.listen.settimeout(3.0)  # 1 second timeout
                data, addr = self.listen.recvfrom(BUFF_SIZE)
                if data:  # Only process if we actually got data
                    logging.debug('received buffer of %d bytes from %s : %d', len(data), addr[0], addr[1])
                    logging.debug('%s', data)
                    # if destination is not yet discovered, handle first packet and bind the resend socket
                    if not self.resender_bound:
                        self.handle_first(data, addr)
                    self.handle_data(data, addr)
                    self.send(data)
            except socket.timeout:
                # This is normal - just continue the loop
                logging.debug('No data received within timeout period')
                continue
            except socket.error as e:
                # This is an actual error
                logging.error("Socket error in loop: %s", e)
                break
