"""
This module implements the TelnetProxy
"""

# Standard library imports
from __future__ import annotations # to enable socket.socket without linter warning
import logging
import socket
import select
import time
import platform
from threading import Thread, Lock
from typing import Annotated,Tuple
import annotated_types


from myhargassner.pubsub.pubsub import PubSub


# Project imports
from myhargassner.telnethelper import TelnetClient
from myhargassner.appconfig import AppConfig
from myhargassner.core import ChanelReceiver, ShutdownAware
from myhargassner.analyser import Analyser
from myhargassner.mqtt_actuator import ThreadedMqttActuator, MqttBase
from myhargassner.socket_manager import SocketManager

#pylint: disable=broad-exception-caught

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
#
#PR001;6;2;4;1;0;0;0;Mode;Manu;Arr;Ballon;Auto;Arr combustion;0;\n
#PR003;6;3;3;3;0;0;0;Progr. HKM1;Manu;Arr;Ballon;Auto;0;\n
#PR004;6;3;3;3;0;0;0;Progr. HKM2;Manu;Arr;Ballon;Auto;0;\n
#PR010;6;1;5;1;0;0;0;Zone A Mode;Arr;Auto;R\xe9duire;Confort;1x Confort;Refroid.;0;\n
#PR011;6;0;5;1;0;0;0;Zone 1 Mode;Arr;Auto;R\xe9duire;Confort;1x Confort;Refroid.;0;\n
#PR012;6;1;5;1;0;0;0;Zone 2 Mode;Arr;Auto;R\xe9duire;Confort;1x Confort;Refroid.;0;\n
#PR013;6;1;5;1;0;0;0;Zone 3 Mode;Arr;Auto;R\xe9duire;Confort;1x Confort;Refroid.;0;\n
#PR014;6;1;5;1;0;0;0;Zone 4 Mode;Arr;Auto;R\xe9duire;Confort;1x Confort;Refroid.;0;\n
#PR015;6;1;5;1;0;0;0;Zone 5 Mode;Arr;Auto;R\xe9duire;Confort;1x Confort;Refroid.;0;\n
#PR016;6;1;5;1;0;0;0;Zone 6 Mode;Arr;Auto;R\xe9duire;Confort;1x Confort;Refroid.;0;\n
#PR017;6;1;5;1;0;0;0;Zone B Mode;Arr;Auto;R\xe9duire;Confort;1x Confort;Refroid.;0;\n
#PR030;6;0;6;0;0;0;0;Choix progr. hebdo KNX;0;1;2;3;4;5;6;0;\n
#PR040;6;0;1;0;0;0;0;Tampon D\xe9marrer chrgt;Non;Oui;0;\n
#PR041;6;0;1;0;0;0;0;Ballon A D\xe9marrer chrgt;Non;Oui;0;\n
#PR042;6;0;1;0;0;0;0;Ballon 1 D\xe9marrer chrgt;Non;Oui;0;\n
#PR043;6;0;1;0;0;0;0;Ballon 2 D\xe9marrer chrgt;Non;Oui;0;\n
#PR044;6;0;1;0;0;0;0;Ballon 3 D\xe9marrer chrgt;Non;Oui;0;\n
#PR045;6;0;1;0;0;0;0;Ballon B D\xe9marrer chrgt;Non;Oui;0;\n
#
# General parameters
# $par get 4
# $4;3;19.500;14.000;26.000;0.500;C;20.000;0;0;0;Zone 1 Temp. ambiante jour;
# $par set "4;3;20"
# zPa A: 4 (Temp. ambiante jour) = 19.5
# zSet Para changed
# zPa N: 4 (Temp. ambiante jour) = 20.0
# zParamter 4 per APP verstellt
# $ack



