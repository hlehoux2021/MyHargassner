"""
 This module contains classes shared by boiler, gateway and telnetproxy
"""
from queue import Queue, Empty
import socket
import platform
import logging
from typing import Annotated
import annotated_types

#----------------------------------------------------------#
BUFF_SIZE= 1024
UDP_LISTENER_TIMEOUT = 5  # Timeout for UDP listener  

# Add socket constants that might not be defined on all systems
if not hasattr(socket, 'SO_BINDTODEVICE'):
    socket.SO_BINDTODEVICE = 25  # From Linux <socket.h>

#----------------------------------------------------------#

class HargInfo():
    """ a data class to store the HargInfo"""
    gw_webapp: str = ''  # HargaWebApp version eg 6.4.1
    gw_sn: str = ''       # IGW serial number


class SharedData():
    """
    This class is used to share data between the gateway and the boiler.
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

class SharedDataReceiver(SharedData):
    """
    This class extends SharedData class with a queue to receive data from
    and a handler to process the received data.
    """
    rq: Queue

    def __init__(self):
        super().__init__()
        self.rq = Queue()

    def handle(self):
        """
        This method handles received messages from the queue.
        """
        try:
            msg = self.rq.get(block=True, timeout=10)
            logging.debug('handleReceiveQueue: received %s', msg)
            if msg.startswith('GW_ADDR:'):
                self.gw_addr = bytes(msg.split(':')[1],'ascii')
                logging.debug('handleReceiveQueue: gw_addr=%s', self.gw_addr)
            elif msg.startswith('GW_PORT:'):
                self.gw_port = int(msg.split(':')[1])
                logging.debug('handleReceiveQueue: gw_port=%d', self.gw_port)
            elif msg.startswith('BL_ADDR:'):
                self.bl_addr = bytes(msg.split(':')[1],'ascii')
                logging.debug('handleReceiveQueue: bl_addr=%s', self.bl_addr)
            elif msg.startswith('BL_PORT:'):
                self.bl_port = int(msg.split(':')[1])
                logging.debug('handleReceiveQueue: bl_port=%d', self.bl_port)
            else:
                logging.debug('handleReceiveQueue: unknown message %s', msg)
        except Empty:
            logging.debug('handleReceiveQueue: no message received')

    def queue(self) -> Queue:
        """
        This method returns the queue to receive data from.
        """
        return self.rq

class ListenerSender(SharedDataReceiver):
    """
    This class extends SharedDataReceiver class with a socket to listen
    and a socket to resend data.
    """
    listen: socket.socket
    resend: socket.socket
    src_iface: bytes
    dst_iface: bytes
    sq: Queue
    bound: bool = False
    resender_bound: bool = False  # Flag to indicate if the resend socket is bound
    @staticmethod
    def _is_ip_address(ip: str) -> bool:
        """Check if a string is a valid IPv4 address"""
        try:
            parts = ip.split('.')
            return len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts)
        except (AttributeError, TypeError, ValueError):
            return False

    def __init__(self, sq: Queue, src_iface: bytes, dst_iface: bytes):
        super().__init__()
        self.sq = sq        # the queue to send what i discover about the network
        self.src_iface = src_iface  # network interface where to listen
        self.dst_iface = dst_iface  # network interface where to resend
        self.bound = False

        self.listen = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.listen.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.listen.settimeout(UDP_LISTENER_TIMEOUT)  # Set a timeout for the listener
        logging.debug(f'system={platform.system()}')
        
        # Configure listen socket
        if platform.system() == 'Linux':
            # Linux: use SO_BINDTODEVICE
            self.listen.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, src_iface)
            logging.debug('listen to device %s', src_iface)
        elif platform.system() == 'Darwin':
            # macOS: bind to interface IP
            src_ip = src_iface.decode('utf-8') if isinstance(src_iface, bytes) else src_iface
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
            self.resend.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, dst_iface)
        elif platform.system() == 'Darwin':
            # macOS: bind to interface IP
            dst_ip = dst_iface.decode('utf-8') if isinstance(dst_iface, bytes) else dst_iface
            if not self._is_ip_address(dst_ip):
                logging.error("On macOS, please provide the IP address instead of interface name")
                logging.error("For example: use '192.168.1.100' instead of 'en4'")
                raise ValueError(f"Invalid IP address for macOS interface: {dst_ip}")
            self.dst_ip = dst_ip  # Store for later binding
            logging.debug('configured resend IP %s', dst_ip)
        

    def handle_first(self, data, addr):
        """
        This method handles the discovery of caller's ip address and port.
        This method must be implemented in the child class.
         """

    def send(self, data):
        """
        This method resends received data to the destination.
        This method must be implemented in the child class.
        """

    def handle_data(self, data: bytes, addr: tuple):
        """
        This method handles received data.
        This method must be implemented in the child class.
        """
    def loop(self):
        """
        This method is the main loop of the class.
        """
        data: bytes
        addr: tuple
        
        if not self.bound:
            logging.error("Cannot start loop - socket not bound yet")
            return
            
        while True:
            logging.debug('waiting data')
            data = None
            addr = ('', 0)
            try:
                data, addr = self.listen.recvfrom(BUFF_SIZE) # Blocks for up to UDP_LISTENER_TIMEOUT seconds
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
