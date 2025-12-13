"""
This module implements the gateway listener.
It discovers the IGW when receiving UDP broadcast messages
and forwards messages from the IGW to the boiler.
"""

# Standard library imports
import logging
from typing import Annotated, Tuple

# Third party imports
import annotated_types
from myhargassner.pubsub.pubsub import PubSub

# Project imports
from myhargassner.appconfig import AppConfig
from myhargassner.core import ListenerSender, ThreadedListenerSender
from myhargassner.socket_manager import (
    SocketSendError,
    SocketTimeoutError,
    SocketBindError,
    InterfaceError
)

# pylint: disable=logging-fstring-interpolation

class GatewayListenerSender(ListenerSender):
    """
    This class extends ListenerSender class to implement the gateway listener.
    """
    udp_port: Annotated[int, annotated_types.Gt(0)]

    def __init__(self, appconfig: AppConfig, communicator: PubSub, delta: int = 0):
        """
        Initialize the gateway listener.

        Args:
            appconfig (AppConfig): Application configuration
            communicator (PubSub): Communication instance
            delta (int, optional): Port offset for same-machine scenarios. Defaults to 0.
        """
        # initiate a ListenerSender from gw_iface to bl_iface
        super().__init__(appconfig, communicator, appconfig.gw_iface(), appconfig.bl_iface())
        # Add any additional initialization logic here

        self.udp_port = self._appconfig.udp_port()  # destination port to which gateway is broadcasting
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

    def get_resender_port(self) -> Tuple[int, int]:
        """
        Get the base port number for the resender socket.
        The gateway resends from the port it was discovered on.

        Returns:
            int: Base port number (delta handling done by SocketManager)
        """
        logging.debug('Getting gateway resend port: %d delta:%d', self.gw_port, -self.delta)
        return self.gw_port, -self.delta

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
                # if same machine we will send to 35601 + 100
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
                delta=0,  # Gateway listens on the actual port 35601, no adjustment needed
                broadcast=True  # Gateway uses broadcast for discovery
            )
            self.bound = True
            logging.debug('Gateway listener bound successfully')
        except (SocketBindError, InterfaceError) as e:
            logging.error('Failed to bind listener: %s', str(e))
            raise

    def handle_data(self, data: bytes, addr: tuple):
        """Handle UDP data from the gateway.

        Publishes discovery information (HargaWebApp, SN) to the bootstrap channel.
        Note: GatewayListener does NOT request system restart - that is handled by TelnetProxy.
        """
        _str: str = ''
        _subpart: str = ''
        _str_parts: list[str] = []

        logging.debug('handle_data::received %d bytes from %s:%d ==>%s',
                      len(data), addr[0], addr[1], data.decode())

        _str = data.decode()
        _str_parts = _str.split('\r\n')
        for part in _str_parts:
            logging.info('UDP received: %s', part)
            if part.startswith('HargaWebApp'):
                _subpart = part[13:]  # Extract portion after the key
                logging.info('HargaWebApp££%s published to %s', _subpart, self._channel)
                self._com.publish(self._channel, f"HargaWebApp££{_subpart}")

            if part.startswith('SN:'):
                _subpart = part[3:]  # Extract portion after the key
                logging.info('SN: [%s]', _subpart)
                self._com.publish(self._channel, f"SN££{_subpart}")

class ThreadedGatewayListenerSender(ThreadedListenerSender):
    """This class implements a Thread to run the gateway."""

    def __init__(self, appconfig: AppConfig, communicator: PubSub, delta=0):
        """
        Initialize the threaded gateway listener.

        Args:
            appconfig: Application configuration
            communicator: PubSub instance for inter-component communication
            delta: Port delta for same-machine scenarios
        """
        gls = GatewayListenerSender(appconfig, communicator, delta)
        super().__init__(gls, 'GatewayListener')

    def run(self):
        """
        Run the gateway listener.
        Gateway doesn't need discovery - it directly binds and listens for broadcasts.
        """
        logging.info('GatewayListenerSender started')
        self._listener_sender.bind()
        self._listener_sender.loop()
