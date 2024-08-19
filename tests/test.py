#!/usr/bin/python
# -*- coding: utf-8 -*-

from threading import Thread
import time, logging, queue, socket, select
import platform
import argparse


#----------------------------------------------------------#
LOG_PATH = "./" #chemin où enregistrer les logs

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
logger = logging.getLogger('log')
logger.setLevel(logging.DEBUG) # choisir le niveau de log : DEBUG, INFO, ERROR...

handler_debug = logging.FileHandler(LOG_PATH + "trace.log", mode="a", encoding="utf-8")
handler_debug.setFormatter(formatter)
handler_debug.setLevel(logging.DEBUG)
logger.addHandler(handler_debug)


#----------------------------------------------------------#
SOCKET_TIMEOUT= 0.2
BUFF_SIZE= 1024

src_iface = b'eth0' # network interface connected to the gateway
dst_iface = b'eth1' # network interface connected to the boiler
udp_port = 35601 # destination port to which gateway is broadcasting

def parse_command_line():
    parser = argparse.ArgumentParser(description='Command line parser')
    parser.add_argument('-s', '--src_iface', type=str, help='Source interface')
    parser.add_argument('-d', '--dst_iface', type=str, help='Destination interface')
    parser.add_argument('-p', '--port', type=int, help='Source port')

    args = parser.parse_args()
    return args

# Utilisation du parseur de ligne de commande
command_line_args = parse_command_line()

if command_line_args.src_iface is not None:
    src_iface = command_line_args.src_iface

if command_line_args.dst_iface is not None:
    dst_iface = command_line_args.dst_iface

if command_line_args.port is not None:
    udp_port = command_line_args.port

#----------------------------------------------------------#

class QueueReceiver(queue.Queue):
    def __init__(self):
        super().__init__()
        self.gw_port = 0    # source port from which gateway is sending
        self.gw_addr= b''   # to save the gateway ip adress when discovered
        self.bl_addr= b''   # to save the boiler ip address when discovered
        self.bl_port= 0     # destination port to which boiler is listening

    def handleReceiveQueue(self):
        try:
            msg = self.get(block=True, timeout=10)
            logger.debug('handleReceiveQueue: received %s', msg)
            if msg.startswith('GW_ADDR:'):
                self.gw_addr = bytes(msg.split(':')[1],'ascii')
                logger.debug('handleReceiveQueue: gw_addr=%s', self.gw_addr)
            elif msg.startswith('GW_PORT:'):
                self.gw_port = int(msg.split(':')[1])
                logger.debug('handleReceiveQueue: gw_port=%d', self.gw_port)
            elif msg.startswith('BL_ADDR:'):
                self.bl_addr = bytes(msg.split(':')[1],'ascii')
                logger.debug('handleReceiveQueue: bl_addr=%s', self.bl_addr)
            elif msg.startswith('BL_PORT:'):
                self.bl_port = int(msg.split(':')[1])
                logger.debug('handleReceiveQueue: bl_port=%d', self.bl_port)
            else:
                logger.debug('handleReceiveQueue: unknown message %s', msg)
        except queue.Empty:
            logger.debug('handleReceiveQueue: no message received')

