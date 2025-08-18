"""
This module implements the gateway listener.
It discovers the IGW when receiving UDP broadcast messages
and forwards messages from the IGW to the boiler.
"""
import logging
from queue import Queue
from threading import Thread
from typing import Annotated, Tuple
import annotated_types

from pubsub.pubsub import PubSub

from shared import ListenerSender
from socket_manager import (
    SocketSendError,
    SocketTimeoutError,
    SocketBindError,
    InterfaceError
)

class GatewayListenerSender(ListenerSender):
    """
    This class extends ListenerSender class to implement the gateway listener.
    """
    udp_port: Annotated[int, annotated_types.Gt(0)]

    def __init__(self, communicator: PubSub, src_iface: bytes,dst_iface: bytes, udp_port: int, delta:int = 0):
        super().__init__(communicator, src_iface, dst_iface)
        # Add any additional initialization logic here

        self.udp_port = udp_port    # destination port to which gateway is broadcasting
        self.delta = delta

    def publish_discovery(self, addr: Tuple[str, int]) -> None:
        """
        This method publishes the discovery of the gateway.
        It sends the gateway address and port to the shared queue.
        
        Args:
            addr: Tuple of (ip_address: str, port: int)
        """
        logging.info('GatewayListenerSender discovered gateway %s:%d', addr[0], addr[1])
        self.gw_port = addr[1]
        self.gw_addr = addr[0].encode('utf-8')

        logging.info('Publishing Gateway info on channel %s', self._channel)
        self._com.publish(self._channel, f"GW_ADDR:{addr[0]}")
        self._com.publish(self._channel, f"GW_PORT:{addr[1]}")

    def get_resender_port(self) -> int:
        """
        Get the base port number for the resender socket.
        The gateway resends from the port it was discovered on.

        Returns:
            int: Base port number (delta handling done by SocketManager)
        """
        logging.debug('Getting gateway resend port: %d', self.gw_port)
        return self.gw_port



    def queue(self) -> Queue:
        """
        This method returns the queue to receive data from.
        """
        return self.queue()

    def send(self, data: bytes) -> None:
        """
        Send received data to the boiler with error handling.
        Rebroadcasts the UDP frame to act as the gateway.

        Args:
            data: The bytes to send

        Raises:
            SocketSendError: If sending fails
            SocketTimeoutError: If send times out
            InterfaceError: If interface specification is invalid
        """
        try:
            self.send_manager.send_with_delta(
                data=data,
                port=self.udp_port,
                delta=self.delta
            )
            logging.debug('Successfully sent %d bytes', len(data))
        except (SocketSendError, SocketTimeoutError, InterfaceError) as e:
            logging.error('Failed to send data: %s', str(e))
            raise

    def bind(self) -> None:
        """
        Bind the listener socket using platform-specific binding.
        The gateway listens on the broadcast port directly (no delta adjustment needed).
        Platform-specific details are handled by SocketManager:
        - On macOS: Validates and binds to specific IP address
        - On Linux: Uses interface name with SO_BINDTODEVICE
        
        Raises:
            SocketBindError: If binding fails
            InterfaceError: If interface configuration is invalid
        """
        try:
            logging.debug('Binding gateway listener on port %d', self.udp_port)
            # Use bind_with_delta with delta=0 since gateway listens on the actual port
            self.listen_manager.bind_with_delta(
                port=self.udp_port,
                delta=0  # Gateway listens on the actual port, no adjustment needed
            )
            self.bound = True
            logging.debug('Gateway listener bound successfully')
        except (SocketBindError, InterfaceError) as e:
            logging.error('Failed to bind listener: %s', str(e))
            raise

    def handle_data(self, data: bytes, addr: tuple):
        """handle udp data
            
        """
        _str: str = ''
        _subpart: str = ''
        _str_parts: list[str] = []

        logging.debug('handle_data::received %d bytes from %s:%d ==>%s',
                      len(data), addr[0], addr[1], data.decode())

        _str = data.decode()
        _str_parts = _str.split('\r\n')
        for part in _str_parts:
            if part.startswith('HargaWebApp'):
                _subpart = part[13]  # Extract portion after the key
                logging.info('HargaWebApp££%s', _subpart)
                self._com.publish(self._channel, f"HargaWebApp££{_subpart}")

            if part.startswith('SN:'):
                _subpart = part[3:]  # Extract portion after the key
                logging.info('SN: [%s]', _subpart)
                self._com.publish(self._channel, f"SN££{_subpart}")

class ThreadedGatewayListenerSender(Thread):
    """This class implements a Thread to run the gateway."""
    gls: GatewayListenerSender

    def __init__(self, communicator: PubSub, src_iface: bytes,dst_iface: bytes, udp_port: int, delta=0):
        super().__init__(name='GatewayListener')
        self.gls= GatewayListenerSender(communicator, src_iface, dst_iface, udp_port, delta)

    def run(self):
        logging.info('GatewayListenerSender started')
        self.gls.bind()
        self.gls.loop()
