"""
This module implments the TelnetProxy
"""
import socket
import select
from queue import Queue
import platform
import logging
from threading import Thread
from typing import Annotated, Tuple
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
    _mq: Queue

    def __init__(self, mq: Queue, src_iface, dst_iface, port):
        super().__init__()
        self.src_iface = src_iface
        self.dst_iface = dst_iface
        self.port = port
        self._mq = mq
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
        # redistribute BL info to the mq Queue for further use
        self._mq.put('BL_ADDR:'+str(self.bl_addr,'ascii'))
        self._mq.put('BL_PORT:'+str(self.bl_port))
    def connect(self):
        """connect to the boiler"""
        logging.info('telnet connecting to %s on port 23', repr(self.bl_addr))
        self._resend.connect((self.bl_addr, 23))

    def parse_request(self, mq: Queue, data: bytes) -> str:
        """parse the telnet request
        set _state to the state of the request/response dialog
        extract _subpart from the request"""
        _state: str = None
        _part: str = None
        _subpart: str = None
        _str_parts: list[str] = None

        _str_parts = data.decode('ascii').split('\r\n')
        for _part in _str_parts:
            logging.debug('_part=%s',_part)
            if _part.startswith('$login token'):
                logging.debug('$login token detected')
                _state = '$login token'
            elif _part.startswith('$login key'):
                logging.debug('$login key detected')
                _state = '$login key'
                _subpart = _part[11:]
                mq.put('$login key:'+_subpart)
                logging.info('$login key:%s', _subpart)
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
                mq.put('$igw set:'+_subpart)
                logging.info('$igw set:%s', _subpart)
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
            elif _part.startswith('$par get changed'):
                logging.debug('$par get changed detected')
                _state = '$par get changed'
            elif _part.startswith('$par get'): # $par get %d
                logging.debug('$par get detected')
                _state = '$par get'
            elif _part.startswith('$erract'):
                logging.debug('$erract detected')
                _state = '$erract'
            elif _part == '':
                logging.debug('empty _part')
            else:
                logging.debug('else unknown state')
                _state = 'unknown'
        logging.debug('_state/_part: %s/%s', _state, _part)
        return _state

    def parse_response_buffer(self, mq: Queue, state: str, buffer: bytes) -> str:
        """parse the response buffer sent by boiler"""
        _state: str = state
        _part: str = None
        _subpart: str = None
        _str_parts: list[str] = None

        logging.debug('parse_response input _state=%s',_state)
        _str_parts= repr(buffer)[2:-1].split('\\r\\n')
        for _part in _str_parts:
            logging.debug('part:%s', _part)
            if _state == '$login token':
                # $wwxxyyzz
                _subpart = _part[1:]
                logging.info('$login token:%s', _subpart)
                mq.put('$login token:'+_subpart)
                _state = ''
            elif _state == '$login key':
                # b'zclient login (0)\r\n$ack\r\n'
                if "zclient login" in _part:
                    logging.debug('zclient login detected')
                if _part.startswith('$ack'):
                    logging.debug('$login key $ack detected')
                    _state = ''
            elif _state == '$apiversion':
                # $1.0.1
                if _part.startswith("$"):
                    logging.debug('$apiversion $ack detected')
                    _subpart = _part[1:]
                    logging.info('$apiversion:%s', _subpart)
                    mq.put('$apiversion:'+_subpart)
                    _state = ''
            elif _state == '$setkomm':
                # $1234567 ack
                if "ack" in _part:
                    _subpart = _part[1:-4]
                    logging.info('$setkomm:%s', _subpart)
                    mq.put('$setkomm:'+_subpart)
                    _state = ''
            elif _state == '$asnr get':
                # $1.0.1
                if _part.startswith("$"):
                    logging.debug('$asnr get $ack detected')
                    _subpart = _part[1:]
                    logging.debug('subpart:%s', _subpart)
                    mq.put('$asnr get:'+_subpart)
                    _state = ''
            elif _state == '$igw set':
                if "ack" in _part:
                    logging.debug('$igw set $ack detected')
                    _state = ''
            elif "$daq stopped" in _part:
                logging.info('$daq stopped')
                _state = ''
            elif "logging disabled" in _part:
                logging.info('$logging disabled')
                _state = ''
            elif _state == '$daq desc':
                #todo review this since filtered before
                if _part.startswith('$<<') and _part.endswith('>>'):
                    logging.debug('$daq desc $ack detected')
                    _state = ''
            elif "daq started" in _part:
                logging.info('$daq started')
                _state = ''
            elif "logging enabled" in _part:
                logging.info('$logging enabled')
                _state = ''
            elif _state == '$bootversion':
                #$V2.18
                if _part.startswith("$V"):
                    logging.debug('$bootversion $ack detected')
                    _subpart = _part[2:]
                    logging.info('$bootversion:%s', _subpart)
                    mq.put('$bootversion:'+_subpart)
                    _state = ''
            elif _state == '$info':
                if _part.startswith('$KT:'):
                    logging.debug('$KT $ack detected')
                    _subpart = _part[5:]
                    logging.info('$KT:%s', _subpart)
                    mq.put('$KT:'+_subpart)
                if _part.startswith('$SWV:'):
                    logging.debug('$SWV $ack detected')
                    _subpart = _part[6:]
                    logging.info('$SWV:%s', _subpart)
                    mq.put('$SWV:'+_subpart)
                if _part.startswith('$FWV I/O:'):
                    logging.debug('$FWV I/O $ack detected')
                    _subpart = _part[10:]
                    logging.info('$FWV I/O:%s', _subpart)
                    mq.put('$FWV I/O:'+_subpart)
                if _part.startswith('$SN I/O:'):
                    logging.debug('$SN I/O $ack detected')
                    _subpart = _part[9:]
                    logging.info('$SN I/O:%s', _subpart)
                    mq.put('$SN I/O:'+_subpart)
                if _part.startswith('$SN BCE:'):
                    logging.debug('$SN BCE $ack detected')
                    _subpart = _part[9:]
                    logging.info('$SN BCE:%s', _subpart)
                    mq.put('$SN BCE:'+_subpart)
                    _state = ''
            elif _state == '$uptime':
                if _part.startswith('$'):
                    logging.debug('$uptime $ack detected')
                    _subpart = _part[1:]
                    logging.info('$uptime:%s', _subpart)
                    mq.put('$uptime:'+_subpart)
                    _state = ''
            elif _state == '$rtc get':
                if _part.startswith('$'):
                    logging.debug('$rtc get $ack detected')
                    _subpart = _part[1:]
                    logging.info('$rtc:%s', _subpart)
                    mq.put('$rtc get:'+_subpart)
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
                logging.debug('$par get all $ack detected')
                _state = ''
            elif _state == '$erract':
                # $no errors OR anything else
                logging.debug('$erract $ack detected')
                _state = ''
            else:
                logging.debug('unknown state:%s', _state)
                _state = ''
        return _state

    def analyse_data_buffer(self, _data: bytes,
                            pm: bytes, buffer: bytes,
                            mode: str, state: str) -> Tuple[bytes, bytes, str, str]:
        """analyse the data buffer"""
        _mode: str = mode
        _state: str = state
        _pm: bytes = pm
        _buffer: bytes = buffer

        if len(_data)>1 and repr(_data[0:2])=="b'pm'":
            logging.debug('pm response detected')
            _pm = _data
            if _pm[-2:] == b'\r\n':
                logging.debug('pm response is complete')
                #todo: analyse the pm response
            else:
                logging.debug('pm response is not complete')
                _mode= 'pm' # switch to mode where we gather the pm response
        if _mode == 'pm':
            _pm = _pm + _data
            if _pm[-2:] == b'\r\n':
                logging.debug('pm detected (%d bytes)',len(_pm))
                #todo: analyse the pm response
            #todo verify if _mode should be set to '' only if pm is complete
            _mode = ''
        if (repr(_data[0:2]) != "b'pm'") and (_mode != 'pm'):
            if _data[-2:] != b'\r\n':
                _mode='buffer'
            logging.debug('normal response detected %s',repr(_data))
            if _mode == 'buffer':
                _buffer = _buffer + _data
            else:
                _buffer = _data
            if _buffer[-2:] == b'\r\n':
                logging.debug('buffer is complete')
                _mode = ''
                if len(_buffer)>4 and repr(_buffer[0:4]) == "b'$<<<'":
                    logging.info('dac desq detected (%d bytes), skipped',len(_buffer))
                else:
                    _state = self.parse_response_buffer(self._mq, _state, _buffer)
                _buffer = b''

        return _pm, _buffer, _mode, _state

    def is_pm_response(self, _data: bytes) -> bool:
        """check if the data is a pm response"""
        if len(_data)>1 and repr(_data[0:2])=="b'pm'":
            return True
        return False

    def is_daq_desc(self, _buffer: bytes) -> bool:
        """check if the data is a daq description"""
        if len(_buffer)>4 and repr(_buffer[0:4]) == "b'$<<<'":
            return True
        return False

    def analyse_data_buffer_v2(self, _mq: Queue, _data: bytes,
                               pm: bytes, buffer: bytes,
                               mode: str, state: str) -> Tuple[bytes, bytes, str, str]:
        """analyse the data buffer
        _mode can have the following values:
        - '' : normal mode
        - 'pm' : special mode for pm response : modify _pm 
        - 'buffer' : special mode for buffer response : modify _buffer
        """
        _mode: str = mode
        _state: str = state
        _pm: bytes = pm
        _buffer: bytes = buffer

        if self.is_pm_response(_data):
            logging.debug('pm response detected')
            _mode= 'pm'

        if _mode == 'pm':
            if _data[-2:] == b'\r\n':
                _pm = _data
                logging.debug('pm detected (%d bytes)',len(_pm))
                #todo: analyse the pm response
                _mode = ''
            else:
                _pm = _pm + _data
            #return after processing _pm
            return _pm, _buffer, _mode, _state

        #here _mode is not 'pm'
        logging.debug('normal response detected')
        if _data[-2:] != b'\r\n':
            _mode='buffer'

        if _mode == 'buffer':
            _buffer = _buffer + _data
        else:
            _buffer = _data

        if _buffer[-2:] == b'\r\n':
            logging.debug('buffer is complete')
            _mode = '' # revert to normal mode for next data
            if self.is_daq_desc(_buffer):
                logging.info('dac desq detected (%d bytes), skipped',len(_buffer))
            else:
                _state = self.parse_response_buffer(self._mq, _state, _buffer)
            _buffer = b'' #clear working buffer
        #return after processing _buffer
        return _pm, _buffer, _mode, _state

    def loop(self):
        """loop waiting requests and replies"""
        _socket: socket.socket
        _data: bytes
        _addr: tuple
        read_sockets: list[socket.socket]
        write_sockets: list[socket.socket]
        error_sockets: list[socket.socket]
        _state: str = '' # state of the request/response dialog
        _buffer: bytes = b'' # buffer to store the data received until we have a complete response
        _pm: bytes = b'' # buffer to store special "pm" response
        _mode: str = ''
        while True:
            logging.debug('telnet waiting data')
            read_sockets, write_sockets, error_sockets = select.select([self._telnet, self._resend], [], [])
            for _socket in read_sockets:
                if _socket == self._telnet:
                    # so we received a request
                    _data, _addr = self._telnet.recvfrom(BUFF_SIZE)
                    logging.debug('telnet received  request %d bytes ==>%s',
                                 len(_data), repr(_data))
                    _state = self.parse_request(self._mq, _data)
                    logging.debug('_state-->%s',_state)
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
                    logging.debug('telnet sent back response to client')
                    # analyse the response
                    _pm, _buffer, _mode, _state = self.analyse_data_buffer_v2(self._mq, _data,
                               _pm, _buffer, _mode, _state)

class ThreadedTelnetProxy(Thread):
    """This class implements a Thread to run the TelnetProxy"""
    def __init__(self, mq: Queue, src_iface, dst_iface, port):
        super().__init__()
        self.tp= TelnetProxy(mq, src_iface, dst_iface, port)
        # Add any additional initialization logic here

    def queue(self) -> Queue:
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
