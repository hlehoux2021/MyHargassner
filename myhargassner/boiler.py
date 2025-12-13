"""
This module implements the boiler proxy
"""

# Standard library imports
import logging
from typing import Tuple

# Third party imports
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

class BoilerListenerSender(ListenerSender):
    """
    This class implements the boiler proxy
    """

    def __init__(self, appconfig: AppConfig, communicator: PubSub, delta: int = 0):
        # initiate a ListenerSender from bl_iface to gw_iface
        # Note: bl_iface is configured as IP address (10.0.0.1) to avoid SO_BINDTODEVICE issues
        # Use IP address for listening socket to avoid SO_BINDTODEVICE issues
        #super().__init__(appconfig, communicator, appconfig.bl_iface(), appconfig.gw_iface())
        bl_ip = bytes('10.0.0.1', 'ascii')

        super().__init__(appconfig, communicator, bl_ip, appconfig.gw_iface() )
        # Add any additional initialization logic here
        self.delta = delta

    def publish_discovery(self, addr):
        """
        This method publishes the discovery of the boiler.
        It sends the boiler address and port to the shared queue.
        """
        logging.info('BoilerListenerSender discovered boiler %s:%d', addr[0], addr[1])
        self.bl_port = addr[1]
        self.bl_addr = addr[0].encode('utf-8')

        logging.info('Publishing Boiler info on channel %s', self._channel)
        self._com.publish(self._channel, f"BL_ADDR:{addr[0]}")
        self._com.publish(self._channel, f"BL_PORT:{self.bl_port}")

    def get_resender_port(self) -> Tuple[int, int]:
        """
        Get the base port number for the resender socket.
        The boiler resends from the port it was discovered on.

        Returns:
            int: Base port number (delta handling done by SocketManager)
        """
        logging.debug('Getting boiler resend port: %d', self.bl_port)
        return self.bl_port, 0

    def send(self, data: bytes) -> None:
        """Send data to the gateway using platform-aware socket management.
        
        Args:
            data: The bytes to send

        Raises:
            SocketSendError: If sending fails
            SocketTimeoutError: If send times out
            InterfaceError: If interface specification is invalid
        """
        try:
            # Decode gateway address for sending
            gw_addr = self.gw_addr.decode('utf-8')
            # Use platform-aware sending with delta
            self.send_manager.send_with_delta(
                data=data,
                port=self.gw_port,
                delta=0, # No delta adjustment needed here we send to port 50000
                dest=gw_addr
            )
            logging.debug('Successfully sent %d bytes to gateway', len(data))
        except (SocketSendError, SocketTimeoutError, InterfaceError) as e:
            logging.error('Failed to send data to gateway: %s', str(e))
            raise

    def discover(self):
        """ This method discovers the gateway ip address and port. ip address and port."""
        logging.info('BoilerListenerSender discovering gateway')
        self._msq = self._com.subscribe(self._channel, self.name())
        while self.gw_port == 0 and not self._shutdown_requested:
            self.handle()
        if self._shutdown_requested:
            logging.info('BoilerListenerSender: Shutdown requested during discovery')
        else:
            logging.info('BoilerListenerSender received gateway information %s:%d', self.gw_addr, self.gw_port)
        #unsubscribe from the channel to avoid receiving further messages
        logging.debug('BoilerListenerSender unsubscribe from channel %s', self._channel)
        self._com.unsubscribe(self._channel,self._msq)
        self._msq = None  # Clear the message queue reference

    def bind(self) -> None:
        """Bind the listener socket using platform-specific binding.
        
        The binding details are handled by the socket manager, which takes care of:
        - Platform-specific binding (IP vs interface)
        - Port delta calculations for same-machine scenarios
        - Input validation
        
        Raises:
            SocketBindError: If binding fails
            InterfaceError: If interface configuration is invalid
        """
        try:
            logging.debug('Binding listener (gw_port=%d, delta=%d)', self.gw_port, self.delta)
            # Let socket manager handle platform-specific binding
            self.listen_manager.bind_with_delta(
                port=self.gw_port,
                # if same machine we will bind to 50000-100
                delta=-self.delta,
                broadcast=False  # No broadcast for boiler listener
            )
            self.setbound()
            logging.log(15, 'BoilerListener bound successfully (gw_port=%d, delta=%d)', self.gw_port, self.delta)
        except (SocketBindError, InterfaceError) as e:
            logging.error('Failed to bind listener: %s', str(e))
            raise
    def handle_data(self, data: bytes, addr: tuple):
        """handle udp data"""
        _str: str = ''
        _subpart: str = ''
        _str_parts: list[str] = []

        logging.debug('handle_data::received %d bytes from %s:%d ==>%s',
                      len(data), addr[0], addr[1], data.decode())
        if data.startswith(b'\x00\x02\x48\x53\x56'):
            logging.info('HSV discovered')
            logging.info('HSV=%s',data[2:32].decode())
            # we do not publish HSV as it is not used by other components
            #self._com.publish(self._channel, f"HSV££{data[2:32].decode()}")
            logging.info('SYS=%s',data[len(data)-16:len(data)].decode())
            self._com.publish(self._channel, f"SYS££{data[len(data)-16:len(data)].decode()}")

class ThreadedBoilerListenerSender(ThreadedListenerSender):
    """
    This class implements a Thread to run the boiler proxy
    """
    _bls: BoilerListenerSender
    def __init__(self, appconfig: AppConfig, communicator: PubSub, delta: int = 0):
        """
        Initialize the threaded boiler listener.

        Args:
            appconfig: Application configuration
            communicator: PubSub instance for inter-component communication
            delta: Port delta for same-machine scenarios
        """
        self._bls = BoilerListenerSender(appconfig, communicator, delta)
        super().__init__(self._bls, 'BoilerListener')

    def run(self):
        """
        Run the boiler listener.
        Boiler needs to discover the gateway address before it can bind and listen.
        """
        logging.info('BoilerListenerSender started')
        self._bls.discover()
        if not self._bls.is_shutdown_requested:
            self._bls.bind()
            self._bls.loop()
        logging.info('BoilerListenerSender exiting')
