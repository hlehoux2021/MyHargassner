"""
This module implements the TelnetProxy
"""
import socket as s
import select
import time

import platform
import logging
from threading import Thread
from typing import Annotated
import annotated_types

from pubsub.pubsub import PubSub

from telnethelper import TelnetClient
from shared import ChanelReceiver,BUFF_SIZE
from analyser import Analyser
from actuator import ThreadedMqttActuator, MqttBase
from socket_manager import SocketManager

# $login token
#   $00A000A0
# $login key xxxxx
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



class TelnetService:
    """
    implements telnet service receiving requests and forwarding them to the boiler
    """
    _listen= None
    _telnet= None

    def __init__(self, src_iface: bytes):
        self._listen = s.socket(s.AF_INET, s.SOCK_STREAM)
        if platform.system() == 'Linux' and not SocketManager.is_valid_ip(src_iface.decode('utf-8')):
            self._listen.setsockopt(s.SOL_SOCKET, s.SO_BINDTODEVICE, src_iface)
        self._listen.setsockopt(s.SOL_SOCKET, s.SO_REUSEPORT, 1)
        self._listen.setsockopt(s.SOL_SOCKET, s.SO_REUSEADDR, 1)

    def bind(self, port: int):
        """bind the telnet socket"""
        logging.debug('TelnetService binding to port %d', port)
        self._listen.bind(('', port))
    def listen(self):
        """listen for a telnet connection"""
        logging.debug('TelnetService listening')
        self._listen.listen()
    def accept(self) -> bytes:
        """accept a telnet connection"""
        _addr: tuple
        logging.info('TelnetService accepting a connection')
        self._telnet, _addr = self._listen.accept()
        logging.info('TelnetService connection from %s:%d accepted', _addr[0], _addr[1])
        # reply the source port from which gateway is telneting
        return _addr[1]
    def send(self, data: bytes)-> int:
        return self._telnet.send(data)
    def socket(self) -> s.socket | None:
        return self._telnet if self._telnet else None
    def recv(self) -> bytes:
        return self._telnet.recv(BUFF_SIZE)


class TelnetProxy(ChanelReceiver, MqttBase):
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
    _active_sockets: set[s.socket] # Track which sockets are still active
 #   _telnet: s.socket
    _analyser: Analyser
