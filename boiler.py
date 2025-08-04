"""
This module implements the boiler proxy
"""

import logging
from queue import Queue
from pubsub.pubsub import PubSub

import platform
from threading import Thread

from shared import ListenerSender

class BoilerListenerSender(ListenerSender):
    """
    This class implements the boiler proxy
    """

    def __init__(self, communicator: PubSub, src_iface: bytes,dst_iface: bytes, delta: int = 0):
        super().__init__(communicator, src_iface, dst_iface)
        # Add any additional initialization logic here
#        self.rq = Queue()
        self.delta = delta

    def publish_discovery(self, addr):
        """
        This method publishes the discovery of the boiler.
        It sends the boiler address and port to the shared queue.
        """
        logging.info('BoilerListenerSender discovered boiler %s:%d', addr[0], addr[1])
        self.bl_port = addr[1]
        self.bl_addr = addr[0]

        logging.info('Publishing Boiler info on channel %s', self._channel)
        self._com.publish(self._channel, f"BL_ADDR:{self.bl_addr}")
        self._com.publish(self._channel, f"BL_PORT:{self.bl_port}")


    def handle_first(self, data, addr):
        logging.debug('first packet, listener not bound yet')
        # first time we receive a packet, bind from the source port
        logging.info('Boiler discovered %s:%d', addr[0], addr[1])
        self.publish_discovery(addr)  # Call the method to publish discovery

        bind_port = self.bl_port - self.delta
        logging.debug('binding sender to %s:%d', self.bl_addr, bind_port)
        self.resend.bind((self.bl_addr, bind_port))
        logging.debug('sender bound to IP %s, port %d', self.bl_addr, bind_port)

    def send(self, data):
        logging.debug('resending %d bytes to %s : %d',
                      len(data), self.gw_addr.decode(), self.gw_port)
        self.resend.sendto(data, (self.gw_addr, self.gw_port))
        logging.debug('resent %d bytes to %s : %d',
                     len(data), self.gw_addr.decode(), self.gw_port)

    def discover(self):
        """ This method discovers the gateway ip address and port. ip address and port."""
        logging.info('BoilerListenerSender discovering gateway')
        while self.gw_port == 0:
            self.handle()
        logging.info('BoilerListenerSender discovered gateway %s:%d', self.gw_addr, self.gw_port)

    def bind(self):
        """ This method binds the listener mimicking the gateway."""
        logging.debug('BoilerListenerSender binding listener gw_port=%d delta=%d',self.gw_port, self.delta)
        if platform.system() == 'Darwin':
            # On macOS, we need to bind to the specific IP address
            bind_port= self.gw_port- self.delta
            logging.debug('binding listener to IP %s, port %d', self.src_ip, bind_port)
            self.listen.bind((self.src_ip, bind_port))
            logging.debug('listener bound to IP %s, port %d', self.src_ip, bind_port)
        else:
            # On Linux, we've already set SO_BINDTODEVICE, so we can bind to any address
            logging.debug('binding listener to '', port %d', self.gw_port)
            self.listen.bind(('', self.gw_port))
            logging.debug('listener bound to port %d', self.gw_port)
        self.bound = True  # Set this after successful binding
    def handle_data(self, data: bytes, addr: tuple):
        """handle udp data"""
        _str: str = None
        _subpart: str = None
        _str_parts: list[str] = None

        logging.debug('handle_data::received %d bytes from %s:%d ==>%s',
                      len(data), addr[0], addr[1], data.decode())
        if data.startswith(b'\x00\x02\x48\x53\x56'):
            logging.info('HSV discovered')
            logging.info('HSV=%s',data[2:32].decode())
            self._com.publish(self._channel, f"HSV££{data[2:32].decode()}")
            #self._mq.put('HSV££' + data[2:32].decode())  # Uncomment if you want to use the queue
            logging.info('SYS=%s',data[len(data)-16:len(data)].decode())
            #self._mq.put('SYS££' + data[len(data)-16:len(data)].decode())
            self._com.publish(self._channel, f"SYS££{data[len(data)-16:len(data)].decode()}")

class ThreadedBoilerListenerSender(Thread):
    """ 
    This class implements a Thread to run the boiler proxy
    """
    bls: BoilerListenerSender

    def __init__(self, communicator: PubSub, src_iface: bytes,dst_iface: bytes, delta: int = 0):
        super().__init__(name='BoilerListener')
        self.bls= BoilerListenerSender(communicator, src_iface, dst_iface, delta)

    def run(self):
        logging.info('BoilerListenerSender started')
        self.bls.discover()
        self.bls.bind()
        self.bls.loop()