class TelnetService:
    """
    Implements telnet service receiving requests and forwarding them to the boiler.
    """
    _listen: socket.socket # socket to listen for telnet connections
    _telnet: socket.socket # socket to handle accepted telnet connections
    _buffer_size: int
    def __init__(self, src_iface: bytes, buffer_size:int):
        """
        Initialize the TelnetService with the given source interface.
        """
        self._listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if platform.system() == 'Linux' and not SocketManager.is_valid_ip(src_iface.decode('utf-8')):
            self._listen.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, src_iface) #pylint: disable=E1101
        self._listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self._listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._buffer_size = buffer_size
    def bind(self, port: int):
        """
        Bind the telnet socket to the specified port.
        """
        logging.debug('TelnetService binding to port %d', port)
        self._listen.bind(('', port))

    def listen(self):
        """
        Start listening for a telnet connection.
        """
        logging.debug('TelnetService listening')
        self._listen.listen()

    def accept(self) -> int:
        """
        Accept a telnet connection and return the source port of the connecting client.
        Returns:
            int: The port number of the connecting client.
        """
        _addr: Tuple[str, int] = ('', 0)
        logging.info('TelnetService accepting a connection')
        self._telnet, _addr = self._listen.accept()
        logging.info('TelnetService connection from %s:%d accepted', _addr[0], _addr[1])
        # reply the source port from which gateway is telneting
        return _addr[1]

    def send(self, data: bytes) -> int:
        """
        Send data to the connected telnet client.
        Args:
            data (bytes): The data to send.
        Returns:
            int: The number of bytes sent.
        """
        logging.debug('TelnetService.send called: self=%s id=%s data=%r', self.__class__.__name__, id(self), data)
        return self._telnet.send(data)

    def socket(self) -> socket.socket | None:
        """
        Get the socket object for the accepted telnet connection.
        Returns:
            socket.socket: The socket object.
        """
        return self._telnet if hasattr(self, "_telnet") and self._telnet else None

    def recv(self) -> bytes:
        """
        Receive data from the connected telnet client.
        Returns:
            bytes: The received data.
        """
        return self._telnet.recv(self._buffer_size)