#    _pmstamp: int = 0
#    _values: dict = None # telnet pm values
    _ma: ThreadedMqttActuator | None = None


    def __init__(self, communicator: PubSub, src_iface, dst_iface, port):
        ChanelReceiver.__init__(self, communicator)
        MqttBase.__init__(self)
        self.src_iface = src_iface
        self.dst_iface = dst_iface
        self.port = port
        self._analyser = Analyser(communicator)
        self._service1 = TelnetService(self.src_iface)
        self._service2 = TelnetService(self.src_iface)
        # we will now create the socket to resend the telnet request
        self._client = None
        self._ma = None
        self._active_sockets = set()

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
        # Re-add service1 socket to active sockets in the loop
        if hasattr(self, '_active_sockets'):
            self._active_sockets.add(self._service1.socket())
            logging.debug('Re-added service1 socket to active set')
    def accept2(self):
        """accept a telnet connection"""
        self._service2.accept()
        # Re-add service2 socket to active sockets in the loop
        if hasattr(self, '_active_sockets'):
            self._active_sockets.add(self._service2.socket())
            logging.debug('Re-added service2 socket to active set')

    # wait for the boiler address and port to be discovered
    def discover(self):
        """wait for the boiler address and port to be discovered"""
        self._msq = self._com.subscribe(self._channel, self.name())

        while (self.bl_port == 0) or (self.bl_addr == b''):
            logging.debug('waiting for the discovery of the boiler address and port')
            self.handle()
        logging.info('TelnetProxy discovered boiler %s:%d', self.bl_addr, self.bl_port)
        # unsubscribe from the channel to avoid receiving further messages
        logging.info('TelnetProxy unsubscribe from channel %s', self._channel)
        self._com.unsubscribe(self._channel, self._msq)
        self._msq = None

        # redistribute BL info to the mq Queue for further use
        #todo check if useless
        self._analyser.push('BL_ADDR',str(self.bl_addr,'ascii'))
        self._analyser.push('BL_PORT',str(self.bl_port))
    def connect(self):
        """connect to the boiler"""
        logging.debug('TelnetProxy connecting to boiler bl_addr=%s  dst_iface=%s', repr(self.bl_addr), repr(self.dst_iface))
        self._client= TelnetClient(self.bl_addr, self.dst_iface)
        self._client.connect()


    def get_boiler_config(self):
        """get the boiler configuration

        Returns:
            dict[str, list[str]]: A dictionary with the parameter name as key and a list of non-zero values
        """
        message: str = 'BoilerConfig:'
        commands= [
            b'$par get PR001\r\n',
            b'$par get PR011\r\n',
            b'$par get PR012\r\n'
        ]
        if not self._client._connected:
            logging.error('Client not connected')
            return {}
        logging.debug('telnet getting boiler config from %s', repr(self.bl_addr))

        for cmd in commands:
            logging.debug('telnet sending command %s', cmd)
            try:
                self._client.send(cmd)
                resp = self._client.recv(BUFF_SIZE)
                if resp:
                    logging.debug('telnet received response %s', resp)
                    message += resp.decode('latin1')  # Use latin-1 to avoid UnicodeDecodeError
            except Exception as e:
                logging.error('Failed to send/recv command %s: %s', cmd, str(e))
                continue
        self._com.publish(self._channel, message)
        logging.debug('Published combined message for commands %s', message)

    def loop(self):
        """loop waiting requests and replies"""
        _sock: s.socket
        _data: bytes
        _addr: tuple
        read_sockets: list[s.socket] = []
        write_sockets: list[s.socket]
        error_sockets: list[s.socket]
        _state: str = '' # state of the request/response dialog
        _buffer: bytes = b'' # buffer to store the data received until we have a complete response
        _mode: str = ''
        _caller: int = 0 # to recall which caller we have to reply to (service1 or service 2)

        # Initialize active sockets if not already done
        service1_socket = self._service1.socket()
        if service1_socket is not None:
            self._active_sockets.add(service1_socket)
            logging.debug('Added service1 socket to active set')
        service2_socket = self._service2.socket()
        if service2_socket is not None:
            self._active_sockets.add(service2_socket)
            logging.debug('Added service2 socket to active set')
        if self._client is not None:
            client_socket = self._client.socket()
            if client_socket is not None:
                self._active_sockets.add(client_socket)
                logging.debug('Added client socket to active set')

        logging.debug('Active sockets: %d', len(self._active_sockets))

        while self._active_sockets:  # Continue as long as we have active sockets
            if self._msq:
                logging.debug('TelnetProxy ChannelQueue size: %d', self._msq.qsize())
            try:
                read_sockets, write_sockets, error_sockets = select.select(list(self._active_sockets), [], [], 1.0)
            except select.error as err:
                logging.error("Select error: %s", str(err))
                continue
            except Exception as err:
                logging.error("Unexpected error in select: %s", str(err))
                continue
