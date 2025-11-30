"""
    This module implements analysis of Gateway requests and Boiler Responses
"""

# Standard library imports
import logging
import time
from typing import Tuple

# Third party imports
from myhargassner.pubsub.pubsub import PubSub

# Project imports
import myhargassner.hargconfig as hargconfig

class Analyser():
    """
    analyser for the dialog with boiler
    """
    config: hargconfig.HargConfig
    _channel= "info" # Channel to publish discoverd info about the boiler (from the dialog between gateway and boiler)
    _com: PubSub # every data receiver should have a PubSub communicator

    _pmstamp: float = 0.0
    _values: dict # telnet pm values
    _pm: bytes = b''

    def __init__(self, communicator: PubSub) -> None:
        self._com = communicator

        self._values= {}
        self.config= hargconfig.HargConfig()

    def push(self, key: str, subpart: str):
        """
        publish a result to the queue where it will be used
        """
        self._com.publish(self._channel, f"{key}££{subpart}")

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

    def parse_request(self, data: bytes) -> Tuple[str, bool]:
        """parse the telnet request
        set _state to the state of the request/response dialog
        extract _subpart from the request

        Returns:
            Tuple of (state, session_end_requested)
            session_end_requested is True when $igw clear is detected
        """
        _state: str = ''
        _part: str = ''
        _subpart: str = ''
        _str_parts: list[str] = []
        _session_end_requested: bool = False

        logging.log(15, 'Analyser: request=%s', repr(data))
        _str_parts = data.decode('ascii').split('\r\n')
        for _part in _str_parts:
            #logging.debug('_part=%s',_part)
            if _part.startswith('$login token'):
                logging.debug('$login token detected')
                _state = '$login token'
            elif _part.startswith('$login key'):
                logging.debug('$login key detected')
                _state = '$login key'
                _subpart = _part[11:]
                self.push('KEY', _subpart)
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
                self.push('IGW', _subpart)
            elif _part.startswith('$igw clear'):
                logging.info('$igw clear detected - session end requested')
                _state = '$igw clear'
                _session_end_requested = True
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
                #logging.debug('empty _part')
                pass
            else:
                logging.debug('Analyser received unhandled request %s - treating as passthrough', _part)
                _state = 'passthrough'  # mark it as passthrough
        logging.debug('_state/_part: %s/%s', _state, _part)
        return _state, _session_end_requested

    def _parse_response_buffer(self, state: str, buffer: bytes,
                               session_end_requested: bool = False) -> Tuple[str, bool, bool]:
        """parse the response buffer sent by boiler

        Args:
            state: Current request state
            buffer: Response buffer from boiler
            session_end_requested: True if waiting for $igw clear response

        Returns:
            Tuple of (state, login_done, session_end_complete)
        """
        _state: str = state
        _part: str = ''
        _subpart: str = ''
        _str_parts: list[str] = []
        _login_done: bool = False
        _session_end_complete: bool = False

        logging.debug('Analyser.parse_response_buffer _state=%s', _state)
        if _state == 'passthrough':
            logging.warning('New response (passthrough) %s', repr(buffer))
        _str_parts= repr(buffer)[2:-1].split('\\r\\n')
        for _part in _str_parts:
            logging.debug('part %d:[%s]', len(_part), _part)
            if _state == '$login token':
                # $wwxxyyzz
                _subpart = _part[1:]
                self.push('TOKEN', _subpart)
                _state = ''
            elif _state == '$login key':
                # b'zclient login (0)\r\n$ack\r\n'
                if "zclient login" in _part:
                    logging.debug('zclient login detected')
                    logging.log(15, 'IGW login done')
                    _login_done = True
                if _part.startswith('$ack'):
                    logging.debug('$login key $ack detected')
                    _state = ''
            elif _state == '$apiversion':
                # $1.0.1
                if _part.startswith("$"):
                    logging.debug('$apiversion $ack detected')
                    _subpart = _part[1:]
                    self.push('API', _subpart)
                    _state = ''
            elif _state == '$setkomm':
                # $1234567 ack
                if "ack" in _part:
                    _subpart = _part[1:-4]
                    self.push('SETKOMM', _subpart)
                    _state = ''
            elif _state == '$asnr get':
                # $1.0.1
                if _part.startswith("$"):
                    logging.debug('$asnr get $ack detected')
                    _subpart = _part[1:]
                    self.push('ASNR', _subpart)
                    _state = ''
            elif _state == '$igw set':
                if "ack" in _part:
                    logging.debug('$igw set $ack detected')
                    _state = ''
            elif _state == '$igw clear':
                # TRIGGER 1: Check for $igw clear response
                if "$ack" in _part:
                    logging.debug('$igw clear $ack detected')
                    if session_end_requested:
                        logging.info('$igw clear session complete')
                        _session_end_complete = True
                    _state = ''
            elif "$daq stopped" in _part:
                logging.debug('$daq stopped')
                _state = ''
            elif "logging disabled" in _part:
                logging.debug('$logging disabled')
                _state = ''
            elif _state == '$daq desc':
                #todo review this since filtered before
                if _part.startswith('$<<') and _part.endswith('>>'):
                    logging.debug('$daq desc $ack detected')
                    _state = ''
            elif "daq started" in _part:
                logging.debug('$daq started')
                _state = ''
            elif "logging enabled" in _part:
                logging.debug('$logging enabled')
                _state = ''
            elif _state == '$bootversion':
                #$V2.18
                if _part.startswith("$V"):
                    logging.debug('$bootversion $ack detected')
                    _subpart = _part[2:]
                    self.push('BOOT', _subpart)
                    _state = ''
            elif _state == '$info':
                if _part.startswith('$KT:'):
                    logging.debug('$KT $ack detected')
                    _subpart = _part[5:]
                    self.push('KT', _subpart)
                if _part.startswith('$SWV:'):
                    logging.debug('$SWV $ack detected')
                    _subpart = _part[6:]
                    self.push('SWV', _subpart)
                if _part.startswith('$FWV I/O:'):
                    logging.debug('$FWV I/O $ack detected')
                    _subpart = _part[10:]
                    self.push('FWV', _subpart)
                if _part.startswith('$SN I/O:'):
                    logging.debug('$SN I/O $ack detected')
                    _subpart = _part[9:]
                    self.push('SNIO', _subpart)
                if _part.startswith('$SN BCE:'):
                    logging.debug('$SN BCE $ack detected')
                    _subpart = _part[9:]
                    self.push('SNBCE', _subpart)
                    _state = ''
            elif _state == '$uptime':
                if _part.startswith('$'):
                    logging.debug('$uptime $ack detected')
                    _subpart = _part[1:]
                    self.push('UPTIME', _subpart)
                    _state = ''
            elif _state == '$rtc get':
                if _part.startswith('$'):
                    logging.debug('$rtc get $ack detected')
                    _subpart = _part[1:]
                    self.push('RTC', _subpart)
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
        return _state, _login_done, _session_end_complete

    def analyse_pm(self, pm: bytes):
        """
        analyse the pm buffer regularly sent by the boiler and publish what's found
        """
        _part: str = ''
        i: int = -1
        _str_parts: list[str] = []
        logging.debug('analyse_pm %d bytes ==>%s',len(pm), repr(pm))
        _str_parts = pm.decode('ascii').split(' ')
        for _part in _str_parts:
            if ((i in self._values) and (_part != self._values[i])) or (i not in self._values):
                self._values[i]= _part
                if i in self.config.map:
                    logging.debug('pm %s --> %s', self.config.map[i],_part)
                    self.push(self.config.map[i], _part)
            i=i+1

    def analyse_data_buffer(self, _data: bytes,
                               buffer: bytes,
                               mode: str, state: str,
                               session_end_requested: bool = False
                            ) -> Tuple[bytes, str, str, bool, bool]:
        """analyse the data buffer sent by the boiler
        it can be a buffer response for a request of the IGW
            values split by \\r\\n
        if can be bytes starting with 'pm' , values split by spaces
        _mode can have the following values:
        - '' : normal mode
        - 'pm' : special mode for pm response : modify _pm
        - 'buffer' : special mode for buffer response : modify _buffer

        Args:
            session_end_requested: True if $igw clear was sent and we're waiting for response

        Returns:
            Tuple of (buffer, mode, state, login_done, session_end_complete)
        """
        _mode: str = mode
        _state: str = state
        _buffer: bytes = buffer
        _login_done: bool = False
        _session_end_complete: bool = False

        if self.is_pm_response(_data):
            logging.debug('pm response detected')
            _mode= 'pm'

        if _mode == 'pm':
            if _data[-2:] == b'\r\n':
                _time= time.time()
                if (self._pmstamp == 0) or ((_time - self._pmstamp) > self.config.scan):
                    self._pm = _data
                    self._pmstamp = _time
                    logging.debug('pm full buffer detected (%d bytes)',len(self._pm))
                    self.analyse_pm(self._pm)
                _mode = ''
            else:
                self._pm = self._pm + _data
            return _buffer, _mode, _state, False, False

        #here _mode is not 'pm'
        logging.debug('normal response detected')
        if _data[-2:] != b'\r\n':
            _mode='buffer'

        if _mode == 'buffer':
            _buffer = _buffer + _data
        else:
            _buffer = _data

        if _buffer[-2:] == b'\r\n':
            logging.debug('buffer complete (%d bytes): %s',len(_buffer), repr(_buffer))
            _mode = '' # revert to normal mode for next data
            if self.is_daq_desc(_buffer):
                logging.log(15, 'daq desc detected (%d bytes), skipped',len(_buffer))
                # do not process daq desc further and reset _state for next request
                _state= ''
            else:
                # we will push the data to mqtt_actuator for further processing
                self._com.publish("track", _buffer.decode('latin-1'))
                _state, _login_done, _session_end_complete = self._parse_response_buffer(
                    _state, _buffer, session_end_requested)
            _buffer = b'' #clear working buffer
        #return after processing _buffer
        return _buffer, _mode, _state, _login_done, _session_end_complete
