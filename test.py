#!/usr/bin/python
# -*- coding: utf-8 -*-

from threading import Thread
import time, logging, queue, socket, select
import platform

#----------------------------------------------------------#
LOG_PATH = "./" #chemin où enregistrer les logs

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('log')
logger.setLevel(logging.DEBUG) # choisir le niveau de log : DEBUG, INFO, ERROR...

handler_debug = logging.FileHandler(LOG_PATH + "trace.log", mode="a", encoding="utf-8")
handler_debug.setFormatter(formatter)
handler_debug.setLevel(logging.DEBUG)
logger.addHandler(handler_debug)

#----------------------------------------------------------#
SOCKET_TIMEOUT= 0.2

#----------------------------------------------------------#

class ListenerSender(Thread):
    def __init__(self, sq: queue.Queue, src_iface: bytes,dst_iface: bytes, logger: logging.Logger):
        super().__init__()
        self.logger = logger
        self.sq = sq        # the queue to send what i discover about the network
        self.gw_port = 0    # source port from which gateway is sending
        self.gw_addr= b''   # to save the gateway ip adress when discovered
        self.bl_addr= b''   # to save the boiler ip address when discovered
        self.bl_port= 0     # destination port to which boiler is listening
        self.src_iface = src_iface  # network interface where to listen
        self.dst_iface = dst_iface  # network interface where to resend
        self.bound= False

        self.listen= socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)  # UDP
        self.listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.listen.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1) # gateway is broadcasting on UDP
        if platform.system() == 'Linux':
            self.listen.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, src_iface)
 
        self.resend= socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.resend.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.resend.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1) #should do only for gateway
        if platform.system() == 'Linux':
            self.resend.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, dst_iface) # bind to vlan iface
        self.resend.settimeout(SOCKET_TIMEOUT)

    def handleFirstPacket(self, data, addr):
        pass

    def reSend(self, data):
        pass

    def loop(self):
        while True:
            logger.debug('waiting data')
            data, addr = self.listen.recvfrom(1024)
            logger.info('received buffer of %d bytes from %s : %d', len(data), addr[0], addr[1])
            logger.debug('%s', data)
            
            self.handleFirstPacket(data, addr)
            self.reSend(data)

   def run(self):
        # Add your thread logic here
        pass

class GatewayListenerSender(ListenerSender):
    def __init__(self, sq: queue.Queue, src_iface: bytes,dst_iface: bytes, udp_port: int, logger: logging.Logger):
        super().__init__(sq, src_iface, dst_iface, logger)
        # Add any additional initialization logic here
        self.udp_port = udp_port    # destination port to which gateway is broadcasting

    def handleFirstPacket(self, data, addr):
        if self.bound == False: 
            logger.debug('first packet, listener not bound yet') 
            # first time we receive a packet, bind from the source port
            logger.info('discovered %s:%d', addr[0], addr[1])
            self.gw_port = addr[1]
            self.gw_addr = addr[0]
            self.sq.put('GW_ADDR:'+self.gw_addr)
            self.sq.put('GW_PORT:'+str(self.gw_port))
            self.resend.bind(('', self.gw_port))
            logger.debug('sender bound to port: %d', self.gw_port)
            self.bound = True

    def reSend(self, data):
		#to act as the gateway, we rebroadcast the udp frame
        logger.debug('resending %d bytes to %s : %d', len(data), self.dst_iface.decode(), self.udp_port)
        if platform.system() == 'Darwin':
            #on Darwin, for simulation, we send to port+1
            self.resend.sendto(data, ('<broadcast>', self.udp_port+1) )
        else:
            self.resend.sendto(data, ('<broadcast>', self.udp_port) )
        logger.info('resent %d bytes to %s : %d', len(data), self.dst_iface.decode(), self.udp_port)

     def run(self):
        logger.info('GatewayListenerSender started')
        self.listen.bind( ('',self.udp_port) )
        logger.debug('listener bound to %s, port %d', self.src_iface.decode(), self.udp_port)

        self.loop()

class BoilerListenerSender(ListenerSender):
    def __init__(self, sq: queue.Queue, src_iface: bytes,dst_iface: bytes, logger: logging.Logger):
        super().__init__(sq, src_iface, dst_iface, logger)
        # Add any additional initialization logic here
        self.rq = queue.Queue()

    def handleFirstPacket(self, data, addr):
        if self.bound == False: 
            logger.debug('first packet, listener not bound yet') 
            # first time we receive a packet, bind from the source port
            logger.info('discovered %s:%d', addr[0], addr[1])
            self.bl_addr = addr[0]
            self.bl_port = addr[1]
            #self.sq.put('BL_ADDR:'+self.bl_addr)
            #self.sq.put('BL_PORT:'+str(self.bl_port))
            self.resend.bind(('', self.bl_port))
            logger.debug('sender bound to port: %d', self.bl_port)
            self.bound = True

    def reSend(self, data):
        logger.debug('resending %d bytes to %s : %d', len(data), self.gw_addr.decode(), self.gw_port)
        if platform.system() == 'Darwin':
            # on Darwin, for simulation, we send to port+1
            self.resend.sendto(data, (self.gw_addr, self.gw_port + 1))
        else:
            self.resend.sendto(data, (self.gw_addr, self.gw_port))
        logger.info('resent %d bytes to %s : %d', len(data), self.gw_addr.decode(), self.gw_port)

    def run(self):
        logger.info('BoilerListenerSender started')
        while self.gw_port == 0:
            self.handleReceiveQueue()

        self.listen.bind( ('',self.gw_port) )
        logger.debug('listener bound to %s, port %d', self.src_iface.decode(), self.gw_port)

        self.loop()

    def getReceiveQueue(self):
        return self.rq
    def handleReceiveQueue(self):
        try:
            msg = self.rq.get(block=True, timeout=10)
            logger.debug('BoilerListenerSender: received %s', msg)
            if msg.startswith('GW_ADDR:'):
                self.gw_addr = msg.split(':')[1]
                logger.debug('BoilerListenerSender: gw_addr=%s', self.gw_addr)
            elif msg.startswith('GW_PORT:'):
                self.gw_port = int(msg.split(':')[1])
                logger.debug('BoilerListenerSender: gw_port=%d', self.gw_port)
            elif msg.startswith('BL_ADDR:'):
                self.bl_addr = msg.split(':')[1]
                logger.debug('BoilerListenerSender: bl_addr=%s', self.bl_addr)
            elif msg.startswith('BL_PORT:'):
                self.bl_port = int(msg.split(':')[1])
                logger.debug('BoilerListenerSender: bl_port=%d', self.bl_port)
            else:
                logger.debug('BoilerListenerSender: unknown message %s', msg)

        except queue.Empty:
            logger.debug('BoilerListenerSender: no message received')
            pass
#----------------------------------------------------------#
sq= queue.Queue()
bls= BoilerListenerSender(sq, b'en0', b'lo0', logger)
gls= GatewayListenerSender(bls.getReceiveQueue(), b'lo0', b'en0', 35601, logger)
bls.start()
gls.start()

