"""
This module implements the boiler proxy
"""

import logging
from queue import Queue
import platform
from threading import Thread

from shared import ListenerSender

class BoilerListenerSender(ListenerSender):
    """
    This class implements the boiler proxy
    """
    _mq: Queue
    def __init__(self, mq: Queue, sq: Queue, src_iface: bytes,dst_iface: bytes, delta: int = 0):
        super().__init__(sq, src_iface, dst_iface)
        # Add any additional initialization logic here
        self.rq = Queue()
        self._mq = mq
        self.delta = delta
    def handle_first(self, data, addr):
        logging.debug('BoilerListenerSender first packet, listener not bound yet')
        # first time we receive a packet, bind from the source port
        logging.info('Boiler discovered %s:%d', addr[0], addr[1])
        self.bl_addr = addr[0]
        self.bl_port = addr[1]
        self.sq.put('BL_ADDR:'+self.bl_addr)
        self.sq.put('BL_PORT:'+str(self.bl_port))
        self.resend.bind((self.bl_addr, self.bl_port))
        logging.debug('sender bound to IP %s, port %d', self.bl_addr, self.bl_port)
#        if platform.system() == 'Darwin':
#            # On macOS, bind to specific interface IP
#            self.resend.bind((self.dst_ip, self.bl_port))
#            logging.debug('sender bound to IP %s, port %d', self.dst_ip, self.bl_port)
#        else:
#            # On Linux, we've already set SO_BINDTODEVICE
#            self.resend.bind(('', self.bl_port))
#            logging.debug('sender bound to port: %d', self.bl_port)


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
            self._mq.put('HSV££' + data[2:32].decode())
            logging.info('Code systeme=%s',data[len(data)-16:len(data)].decode())
            self._mq.put('SYS££' + data[len(data)-16:len(data)].decode())

class ThreadedBoilerListenerSender(Thread):
    """
    This class implements a Thread to run the boiler proxy
    """
    bls: BoilerListenerSender

    def __init__(self, mq: Queue, sq: Queue, src_iface: bytes,dst_iface: bytes, delta: int = 0):
        super().__init__(name='BoilerListener')
        self.bls= BoilerListenerSender(mq, sq, src_iface, dst_iface, delta)

    def queue(self) -> Queue:
        """
        This method returns the queue to receive data from.
        """
        return self.bls.queue()

    def run(self):
        logging.info('BoilerListenerSender started')
        self.bls.discover()
        self.bls.bind()
        self.bls.loop()