#                [self._service1.socket(), self._client.socket()], [], [])
            for _sock in read_sockets:
                if _sock == self._service1.socket():
                    # so we received a request
                    try:
                        _data = self._service1.recv()
                        if not _data:
                            logging.warning('service1 received empty request - client disconnected')
                            sock = self._service1.socket()
                            if sock is not None:
                                try:
                                    sock.close()
                                    self._active_sockets.discard(sock)
                                except Exception as close_err:
                                    logging.error("Error closing service1 socket: %s", str(close_err))
                            raise s.error("service1: Client disconnected")
                        logging.debug('service1 received request %d bytes ==>%s', len(_data), repr(_data))
                        _caller = 1
                        # ask the Analyser() to analyse the IGW request
                        _state = self._analyser.parse_request(_data)
                        logging.debug('_state-->%s', _state)
                        # we should resend it
                        logging.debug('service1 resending %d bytes to %s:%d',
                                    len(_data), repr(self.bl_addr), self.port)
                        #todo manage partial send data
                        self._client.send(_data)
                    except s.error as err:
                        logging.error("Socket error in service1 recv: %s", str(err))
                        sock = self._service1.socket()
                        if sock is not None:
                            try:
                                sock.close()
                                self._active_sockets.discard(sock)
                            except Exception as close_err:
                                logging.error("Error closing service1 socket: %s", str(close_err))
                        # Raise with service identification
                        raise s.error(f"service1: {str(err)}")
                    except Exception as err:
                        logging.critical("Unexpected error in service1 recv: %s", type(err))
                        if self._service1.socket() is not None:
                            try:
                                self._service1.socket().close()
                            except:
                                pass
                        # Raise with service identification
                        raise s.error(f"service1: {str(err)}")
                if _sock == self._service2.socket():
                    try:
                        _data = self._service2.recv()
                        if not _data:
                            logging.warning('service2 received empty request')
                            continue
                        logging.debug('service2 received request %d bytes ==>%s', len(_data), repr(_data))
                        _caller = 2
                        # we should resend it
                        logging.debug('service2 resending %d bytes to %s:%d',
                                    len(_data), repr(self.bl_addr), self.port)
                        #todo manage partial send data
                        self._client.send(_data)
                    except s.error as err:
                        logging.error("Socket error in service2 recv: %s", str(err))
                        sock = self._service2.socket()
                        if sock is not None:
                            try:
                                sock.close()
                                self._active_sockets.discard(sock)
                            except Exception as close_err:
                                logging.error("Error closing service2 socket: %s", str(close_err))
                        # Raise with service identification
                        raise s.error(f"service2: {str(err)}")
                    except Exception as err:
                        logging.critical("Unexpected error in service2 recv: %s", type(err))
                        if self._service2.socket() is not None:
                            try:
                                sock = self._service2.socket()
                                sock.close()
                                self._active_sockets.discard(sock)
                            except Exception as close_err:
                                logging.error("Error closing service2 socket: %s", str(close_err))
                        # Raise with service identification
                        raise s.error(f"service2: {str(err)}")
                if _sock ==self._client.socket():
                    # so we received a reply
                    try:
                        _data = self._client.recv(BUFF_SIZE)
                    except Exception as err:
                        logging.critical("Exception on client telnet socket: %s", type(err))
                        if self._client is not None:
                            self._client.close()
                        raise  # Re-raise to be caught by loop() to continue with other sockets

                    if not _data:
                        logging.warning('client received empty response')
                        if self._client is not None:
                            self._client.close()
                        raise s.error("Empty response from client")

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
                        _sent = 0
                        logging.debug('telnet sending response to caller %d', _caller)
                        if _caller==1:
                            _sent= self._service1.send(_data)
                        elif _caller==2:
                            _sent= self._service2.send(_data)
                        elif _data.startswith(b'pm'):
                            if self._service1.socket() is not None:
                                logging.debug('telnet sending pm response to service1')
                                _sent = self._service1.send(_data)
                            else:
                                logging.warning('Received a pm response but no service1 socket registered yet')
                        else:
                            logging.warning('Beware received a response with not registered caller %d', _caller)
                        if _sent != len(_data):
                            logging.error('telnet send error: not all data sent %d/%d', _sent, len(_data))
                        logging.debug('telnet sent back response to client')
                    except Exception as err:
                        logging.critical("Exception: %s", type(err))
                        raise
                    # ask Analyser() to analyse the pellet boiler response
                    _login_done: bool = False
                    _buffer, _mode, _state, _login_done = self._analyser.analyse_data_buffer(_data,
                               _buffer, _mode, _state)
                    if _login_done:
                        logging.info('login done, should get_boiler_config')
                        self.get_boiler_config()

    def restart_service1(self):
        """Restart service1 after failure"""
        logging.info("Restarting service1...")
        try:
            self._service1 = TelnetService(self.src_iface)
            self.bind1()
            self.listen1()
            self.accept1()
            return True
        except Exception as err:
            logging.error("Failed to restart service1: %s", str(err))
            return False

    def restart_service2(self):
        """Restart service2 after failure"""
        logging.info("Restarting service2...")
        try:
            self._service2 = TelnetService(self.src_iface)
            self.bind2()
            self.listen2()
            self.accept2()
            return True
        except Exception as err:
            logging.error("Failed to restart service2: %s", str(err))
            return False

    def restart_client(self):
        """Restart client connection after failure"""
        logging.info("Restarting client connection...")
        try:
            self.connect()
            # we cannot get_boiler_config until gateway and boiler have exchanged login token and login key
            # because we would receive b'$permission denied\r\n' from the boiler
            #self.get_boiler_config()
            return True
        except Exception as err:
            logging.error("Failed to restart client: %s", str(err))
            return False

    def service(self):
        """Main service loop that handles reconnections"""
        logging.debug('TelnetProxy::service')
        # Initial setup
        if not self.restart_client():
            raise RuntimeError("Failed initial client connection")
        while True:
            try:
                logging.debug('TelnetProxy::service starting loop')
                self.loop()
            except s.error as err:
                if "service1" in str(err):
                    logging.error("Service1 failed, attempting restart: %s", str(err))
                    if self.restart_service1():
                        continue
                elif "service2" in str(err):
                    logging.error("Service2 failed, attempting restart: %s", str(err))
                    if self.restart_service2():
                        continue
                else:
                    logging.error("Client connection failed, attempting restart: %s", str(err))
                    if self.restart_client():
                        continue
                # If we get here, restart failed
                time.sleep(5)  # Wait before retry
            except Exception as err:
                logging.critical("Fatal error in service: %s", str(err))
                raise  # Re-raise fatal errors

