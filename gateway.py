"""
This module implements the gateway listener
it discovers the IGW when receiving broadcasted udp messages
it forwards messages from the IGW to the boiler
"""
import logging
import platform
from queue import Queue
from pubsub.pubsub import PubSub

from threading import Thread
from typing import Annotated
import annotated_types

from shared import ListenerSender

class GatewayListenerSender(ListenerSender):
    """
    This class extends ListenerSender class to implement the gateway listener.
    """
    udp_port: Annotated[int, annotated_types.Gt(0)]
    _com: PubSub


    def __init__(self, communicator: PubSub, src_iface: bytes,dst_iface: bytes, udp_port: int, delta:int = 0):
        super().__init__(communicator, src_iface, dst_iface)
        # Add any additional initialization logic here

        # GatewayListenerSender doesn't read pubsub channel: unsubscribe immediatly 
#        logging.info('BoilerListenerSender : unsubscribe from channel %s', self._channel)
#        self._com.unsubscribe(self._channel,self._msq)
#        self._msq = None  # Clear the message queue reference

        self.udp_port = udp_port    # destination port to which gateway is broadcasting
        self.delta = delta

    def publish_discovery(self, addr):
        """
        This method publishes the discovery of the gateway.
        It sends the gateway address and port to the shared queue.
        """
        logging.info('GatewayListenerSender discovered gateway%s:%d', addr[0], addr[1])
        self.gw_port = addr[1]
        self.gw_addr = addr[0]

        logging.info('Publishing Gateway info on channel %s', self._channel)
        self._com.publish(self._channel, f"GW_ADDR:{self.gw_addr}")
        self._com.publish(self._channel, f"GW_PORT:{self.gw_port}")

    def get_resender_binding(self):
        """
        This method returns the binding details for the resender.
        """
        #todo sort usage of delta between MacOS and Linux
        if platform.system() == 'Darwin':
            # On macOS, we bind to the specific interface IP
            bind_port = self.gw_port - self.delta
            logging.debug('Binding details - IP: %s, Port: %d, Delta: %d, Original Port: %d', 
                self.dst_ip, bind_port, self.delta, self.gw_port)
            return (self.dst_ip, bind_port)
        else:
            # On Linux, we already used SO_BINDTODEVICE
            return ('', self.gw_port)



    def queue(self) -> Queue:
        """
        This method returns the queue to receive data from.
        """
        return self.queue()

    def send(self, data):
        """
        This method sends received data to the boiler.
        """
		#to act as the gateway, we rebroadcast the udp frame
        logging.debug('resending %d bytes to %s : %d',
                      len(data), self.dst_iface.decode(), self.udp_port+self.delta)
        self.resend.sendto(data, ('<broadcast>', self.udp_port+self.delta))
        logging.debug('resent %d bytes to %s : %d',
                     len(data), self.dst_iface.decode(), self.udp_port+self.delta)

    def bind(self):
        """ This method binds the listener mimicking the gateway."""
        if platform.system() == 'Darwin remove':
            # On macOS, we need to bind to the specific interface IP
            logging.debug('binding listener to IP %s, port %d', self.src_ip, self.udp_port)
            self.listen.bind((self.src_ip, self.udp_port))
            logging.debug('listener bound to IP %s, port %d', self.src_ip, self.udp_port)
        else:
            # On Linux, we already used SO_BINDTODEVICE, so we can bind to all interfaces
            logging.debug('binding listener to '', port %d', self.udp_port)
            self.listen.bind(('', self.udp_port))
            logging.debug('listener bound to '', port %d', self.udp_port)
        self.bound = True

    def handle_data(self, data: bytes, addr: tuple):
        """handle udp data
            
        """
        _str: str = None
        _subpart: str = None
        _str_parts: list[str] = None

        logging.debug('handle_data::received %d bytes from %s:%d ==>%s',
                      len(data), addr[0], addr[1], data.decode())

        _str = data.decode()
        _str_parts = _str.split('\r\n')
        for part in _str_parts:
            if part.startswith('HargaWebApp'):
                _subpart = part[13:]  # Extract portion after the key
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

    def queue(self) -> Queue:
        """
        This method returns the queue to receive data from.
        """
        return self.gls.queue()

    def run(self):
        logging.info('GatewayListenerSender started')
        self.gls.bind()
        self.gls.loop()
