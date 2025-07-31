"""
This module implements the gateway listener
it discovers the IGW when receiving broadcasted udp messages
it forwards messages from the IGW to the boiler
"""
import logging
import platform
from queue import Queue

from threading import Thread
from typing import Annotated
import annotated_types

from shared import ListenerSender

class GatewayListenerSender(ListenerSender):
    """
    This class extends ListenerSender class to implement the gateway listener.
    """
    udp_port: Annotated[int, annotated_types.Gt(0)]
    _mq: Queue

    def __init__(self, mq: Queue, sq: Queue, src_iface: bytes,dst_iface: bytes, udp_port: int):
        super().__init__(sq, src_iface, dst_iface)
        # Add any additional initialization logic here
        self.udp_port = udp_port    # destination port to which gateway is broadcasting
        self._mq = mq
    def handle_first(self, data, addr):
        """
        This method handles the discovery of caller's ip address and port.
        """
        if self.bound is False:
            logging.debug('first packet, listener not bound yet')
            # first time we receive a packet, bind from the source port
            logging.info('discovered %s:%d', addr[0], addr[1])
            self.gw_port = addr[1]
            self.gw_addr = addr[0]
            self.sq.put('GW_ADDR:'+self.gw_addr)
            self.sq.put('GW_PORT:'+str(self.gw_port))
            if platform.system() == 'Darwin':
                self.resend.bind(('', self.gw_port+1))
            else:
                self.resend.bind(('', self.gw_port))
            logging.debug('sender bound to port: %d', self.gw_port)
            self.bound = True

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
                      len(data), self.dst_iface.decode(), self.udp_port)
        if platform.system() == 'Darwin':
            #on Darwin, for simulation, we send to port+1
            self.resend.sendto(data, ('<broadcast>', self.udp_port+1) )
        else:
            self.resend.sendto(data, ('<broadcast>', self.udp_port) )
        logging.debug('resent %d bytes to %s : %d',
                     len(data), self.dst_iface.decode(), self.udp_port)

    def bind(self):
        """ This method binds the listener mimicking the gateway."""
        self.listen.bind( ('',self.udp_port) )
        logging.debug('listener bound to %s, port %d', self.src_iface.decode(), self.udp_port)

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
                self._mq.put('HargaWebApp££'+_subpart)

            if part.startswith('SN:'):
                _subpart = part[3:]  # Extract portion after the key
                logging.info('SN: [%s]', _subpart)
                self._mq.put('SN££'+_subpart)

class ThreadedGatewayListenerSender(Thread):
    """This class implements a Thread to run the gateway."""
    gls: GatewayListenerSender

    def __init__(self, mq: Queue, sq: Queue, src_iface: bytes,dst_iface: bytes, udp_port: int):
        super().__init__(name='GatewayListener')
        self.gls= GatewayListenerSender(mq, sq, src_iface, dst_iface, udp_port)

    def queue(self) -> Queue:
        """
        This method returns the queue to receive data from.
        """
        return self.gls.queue()

    def run(self):
        logging.info('GatewayListenerSender started')
        self.gls.bind()
        self.gls.loop()