class ThreadedTelnetProxy(Thread):
    """This class implements a Thread to run the TelnetProxy"""
    _tserver: Thread
    def __init__(self, communicator: PubSub, src_iface, dst_iface, port):
        super().__init__(name='TelnetProxy')
        self.tp= TelnetProxy(communicator, src_iface, dst_iface, port)
        # Add any additional initialization logic here

    def run(self):
        _ts: Thread | None = None
        logging.info('telnet proxy started: %s , %s', self.tp.src_iface, self.tp.dst_iface)

        # we will first discover the boiler
        self.tp.discover()

        # if we have a BL_ADDR, we create the ThreadedMqttActuator
        if not self.tp._ma:
            logging.debug("BL_ADDR present but no actuator found")
            logging.debug('we create and launch a ThreadedMqttActuator in a separate thread')
            self.tp._create_device_info(self.tp.bl_addr.decode('ascii'))
            self.tp._ma = ThreadedMqttActuator(self.tp._com, self.tp._device_info)
            self.tp._ma.start()

        # then we can bind/listen/accept and service()
        self.tp.bind1()
        self.tp.bind2()
        self.tp.listen1()
        self.tp.listen2()
        # Create separate threads for accepting connections
        _accept1_thread = Thread(target=self.tp.accept1, name='AcceptService1')
        _accept2_thread = Thread(target=self.tp.accept2, name='AcceptService2')
        # Start both accept threads
        _accept1_thread.start()
        _accept2_thread.start()
        # Service thread will handle the communication
        _ts = Thread(target=self.tp.service, name='TelnetProxyService')
        _ts.start()
        # Wait for all threads
        _accept1_thread.join()
        _accept2_thread.join()
        _ts.join()