class TelnetProxy(Thread, QueueReceiver):
    def __init__(self, src_iface, dst_iface, port):
        super().__init__()
        QueueReceiver.__init__(self)

        self.src_iface = src_iface
        self.dst_iface = dst_iface
        self.port = port
        self.listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if platform.system() == 'Linux':
            self.listen.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self.src_iface)
        self.listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def run(self):
        logger.info('telnet proxy started: %s , %s', self.src_iface, self.dst_iface)

        logger.debug('telnet binding to port %s', self.port)
        self.listen.bind(('', self.port))

        logger.debug('telnet listening')
        self.listen.listen()

        logger.debug('telnet accepting a connection')
        self.telnet, self.addr = self.listen.accept()
        logger.info('telnet connection from %s:%d accepted', self.addr[0], self.addr[1])

        # remember the source port from which gateway is telneting
        self.gwt_port = self.addr[1]
 
        # we will now create the socket to resend the telnet request
        self.resend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.resend.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.resend.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.resend.settimeout(SOCKET_TIMEOUT)

        # wait for the boiler address and port to be discovered
        while (self.bl_port == 0) or (self.bl_addr == b''):
                logger.debug('waiting for the discovery of the boiler address and port')  
                self.handleReceiveQueue()

        # boiler is listening on port 23
        logger.info('telnet connecting to %s on port 23', self.bl_addr.decode())
        self.resend.connect( (self.bl_addr, 23) )

        self.socket_list = [self.telnet, self.resend]
        while True:
            logger.debug('telnet waiting data')
            self.read_sockets, self.write_sockets, self.error_sockets = select.select(self.socket_list, [], [])
            for self.sock in self.read_sockets:
                if self.sock == self.telnet:
                    # so we received a request
                    self.data, self.addr = self.telnet.recvfrom(BUFF_SIZE)
                    logger.info('telnet received  request %d bytes', len(self.data))
                    #logger.info('telnet received  request %s', self.addr[0])
                    #logger.info('telnet received  request %d', self.addr[1])
                    #logger.debug(......., self.data.decode())
                    # we should resend it
                    logger.info('resending %d bytes to %s:%d', len(self.data), self.bl_addr.decode(), self.port)
                    self.resend.send(self.data)
                if self.sock == self.resend:
                    # so we received a reply
                    self.data, self.addr = self.resend.recvfrom(BUFF_SIZE)
                    logger.info('telnet received response %d bytes',len(self.data))
                    # from  %s:%d', len(self.data), self.addr[0], self.addr[1])
                    #logger.debug(....., self.data.decode())

                    logger.debug('sending %d bytes to %s:%d', len(self.data), self.gw_addr.decode(), self.gwt_port)
                    self.telnet.send(self.data)
                    logger.info('telnet sent back response to client')


class ListenerSender(Thread, QueueReceiver):
    def __init__(self, sq: queue.Queue, src_iface: bytes,dst_iface: bytes):
        super().__init__()
        #super(Thread, self).__init__()
        #Thread().__init__(self)
        #super(QueueReceiver,self).__init__()
        QueueReceiver.__init__(self)
        self.sq = sq        # the queue to send what i discover about the network
#        self.gw_port = 0    # source port from which gateway is sending
#        self.gw_addr= b''   # to save the gateway ip adress when discovered
#        self.bl_addr= b''   # to save the boiler ip address when discovered
#        self.bl_port= 0     # destination port to which boiler is listening
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
    def __init__(self, sq: queue.Queue, src_iface: bytes,dst_iface: bytes, udp_port: int):
        super().__init__(sq, src_iface, dst_iface)
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
            if platform.system() == 'Darwin':
                self.resend.bind(('', self.gw_port+1))
            else:
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
    def __init__(self, sq: queue.Queue, src_iface: bytes,dst_iface: bytes):
        super().__init__(sq, src_iface, dst_iface)
        # Add any additional initialization logic here
        self.rq = queue.Queue()

    def handleFirstPacket(self, data, addr):
        if self.bound == False: 
            logger.debug('BoilerListenerSender first packet, listener not bound yet') 
            # first time we receive a packet, bind from the source port
            logger.info('BoilerListenerSender discovered %s:%d', addr[0], addr[1])
            self.bl_addr = addr[0]
            self.bl_port = addr[1]
            self.sq.put('BL_ADDR:'+self.bl_addr)
            self.sq.put('BL_PORT:'+str(self.bl_port))
            self.resend.bind(('', self.bl_port))
            logger.debug('sender bound to port: %d', self.bl_port)
            self.bound = True

    def reSend(self, data):
        logger.debug('resending %d bytes to %s : %d', len(data), self.gw_addr.decode(), self.gw_port)
        self.resend.sendto(data, (self.gw_addr, self.gw_port))
        logger.info('resent %d bytes to %s : %d', len(data), self.gw_addr.decode(), self.gw_port)

    def run(self):
        logger.info('BoilerListenerSender started')
        while self.gw_port == 0:
            self.handleReceiveQueue()

        self.listen.bind( ('',self.gw_port) )
        logger.debug('listener bound to %s, port %d', self.src_iface.decode(), self.gw_port)

        self.loop()

#----------------------------------------------------------#
tln= TelnetProxy(src_iface, dst_iface, 23)
bls= BoilerListenerSender(tln, dst_iface, src_iface)
gls= GatewayListenerSender(bls, src_iface, dst_iface, udp_port)

tln.start()
bls.start()
gls.start()