class TelnetProxy(ShutdownAware, ChanelReceiver, MqttBase):
    """
    This class implements the TelnetProxy.
    Includes ShutdownAware mixin for graceful shutdown support.
    """
    src_iface: bytes
    dst_iface: bytes
    port: Annotated[int, annotated_types.Gt(0)]
    _client: TelnetClient # to request the boiler
    _service1: TelnetService # to service the IGW gateway
    _service2: TelnetService # to service other requests
    _active_sockets: set[socket.socket] # Track which sockets are still active
    _analyser: Analyser
    _service_lock: Lock
    _session_end_requested : bool # Flag for $igw clear detection
    _discovery_complete: bool # Flag to track boiler discovery completion
    _telnet_session_active: bool # Flag to track if telnet session is active
    # Note: _shutdown_requested is inherited from ShutdownAware mixin

    def __init__(self, appconfig: AppConfig, communicator: PubSub,
                 port: Annotated[int, annotated_types.Gt(0)], lock: Lock):
        """
        Initialize the TelnetProxy with communication channel, interfaces, and port.
        """
        ShutdownAware.__init__(self)  # Initializes _shutdown_requested
        ChanelReceiver.__init__(self, communicator, appconfig)
        MqttBase.__init__(self, appconfig)
        self.src_iface = self._appconfig.gw_iface()
        self.dst_iface = self._appconfig.bl_iface()
        self.port = port
        self._analyser = Analyser(communicator)
        self._service1 = TelnetService(self.src_iface, self._appconfig.buff_size)
        self._service2 = TelnetService(self.src_iface, self._appconfig.buff_size)
        self._service_lock = lock
        self._active_sockets = set()
        self._session_end_requested = False
        self._discovery_complete = False
        self._telnet_session_active= False

    def bind1(self):
        """
        Bind the first telnet service socket to the configured port.
        """
        logging.debug('telnet binding to port %s', self.port)
        self._service1.bind(self.port)

    def bind2(self):
        """
        Bind the second telnet service socket to port 4000.
        """
        logging.debug('telnet binding to port 4000')
        self._service2.bind(4000)

    def listen1(self):
        """
        Start listening for a telnet connection on the first service.
        """
        logging.debug('telnet listening')
        self._service1.listen()

    def listen2(self):
        """
        Start listening for a telnet connection on the second service.
        """
        logging.debug('telnet listening')
        self._service2.listen()

    def accept1(self):
        """
        Accept a telnet connection on the first service and track the socket.
        """
        # First remove any existing service1 socket from active set
        if hasattr(self, '_active_sockets'):
            old_sock = self._service1.socket()
            if old_sock is not None:
                self._active_sockets.discard(old_sock)
                try:
                    old_sock.close()
                except Exception:
                    pass

        # Accept new connection and remember the source port
        self.gwt_port = self._service1.accept()
        _sock = self._service1.socket()

        # Add new socket to active set
        if hasattr(self, '_active_sockets') and _sock is not None:
            self._active_sockets.add(_sock)
            logging.debug('Added new service1 socket to active set')

    def accept2(self):
        """
        Accept a telnet connection on the second service and track the socket.
        """
        # First remove any existing service2 socket from active set
        if hasattr(self, '_active_sockets'):
            old_sock = self._service2.socket()
            if old_sock is not None:
                self._active_sockets.discard(old_sock)
                try:
                    old_sock.close()
                except Exception:
                    pass

        # Accept new connection
        self._service2.accept()
        _sock = self._service2.socket()

        # Add new socket to active set
        if hasattr(self, '_active_sockets') and _sock is not None:
            self._active_sockets.add(_sock)
            logging.debug('Added new service2 socket to active set')

    # request_shutdown() inherited from ShutdownAware mixin

    def _request_restart(self, reason: str):
        """
        Request restart by publishing to 'system' channel for main.py to handle.
        Called only once per session from _cleanup_and_exit().

        Args:
            reason: Reason for restart (for logging)
        """
        logging.info('TelnetProxy requesting restart: %s', reason)
        self._com.publish('system', 'RESTART_REQUESTED')

    def discover(self):
        """
        Wait for the boiler address and port to be discovered.
        """
        self._msq = self._com.subscribe(self._channel, self.name())

        while (self.bl_port == 0 or self.bl_addr == b'') and not self._shutdown_requested:
            logging.debug('waiting for the discovery of the boiler address and port')
            self.handle()

        if self._shutdown_requested:
            logging.info('TelnetProxy: Shutdown requested during discovery')
            if self._msq:
                self._com.unsubscribe(self._channel, self._msq)
                self._msq = None
            return

        logging.info('TelnetProxy discovered boiler %s:%d', self.bl_addr, self.bl_port)
        self._discovery_complete = True

        # CRITICAL: Stay subscribed to detect duplicate discovery (Trigger 3 - reconnection)
        # Do NOT unsubscribe! We need to monitor for new HargaWebApp broadcasts during active session
        logging.info('TelnetProxy: Discovery complete, monitoring for reconnection signals')

        # redistribute BL info to the mq Queue for further use
        #todo check if useless
        self._analyser.push('BL_ADDR',str(self.bl_addr,'ascii'))
        self._analyser.push('BL_PORT',str(self.bl_port))

    def connect(self):
        """
        Connect to the boiler using the discovered address and interface.
        """
        logging.debug('TelnetProxy connecting to boiler bl_addr=%s  dst_iface=%s',
                      repr(self.bl_addr), repr(self.dst_iface))
        self._client= TelnetClient(self.bl_addr, self.dst_iface, buffer_size=self._appconfig.buff_size)
        self._client.connect()

    def get_boiler_config(self) -> None:
        """
        Get the boiler configuration.

        """
        message: str = 'BoilerConfig:'
        # todo make this as an HargConfig parameter.
        commands= [
            b'$par get PR001\r\n', # Mode Boiler
            b'$par get PR011\r\n', # Mode Zone 1
            b'$par get PR012\r\n', # Mode Zone 2
            b'$par get PR040\r\n', # démarrage Tampon.
            b'$par get 4\r\n', # parameter 4 : Temp. ambiante jour
            b'$par get 5\r\n' # parameter 5 : Temp. ambiante de réduit
        ]
        if not self._client.connected:
            logging.error('Client not connected')
            return
        logging.debug('telnet getting boiler config from %s', repr(self.bl_addr))

        for cmd in commands:
            logging.debug('telnet sending command %s', cmd)
            try:
                self._client.send(cmd)
                resp_chunks = []
                while True:
                    resp = self._client.recv()
                    if resp:
                        resp_chunks.append(resp)
                        if resp.endswith(b'\r\n'):
                            break
                    else:
                        break
                full_resp = b''.join(resp_chunks)
                if full_resp:
                    logging.debug('telnet received response %s', full_resp)
                    message += full_resp.decode('latin1')  # Use latin-1 to avoid UnicodeDecodeError
            except Exception as e:
                logging.error('Failed to send/recv command %s: %s', cmd, str(e))
                continue
        self._com.publish(self._channel, message)
        logging.debug('Published combined message for commands %s', message)

    def _cleanup_and_exit(self, reason: str) -> None:
        """
        Clean up all resources and request restart before exiting loop.

        Args:
            reason: Reason for exit (for logging and restart request)
        """
        logging.info('TelnetProxy cleaning up and exiting: %s', reason)

        # Close client connection to boiler
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                logging.warning('Error closing client connection: %s', e)

        # Close service sockets
        for service in [self._service1, self._service2]:
            sock = service.socket()
            if sock:
                try:
                    sock.close()
                    self._active_sockets.discard(sock)
                    logging.debug('Closed service socket')
                except Exception as e:
                    logging.warning('Error closing service socket: %s', e)

        # Clear active sockets set
        self._active_sockets.clear()

        # Unsubscribe from channel if still subscribed
        if self._msq:
            try:
                self._com.unsubscribe(self._channel, self._msq)
                self._msq = None
                logging.debug('Unsubscribed from channel %s', self._channel)
            except Exception as e:
                logging.warning('Error unsubscribing from channel: %s', e)

        # Request restart
        self._request_restart(reason)

    def monitor_for_reconnection(self) -> bool:
        """
        Check for reconnection signals (non-blocking).
        Detects Trigger 3: New HargaWebApp broadcast during active session.

        Returns:
            bool: True if reconnection detected, False otherwise
        """
        if not self._msq or not self._discovery_complete:
            logging.warning('monitor_for_reconnection called before discovery complete or without subscription')
            return False

        try:
            # Non-blocking check for new discovery messages
            iterator = self._msq.listen(timeout=0.01)  # Very short timeout
            message = next(iterator)

            if message:
                msg = message['data']

                # Check for new "HargaWebApp" broadcast during active session
                # only return True if telnet session is active
                logging.info('monitor_for_reconnection received message: %s', msg)
                if not self._telnet_session_active:
                    logging.warning('Received new HargaWebApp but no active telnet session - ignoring restart')
                    return False
                if 'HargaWebApp' in msg:
                    logging.critical('Received new HargaWebApp during active session - IGW reconnected')
                    return True

        except StopIteration:
            pass  # No message, continue

        return False

    def loop(self) -> None:
        """
        Main loop waiting for requests and replies, handling all active sockets.
        """
        _sock: socket.socket
        _data: bytes
        _addr: tuple
        read_sockets: list[socket.socket] = []
        write_sockets: list[socket.socket] = []  # pylint: disable=unused-variable
        error_sockets: list[socket.socket] = []  # pylint: disable=unused-variable
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

        self._telnet_session_active = False
        logging.info('TelnetProxy entering main loop, IGW session not yet active')
        while self._active_sockets and not self._shutdown_requested:  # Continue as long as we have active sockets
            # TRIGGER 3: Periodically check for reconnection signals (new HargaWebApp)
            if self.monitor_for_reconnection():
                self._cleanup_and_exit('new_HargaWebApp_during_active_session')
                return

            if self._msq:
                logging.debug('TelnetProxy ChannelQueue size: %d', self._msq.qsize())
            try:
                # Use configurable timeout for select to ensure shutdown responsiveness
                read_sockets, write_sockets, error_sockets = select.select(
                    list(self._active_sockets), [], [], self._appconfig.loop_timeout()
                )
            except select.error as err:
                logging.error("Select error: %s", str(err))
                continue
            except Exception as err:
                logging.error("Unexpected error in select: %s", str(err))
                continue
            for _sock in read_sockets:
                if _sock == self._service1.socket():
                    # Only process service1 if lock is not held (by actuator sending commands to service2)
                    if self._service_lock.locked():
                        logging.debug('Service1 socket is paused/locked, skipping processing')
                        time.sleep(self._appconfig.service_lock_delay)
                        continue
                    # so we received a request
                    try:
                        _data = self._service1.recv()
                        if not _data:
                            # TRIGGER 2: IGW closed connection
                            logging.info('service1: IGW closed connection')
                            self._cleanup_and_exit('connection_closed')
                            return

                        logging.debug('service1 received request %d bytes ==>%s', len(_data), repr(_data))
                        _caller = 1
                        # ask the Analyser() to analyse the IGW request
                        _state, _session_end_requested = self._analyser.parse_request(_data)
                        logging.debug('_state-->%s', _state)
                        # if _state is "$login token" then telnet session with IGW becomes active.
                        if _state == "$login token":
                            self._telnet_session_active = True
                            logging.info('Telnet session with IGW is now active')

                        # TRIGGER 1: Update session end flag if $igw clear detected by analyser
                        if _session_end_requested:
                            self._session_end_requested = True
                            # as soon as $igw clear is received, we trigger restart, even before receiving $ack
                            logging.info('$igw clear command detected, cleaning up session')
                            self._cleanup_and_exit('igw_clear_command')
                            return

                        # Forward request to boiler
                        logging.debug('service1 resending %d bytes to %s:%d',
                                    len(_data), repr(self.bl_addr), self.port)
                        try:
                            self._client.send(_data)
                        except Exception as e:
                            logging.error("Error sending request to boiler: %s", str(e))
                            # Don't raise here - let the connection continue
                    except socket.error as err:
                        # TRIGGER 2: Socket error
                        logging.error("Socket error in service1 recv: %s", str(err))
                        self._cleanup_and_exit('socket_error')
                        return

                    except Exception as err:
                        logging.critical("Unexpected error in service1 recv: %s", type(err))
                        self._cleanup_and_exit('unexpected_error')
                        return
                if _sock == self._service2.socket():
                    try:
                        _data = self._service2.recv()
                        if not _data:
                            logging.error('service2 received empty request')
                            self._cleanup_and_exit('received_empty_request_service2')
                            return
                        logging.debug('service2 received request %d bytes ==>%s', len(_data), repr(_data))
                        _caller = 2
                        # we should resend it
                        logging.debug('service2 resending %d bytes to %s:%d',
                                    len(_data), repr(self.bl_addr), self.port)
                        #todo manage partial send data
                        self._client.send(_data)
                    except socket.error as err:
                        logging.error("Socket error in service2 recv: %s", str(err))
                        self._cleanup_and_exit('socket_error_service2')
                        return
                    except Exception as err:
                        logging.critical("Unexpected error in service2 recv: %s", type(err))
                        self._cleanup_and_exit('unexpected_error_service2')
                        return
                if _sock ==self._client.socket():
                    # so we received a reply
                    try:
                        _data = self._client.recv()
                    except Exception as err:
                        logging.critical("Exception on client telnet socket: %s", type(err))
                        self._cleanup_and_exit('client_socket_exception')
                        return

                    if not _data:
                        logging.warning('client received empty response from boiler')
                        self._cleanup_and_exit('boiler_disconnected')
                        return

                    if not _data.startswith(b'pm'):
                        logging.debug('telnet received response %d bytes ==>%s',len(_data), repr(_data))
                    else:
                        logging.debug('telnet received pm response %d bytes',len(_data))
                    #logging.debug('sending %d bytes to %s:%d',len(_data), self.gw_addr.decode(), self.gwt_port)
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
                        if _data.startswith(b'pm'):
                            if self._service1.socket() is not None:
                                logging.debug('telnet sending pm response to service1')
                                _sent = self._service1.send(_data)
                            else:
                                logging.debug('Received a pm response but no service1 socket registered yet')
                        else:
                            if _caller == 1:
                                _sent = self._service1.send(_data)
                            elif _caller == 2:
                                logging.debug('telnet sending response to service2')
                                _sent = self._service2.send(_data)
                                #send also to the IGW to inform about changes
                                _sent = self._service1.send(_data)
                            else:
                                logging.warning('Beware received a buffer with not registered caller %d', _caller)
                                if self._service1.socket() is not None:
                                    logging.warning('telnet sending generic buffer to service1')
                                    _sent = self._service1.send(_data)
                                else:
                                    logging.warning('No service1 socket registered yet to send generic buffer')
