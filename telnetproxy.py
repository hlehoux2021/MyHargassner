"""
This module implements the TelnetProxy
"""
import socket as s
import select
#from queue import Queue
from pubsub.pubsub import PubSub

import platform
import logging
from threading import Thread
from typing import Annotated, Tuple
import annotated_types

from shared import SharedDataReceiver,BUFF_SIZE
from analyser import Analyser

# $login token
#   $00A000A0
# $login key
#   zclient login (x)
#   $ack
# $apiversion
#   $1.0.1
# $setkomm
#   $1234567 ack
# $asnr get
#   $
# $igw set 1234567
#   $ack
# $daq stop
#   $daq stopped
# $logging disable
#   $logging disabled
# $daq desc
#   $<<<DAQPRJ> .... (long)
# $daq start
#   $daq started
# $logging enable
#   $logging enabled
# $bootversion
#   $V0.00
# $info
#   $KT: 'Nano.....'
#   $SWV: 'V00.0n0'
#   $FWV I/O: 'V0.0.0'
#   $SN I/O: '1234567'
#   $SN BCE: '1234567'
# $uptime
#   $0000
# $rtc get
#   $YYYY-MM-DD HH:MM:SS
# $par get changed "YYYY-MM-DD HH:MM:SS"
#   $--
# $erract
#   $no errors

# dictionnary
# BL_ADDR: boiler ip
# BL_PORT: boiler port
# HSV: eg HSV/CL 9-60KW V14.0n3
# SYS: code system
# KEY: login key
# TOKEN: login token
# IGW: internet gateway number
# API: api version
# SETKOMM: setkomm value
# ASNR: asnr version number
# BOOT: boot version number
# KT: kt description
# SWV: software version
# FWV: firmware i/o version
# SNIO: sn i/o
# SNBCE: sn bce
# UPTIME: uptime
# RTC: real time count

# Arret
#$par get PR001\r\n
#    $PR001;6;2;4;1;0;0;0;Mode;Manu;Arr;Ballon;Auto;Arr combustion;0;\r\n
#$par set "PR001;6;1"\r\n
#   zPa A: PR001 (Mode) = Ballon\r\n
#   zPa N: PR001 (Mode) = Arr\r\n
#   zParamter PR001 per APP verstellt\r\n
#   $ack\r\n
#$par get PR001\r\n
#   $PR001;6;1;4;1;0;0;0;Mode;Manu;Arr;Ballon;Auto;Arr combustion;0;\r\n
#
# Auto
#$par get PR001\r\n
#   $PR001;6;1;4;1;0;0;0;Mode;Manu;Arr;Ballon;Auto;Arr combustion;0;\r\n
# $par set "PR001;6;3"\r\n
#   zPa A: PR001 (Mode) = Arr\r\n
#   zPa N: PR001 (Mode) = Auto\r\n
#   zParamter PR001 per APP verstellt\r\n
#   $ack\r\n
#$par get PR001\r\n
#   $PR001;6;3;4;1;0;0;0;Mode;Manu;Arr;Ballon;Auto;Arr combustion;0;\r\n
#
# table, 6 champs
# Mode
# Manu : 0
# Arr : 1
# Ballon : 2
# Auto : 3
# Arret Combustion : 4

#Chauffage Zone 1
# 0: arret
# 1: auto
# 2: reduire
# 3: confort
# 4: 1x confort
# 5: Refroid
# automatique
#$par get PR011\r\n
#   $PR011;6;0;5;1;0;0;0;Zone 1 Mode;Arr;Auto;R\xe9duire;Confort;1x Confort;Refroid.;0;\r\n
#$par set "PR011;6;1"\r\n
#   zPa A: PR011 (Mode) = Arr\r\nz
#   Set Para changed\r\n
#   zPa N: PR011 (Mode) = Auto\r\n
#   zParamter PR011 per APP verstellt\r\n
#   $ack\r\n
#
# reduire
#$par set "PR011;6;2"\r\n
# confort
#$par set "PR011;6;3"\r\n
# arret
# $par set "PR011;6;0"\r\n
#   zPa A: PR011 (Mode) = Confort\r\n
#   zPa N: PR011 (Mode) = Arr\r\n
#   zParamter PR011 per APP verstellt\r\n
#   $ack
#   zFr 1 Set Mode 0 (2)\r\n
#   zHK1 Restwaerme\r\n
#   zkeine Anforderung\r\n
#   zPuffer Aus\r\n


class TelnetClient():
    """
    implement a client connecting to a telnet service
    """
    _sock= None
    def __init__(self):
        super().__init__()
        # we will now create the socket to resend the telnet request
        self._sock = s.socket(s.AF_INET, s.SOCK_STREAM)
        self._sock.setsockopt(s.SOL_SOCKET, s.SO_REUSEPORT, 1)
        self._sock.setsockopt(s.SOL_SOCKET, s.SO_REUSEADDR, 1)
