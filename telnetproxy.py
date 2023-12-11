"""
This module implments the TelnetProxy
"""
import socket
import select
import queue
import platform
import logging
from threading import Thread
from typing import Annotated
import annotated_types

from shared import SharedDataReceiver,SOCKET_TIMEOUT,BUFF_SIZE

class TelnetProxy(SharedDataReceiver):
    """
    This class implements the TelnetProxy
    """
    src_iface: bytes
    dst_iface: bytes
    port: Annotated[int, annotated_types.Gt(0)]
    _listen: socket.socket
    _resend: socket.socket
    _telnet: socket.socket

    def __init__(self, src_iface, dst_iface, port):
        super().__init__()
        self.src_iface = src_iface
        self.dst_iface = dst_iface
        self.port = port
        self._listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if platform.system() == 'Linux':
            self._listen.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self.src_iface)
        self._listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self._listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # we will now create the socket to resend the telnet request
        self._resend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._resend.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self._resend.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._resend.settimeout(SOCKET_TIMEOUT)

    def bind(self):
        """bind the telnet socket"""
        logging.debug('telnet binding to port %s', self.port)
        self._listen.bind(('', self.port))

    def listen(self):
        """listen for a telnet connection"""
        logging.debug('telnet listening')
        self._listen.listen()

    def accept(self):
        """accept a telnet connection"""
        _addr: tuple
        logging.debug('telnet accepting a connection')
        self._telnet, _addr = self._listen.accept()
        logging.info('telnet connection from %s:%d accepted', _addr[0], _addr[1])
        # remember the source port from which gateway is telneting
        self.gwt_port = _addr[1]

    # wait for the boiler address and port to be discovered
    def discover(self):
        """wait for the boiler address and port to be discovered"""
        while (self.bl_port == 0) or (self.bl_addr == b''):
            logging.debug('waiting for the discovery of the boiler address and port')
            self.handle()

    def connect(self):
        """connect to the boiler"""
        logging.info('telnet connecting to %s on port 23', repr(self.bl_addr))
        self._resend.connect((self.bl_addr, 23))

    def parse_request(self, data: bytes):
        """parse the telnet request
        set _state to the state of the request/response dialog
        extract _subpart from the request"""
        _str_parts = repr(data).split('\r\n')
        for _part in _str_parts:
            if _part.startswith('$login token'):
                logging.debug('$login token detected')
                _state = '$login token'
            elif _part.startswith('$login key'):
                logging.debug('$login key detected')
                _state = '$login key'
                _subpart = _part[11:]
                logging.debug('subpart:%s', _subpart)
            elif _part.startswith('$apiversion'):
                logging.debug('$apiversion detected')
                _state = '$apiversion'
            elif _part.startswith('$setkomm'):
                logging.debug('$setkomm detected')
                _state = '$setkomm'
            elif _part.startswith('$asnr get'):
                logging.debug('$asnr get detected')
                _state = '$asnr get'
            elif _part.startswith('$igw set'):
                logging.debug('$igw set detected')
                _state = '$igw set'
                _subpart = _part[9:]
                logging.debug('subpart:%s', _subpart)
            elif _part.startswith('$daq stop'):
                logging.debug('$daq stop detected')
                _state = '$daq stop'
            elif _part.startswith('$logging disable'):
                logging.debug('$logging disable detected')
                _state = '$logging disable'
            elif _part.startswith('$daq desc'):
                logging.debug('$daq desc detected')
                _state = '$daq desc'
            elif _part.startswith('$daq start'):
                logging.debug('$daq start detected')
                _state = '$daq start'
            elif _part.startswith('$logging enable'):
                logging.debug('$logging enable detected')
                _state = '$logging enable'
            elif _part.startswith('$bootversion'):
                logging.debug('$bootversion detected')
                _state = '$bootversion'
            elif _part.startswith('$info'):
                logging.debug('$info detected')
                _state = '$info'
            elif _part.startswith('$uptime'):
                logging.debug('$uptime detected')
                _state = '$uptime'
            elif _part.startswith('$rtc get'):
                logging.debug('$rtc get detected')
                _state = '$rtc get'
            elif _part.startswith('$par get all'):
                logging.debug('$par get all detected')
                _state = '$par get all'
            elif _part.startswith('$par get'): # $par get %d
                logging.debug('$par get detected')
                _state = '$par get'
            elif _part.startswith('$par get changed'):
                logging.debug('$par get changed detected')
                _state = '$par get changed'
            elif _part.startswith('$erract'):
                logging.debug('$erract detected')
                _state = '$erract'
            else:
                _state = 'unknown'

    def loop(self):
        """loop waiting requests and replies"""
        _socket: socket.socket
        _data: bytes
        _addr: tuple
        read_sockets: list[socket.socket]
        write_sockets: list[socket.socket]
        error_sockets: list[socket.socket]
        _state: str # state of the request/response dialog
        _str: str = None
        _subpart: str = None
        _str_parts: list[str] = None
        _buffer: bytes = b'' # buffer to store the data received until we have a complete response
        _pm: bytes = b'' # buffer to store special "pm" response
        while True:
            logging.debug('telnet waiting data')
            read_sockets, write_sockets, error_sockets = select.select([self._telnet, self._resend], [], [])
            for _socket in read_sockets:
                if _socket == self._telnet:
                    # so we received a request
                    _data, _addr = self._telnet.recvfrom(BUFF_SIZE)
                    logging.debug('telnet received  request %d bytes ==>%s',
                                 len(_data), repr(_data))

                    # we should resend it
                    logging.debug('resending %d bytes to %s:%d',
                                 len(_data), repr(self.bl_addr), self.port)
                    self._resend.send(_data)
                if _socket == self._resend:
                    # so we received a reply
                    _data, _addr = self._resend.recvfrom(BUFF_SIZE)
                    logging.debug('telnet received response %d bytes ==>%s',
                                 len(_data), repr(_data))

                    logging.debug('sending %d bytes to %s:%d',
                                  len(_data), self.gw_addr.decode(), self.gwt_port)
                    self._telnet.send(_data)
                    logging.info('telnet sent back response to client')
                    # analyse the response
                    if _data[0:1] == b'pm':
                        logging.debug('pm response detected')
                        _pm = _data
                        if _pm[len(_pm)-1:len(_pm)] == b'\r\n':
                            logging.debug('pm response is complete')
                            #todo: analyse the pm response
                        else:
                            logging.debug('pm response is not complete')
                            _mode= 'pm' # switch to mode where we gather the pm response
                    if _mode == 'pm':
                        _pm = _pm + _data
                        if _pm[len(_pm)-1:len(_pm)] == b'\r\n':
                            logging.debug('pm response is complete')
                            #todo: analyse the pm response
                        _mode = ''
                    if (_data[0:1] != b'pm') and (_mode != 'pm'):
                        logging.debug('normal response detected')
                        if _mode == 'buffer':
                            _buffer = _buffer + _data
                        else:
                            _buffer = _data
                        if _buffer[len(_buffer)-1:len(_buffer)] == b'\r\n':
                            logging.debug('buffer is complete')
                            _mode = ''
                            _str_parts= repr(_buffer).split('\r\n')
                            for _part in _str_parts:
                                logging.debug('part:%s', _part)
                                if _state == '$login token':
                                    # $wwxxyyzz\r\n
                                    _subpart = _part[1:]
                                    logging.debug('subpart:%s', _subpart)
                                    _state = ''
                                elif _state == '$login key':
                                    # zclient login (0)\r\n$ack\r\n
                                    if _part.startswith('zclient login'):
                                        logging.debug('zclient login detected')
                                    if _part.startswith('$ack'):
                                        logging.debug('$login key $ack detected')
                                        _state = ''
                                elif _state == '$apiversion':
                                    # $1.0.1\r\n
                                    if _part.startswith('$'):
                                        logging.debug('$apiversion $ack detected')
                                        _subpart = _part[1:]
                                        logging.debug('subpart:%s', _subpart)
                                        _state = ''
                                elif _state == '$setkomm':
                                    # $1234567 ack\r\n
                                    if _part.startswith('$') and _part.endswith('ack'):
                                        _subpart = _part[1:-4]
                                        logging.debug('subpart:{%s}', _subpart)
                                        _state = ''
                                elif _state == '$asnr get':
                                    # $1.0.1\r\n
                                    if _part.startswith('$'):
                                        logging.debug('$asnr get $ack detected')
                                        _subpart = _part[1:]
                                        logging.debug('subpart:%s', _subpart)
                                        _state = ''
                                elif _state == '$igw set':
                                    if _part == '$ack':
                                        logging.debug('$igw set $ack detected')
                                        _state = ''
                                elif _state == '$daq stop':
                                    if _part == '$daq stopped':
                                        logging.debug('$daq stop $ack detected')
                                        _state = ''
                                elif _state == '$logging disable':
                                    if _part == '$logging disabled':
                                        logging.debug('$logging disable $ack detected')
                                        _state = ''
                                elif _state == '$daq desc':
                                    if _part.startswith('$<<') and _part.endswith('>>'):
                                        logging.debug('$daq desc $ack detected')
                                        _state = ''
                                elif _state == '$daq start':
                                    if _part == '$daq started':
                                        logging.debug('$daq start $ack detected')
                                        _state = ''
                                elif _state == '$logging enable':
                                    if _part == '$logging enabled':
                                        logging.debug('$logging enable $ack detected')
                                        _state = ''
                                elif _state == '$bootversion':
                                    if _part.startswith('$'):
                                        logging.debug('$bootversion $ack detected')
                                        _subpart = _part[1:]
                                        logging.debug('subpart:%s', _subpart)
                                        _state = ''
                                elif _state == '$info':
                                    if _part.startswith('$KT:'):
                                        logging.debug('$KT $ack detected')
                                        _subpart = _part[5:]
                                        logging.debug('subpart:%s', _subpart)
                                    if _part.startswith('$SWV:'):
                                        logging.debug('$SWV $ack detected')
                                        _subpart = _part[6:]
                                        logging.debug('subpart:%s', _subpart)
                                    if _part.startswith('$FWV I/O:'):
                                        logging.debug('$FWV I/O $ack detected')
                                        _subpart = _part[10:]
                                        logging.debug('subpart:%s', _subpart)
                                    if _part.startswith('$SN I/O:'):
                                        logging.debug('$SN I/O $ack detected')
                                        _subpart = _part[9:]
                                        logging.debug('subpart:%s', _subpart)
                                    if _part.startswith('$SN BCE:'):
                                        logging.debug('$SN BCE $ack detected')
                                        _subpart = _part[9:]
                                        logging.debug('subpart:%s', _subpart)
                                        _state = ''
                                elif _state == '$uptime':
                                    if _part.startswith('$'):
                                        logging.debug('$uptime $ack detected')
                                        _subpart = _part[1:]
                                        _state = ''
                                elif _state == '$rtc get':
                                    if _part.startswith('$'):
                                        logging.debug('$rtc get $ack detected')
                                        _subpart = _part[1:]
                                        logging.debug('subpart:%s', _subpart)
                                        _state = ''
                                elif _state == '$par get changed':
                                    if _part == '$--':
                                        logging.debug('$par get changed $ack detected')
                                        _state = ''
                                elif _state == '$par get':
                                    if _part.startswith('$'):
                                        logging.debug('$par get $ack detected')
                                        _subpart = _part[1:] # value of the parameter asked by IGW
                                        _state = ''
                                elif _state == '$par get all':
                                    _state = ''
                                elif _state == '$erract':
                                    # $no errors OR anything else
                                    _state = ''

class ThreadedTelnetProxy(Thread):
    """This class implements a Thread to run the TelnetProxy"""
    def __init__(self, src_iface, dst_iface, port):
        super().__init__()
        self.tp= TelnetProxy(src_iface, dst_iface, port)
        # Add any additional initialization logic here

    def queue(self) -> queue.Queue:
        """
        This method returns the queue to receive data from.
        """
        return self.tp.queue()

    def run(self):
        logging.info('telnet proxy started: %s , %s', self.tp.src_iface, self.tp.dst_iface)

        self.tp.bind()

        self.tp.listen()

        self.tp.accept()

        # wait for the boiler address and port to be discovered
        self.tp.discover()

        # boiler is listening on port 23
        self.tp.connect()

        # now we can loop waiting requests and replies
        self.tp.loop()