#                        if _sent != len(_data):
#                            logging.error('telnet send error: not all data sent %d/%d', _sent, len(_data))
                        logging.debug('telnet sent back response to client')
                    except Exception as err:
                        logging.critical("Exception sending response to IGW: %s", type(err))
                        self._cleanup_and_exit('send_response_exception')
                        return
                    # ask Analyser() to analyse the pellet boiler response
                    _login_done: bool = False
                    _session_end_complete: bool = False
                    #we call the analyser
                    _buffer, _mode, _state, _login_done, _session_end_complete = \
                        self._analyser.analyse_data_buffer(
                            _data, _buffer, _mode, _state, self._session_end_requested)

                    # TRIGGER 1: Check if $igw clear session completed
                    if _session_end_complete:
                        logging.info('$igw clear complete')
                        self._cleanup_and_exit('igw_clear_command')
                        return
                    if _login_done:
                        logging.log(15, 'TelnetProxy get_boiler_config()')
                        self.get_boiler_config()

        # Clean exit
        if self._shutdown_requested:
            logging.info('TelnetProxy: Exiting loop cleanly due to shutdown request')
        else:
            logging.info('TelnetProxy: Exiting loop (no active sockets)')

    def connect_client(self) -> bool:
        """
        Connect to the boiler for the first time.
        Returns:
            bool: True if connection succeeded, False otherwise.
        """
        logging.info("Connecting to boiler...")
        try:
            self.connect()
            # we cannot get_boiler_config until gateway and boiler have exchanged login token and login key
            # because we would receive b'$permission denied\r\n' from the boiler
            #self.get_boiler_config()
            return True
        except Exception as err:
            logging.error("Failed to connect to boiler: %s", str(err))
            return False

    def service(self) -> None:
        """
        Main service - run once per IGW connection session.
        No restart logic - let main.py handle restarts.
        """
        logging.debug('TelnetProxy::service starting')

        # Initial setup - connect to boiler
        if not self.connect_client():
            raise RuntimeError("Failed to connect to boiler")

        # Run the main loop for this connection session
        logging.info('TelnetProxy: Running main loop')
        self.loop()

        # Clean exit (no restart logic)
        logging.info('TelnetProxy: Connection ended, exiting service')