#        self._sock.settimeout(SOCKET_TIMEOUT)

    def connect(self, addr: bytes):
        """connect to the boiler"""
        if platform.system() == 'Darwin':
            port= 24  # default telnet port
        else:
            port= 23  # default telnet port
        logging.info('telnet connecting to %s on port %d', repr(addr), port)
        self._sock.connect((addr, port))

    def send(self, data: bytes):
        self._sock.send(data)
    def socket(self):
        return self._sock
    def recvfrom(self) -> Tuple[bytes, bytes]:
        return self._sock.recvfrom(BUFF_SIZE)

class TelnetService():
    """
    implements telnet service receiving requests and forwarding them to the boiler
    """
    _listen= None
    _telnet= None

    def __init__(self, src_iface: bytes):
        super().__init__()
        self._listen = s.socket(s.AF_INET, s.SOCK_STREAM)
        if platform.system() == 'Linux':
            self._listen.setsockopt(s.SOL_SOCKET, s.SO_BINDTODEVICE, src_iface)
        self._listen.setsockopt(s.SOL_SOCKET, s.SO_REUSEPORT, 1)
        self._listen.setsockopt(s.SOL_SOCKET, s.SO_REUSEADDR, 1)

    def bind(self, port: int):
        """bind the telnet socket"""
        logging.debug('telnet binding to port %d', port)
        self._listen.bind(('', port))
    def listen(self):
        """listen for a telnet connection"""
        logging.debug('telnet listening')
        self._listen.listen()
    def accept(self) -> bytes:
        """accept a telnet connection"""
        _addr: tuple
        logging.info('telnet accepting a connection')
        self._telnet, _addr = self._listen.accept()
        logging.info('telnet connection from %s:%d accepted', _addr[0], _addr[1])
        # reply the source port from which gateway is telneting
        return _addr[1]
    def send(self, data: bytes)-> int:
        return self._telnet.send(data)
    def socket(self):
        return self._telnet
    def recvfrom(self) -> Tuple[bytes, bytes]:
        return self._telnet.recvfrom(BUFF_SIZE)


class TelnetProxy(SharedDataReceiver):
    """
    This class implements the TelnetProxy
    """
    src_iface: bytes
    dst_iface: bytes
    port: Annotated[int, annotated_types.Gt(0)]
 #   _listen: s.socket
 #  _resend: s.socket
    _client: TelnetClient # to request the boiler
    _service1: TelnetService # to service the IGW gateaway
    _service2: TelnetService # to service other requests
 #   _telnet: s.socket
    _analyser: Analyser
#    _pmstamp: int = 0
#    _values: dict = None # telnet pm values

    def __init__(self, communicator: PubSub, src_iface, dst_iface, port):
        super().__init__(communicator)
        self.src_iface = src_iface
        self.dst_iface = dst_iface
        self.port = port
        self._analyser= Analyser(communicator)
#        self._listen = s.socket(s.AF_INET, s.SOCK_STREAM)
#        if platform.system() == 'Linux':
#            self._listen.setsockopt(s.SOL_SOCKET, s.SO_BINDTODEVICE, self.src_iface)
#        self._listen.setsockopt(s.SOL_SOCKET, s.SO_REUSEPORT, 1)
#        self._listen.setsockopt(s.SOL_SOCKET, s.SO_REUSEADDR, 1)
        self._service1= TelnetService(self.src_iface)
        self._service2= TelnetService(self.src_iface)
        # we will now create the socket to resend the telnet request
        self._client= TelnetClient()
#        self._resend.setsockopt(s.SOL_SOCKET, s.SO_REUSEADDR, 1)
#        self._resend = s.socket(s.AF_INET, s.SOCK_STREAM)
#        self._resend.setsockopt(s.SOL_SOCKET, s.SO_REUSEPORT, 1)
#        self._resend.settimeout(SOCKET_TIMEOUT)
#        self._values= dict()
#        self._convert= dict()

    def bind1(self):
        """bind the telnet socket"""
        logging.debug('telnet binding to port %s', self.port)
        self._service1.bind(self.port)
    def bind2(self):
        """bind the telnet socket"""
        logging.debug('telnet binding to port 4000')
        self._service2.bind(4000)

    def listen1(self):
        """listen for a telnet connection"""
        logging.debug('telnet listening')
        self._service1.listen()
    def listen2(self):
        """listen for a telnet connection"""
        logging.debug('telnet listening')
        self._service2.listen()

    def accept1(self):
        """accept a telnet connection"""
        # remember the source port from which gateway is telneting
        self.gwt_port = self._service1.accept()
    def accept2(self):
        """accept a telnet connection"""
        self._service2.accept()

    # wait for the boiler address and port to be discovered
    def discover(self):
        """wait for the boiler address and port to be discovered"""
        while (self.bl_port == 0) or (self.bl_addr == b''):
            logging.debug('waiting for the discovery of the boiler address and port')
            self.handle()
        # redistribute BL info to the mq Queue for further use
        self._analyser.push('BL_ADDR',str(self.bl_addr,'ascii'))
        self._analyser.push('BL_PORT',str(self.bl_port))
    def connect(self):
        """connect to the boiler"""
        logging.info('telnet connecting to %s on port 23', repr(self.bl_addr))
        self._client.connect(self.bl_addr)

    def loop(self):
        """loop waiting requests and replies"""
        _sock: s.socket
        _data: bytes
        _addr: tuple
        read_sockets: list[s.socket]
        write_sockets: list[s.socket]
        error_sockets: list[s.socket]
        _state: str = '' # state of the request/response dialog
        _buffer: bytes = b'' # buffer to store the data received until we have a complete response