class ThreadedTelnetProxy(Thread):
    """
    This class implements a Thread to run the TelnetProxy.
    """
    _tserver: Thread
    _com: PubSub
    _src_iface: bytes
    _dst_iface: bytes
    _port: int
    _ma: ThreadedMqttActuator | None = None
    _service_lock: Lock
    _appconfig: AppConfig

    def __init__(self, appconfig: AppConfig, communicator: PubSub, port: int):
        """
        Initialize the ThreadedTelnetProxy with communication channel, interfaces, and port.
        """
        self._appconfig = appconfig
        self._com = communicator
        self._src_iface = self._appconfig.gw_iface()
        self._dst_iface = self._appconfig.bl_iface()
        self._port = port
        self._ma = None
        self._service_lock = Lock()

        # Initialize the TelnetProxy instance
        super().__init__(name='TelnetProxy')
        self.tp= TelnetProxy(self._appconfig, self._com, port, self._service_lock)
        # Add any additional initialization logic here

    def request_shutdown(self) -> None:
        """Request graceful shutdown of TelnetProxy and MqttActuator."""
        logging.info("ThreadedTelnetProxy: Shutdown requested")
        self.tp.request_shutdown()
        # Also shutdown MqttActuator if running
        if self._ma:
            self._ma.request_shutdown()

    def run(self) -> None:
        """
        Run the TelnetProxy in a separate thread.
        Always cleans up MqttActuator when TelnetProxy exits.
        """
        _ts: Thread | None = None
        logging.info('telnet proxy started: %s , %s', self.tp.src_iface, self.tp.dst_iface)

        try:
            # Discover the boiler
            self.tp.discover()

            # Create and start MqttActuator
            if not self._ma:
                logging.debug("Creating ThreadedMqttActuator")
                self.tp.init_device_info(self.tp.bl_addr.decode('ascii'))
                self._ma = ThreadedMqttActuator(
                    self._appconfig, self._com,
                    self.tp.device_info(),
                    self._src_iface,
                    self._service_lock
                )
                self._ma.start()

            # Bind, listen, accept
            self.tp.bind1()
            self.tp.bind2()
            self.tp.listen1()
            self.tp.listen2()

            # Create separate threads for accepting connections
            _accept1_thread = Thread(target=self.tp.accept1, name='AcceptService1')
            _accept2_thread = Thread(target=self.tp.accept2, name='AcceptService2')
            _accept1_thread.start()
            _accept2_thread.start()

            # Service thread
            _ts = Thread(target=self.tp.service, name='TelnetProxyService')
            _ts.start()

            # Wait for service to exit (IGW disconnect)
            _ts.join()
            _accept1_thread.join(timeout=2)
            _accept2_thread.join(timeout=2)

        finally:
            # Always cleanup MqttActuator when TelnetProxy exits
            logging.info("TelnetProxy exiting, shutting down MqttActuator...")
            if self._ma:
                self._ma.request_shutdown()
                self._ma._thread.join(timeout=5)  # pylint: disable=protected-access
                if self._ma._thread.is_alive():  # pylint: disable=protected-access
                    logging.warning("MqttActuator did not exit cleanly")
                self._ma = None

            logging.info("ThreadedTelnetProxy: Run completed")