#        _pm: bytes = b'' # buffer to store special "pm" response
        _mode: str = ''
        _caller: int = 0 # to recall which caller we have to reply to (service1 or service 2)
        while True:
            logging.debug('telnet waiting data')
            if self._service2.socket() == None:
                read_sockets, write_sockets, error_sockets = select.select(
                    [self._service1.socket(), self._client.socket()], [], [])
            else:
                read_sockets, write_sockets, error_sockets = select.select(
                    [self._service1.socket(), self._service2.socket(), self._client.socket()], [], [])
#                [self._service1.socket(), self._client.socket()], [], [])
            for _sock in read_sockets:
                if _sock == self._service1.socket():
                    # so we received a request
                    _data, _addr = self._service1.recvfrom()
                    logging.debug('service1 received  request %d bytes ==>%s',
                                 len(_data), repr(_data))
                    _caller= 1
                    if not _data:
                        logging.warning('service1 received empty request')
                        continue
                    _state = self._analyser.parse_request(_data)
                    logging.debug('_state-->%s',_state)
                    # we should resend it
                    logging.debug('resending %d bytes to %s:%d',
                                 len(_data), repr(self.bl_addr), self.port)
                    #todo manage partial send data
                    self._client.send(_data)
 #               if _sock == self._resend:
                if _sock == self._service2.socket():
                    _data, _addr = self._service2.recvfrom()
                    logging.debug('service2 received  request %d bytes ==>%s',
                                 len(_data), repr(_data))
                    _caller= 2
                    for i in str(_sock).split():
                            logging.debug(i)
                    #self._service2.send(b'Thank you for calling')
                if _sock ==self._client.socket():
                    # so we received a reply
                    _data, _addr = self._client.recvfrom()
                    if not _data.startswith(b'pm'):
                        logging.debug('telnet received response %d bytes ==>%s',len(_data), repr(_data))
                    else:
                        logging.debug('telnet received pm response %d bytes',len(_data))
                    logging.debug('sending %d bytes to %s:%d',len(_data), self.gw_addr.decode(), self.gwt_port)
                    #todo manage when not all data is sent in one call
                    #todo manage exceptions
                    try:
                        # sending data back to the caller
                        # we imagine we receive the response quickly enough, 
                        # before receiving a new request from the other caller
                        # also this doesn't work if the pm buffer is split in several chunks
                        # would need a more robust logic here
                        if _caller==1 or _data.startswith(b'pm'):
                            _sent= self._service1.send(_data)
                        elif _caller==2:
                            _sent= self._service2.send(_data)
                        else:
                            logging.warning('Beware received a response with not registered caller %d', _caller)
                        if  _sent!= len(_data):
                            logging.error('telnet send error: not all data sent %d/%d',_sent, len(_data))
                        logging.debug('telnet sent back response to client')
                    except Exception as err:
                        logging.critical("Exception: %s", type(err))
                        raise
                    # analyse the response
                    _buffer, _mode, _state = self._analyser.analyse_data_buffer(_data,
                               _buffer, _mode, _state)

    def service(self):
        logging.debug('TelnetProxy::service()')
        # wait for the boiler address and port to be discovered
        self.discover()
        # boiler is listening on port 23
        self.connect()
        # now we can loop waiting requests and replies
        self.loop()

class ThreadedTelnetProxy(Thread):
    """This class implements a Thread to run the TelnetProxy"""
    _tserver: Thread
    def __init__(self, communicator: PubSub, src_iface, dst_iface, port):
        super().__init__(name='TelnetProxy')
        self.tp= TelnetProxy(communicator, src_iface, dst_iface, port)
        # Add any additional initialization logic here

    def run(self):
        _ts: Thread= None
        logging.info('telnet proxy started: %s , %s', self.tp.src_iface, self.tp.dst_iface)

        self.tp.bind1()
        self.tp.listen1()
        self.tp.accept1()
        #we will service the accepted connexion in a separate thread
        _ts= Thread(target=self.tp.service)
        _ts.start()
        self.tp.bind2()
        self.tp.listen2()
        self.tp.accept2()
        _ts.join()
