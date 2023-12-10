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
        logging.info('telnet connecting to %s on port 23', self.bl_addr.decode())
        self._resend.connect((self.bl_addr, 23))


    def loop(self):
        """loop waiting requests and replies"""
        _socket: socket.socket
        _data: bytes
        _addr: tuple
        read_sockets: list[socket.socket]
        write_sockets: list[socket.socket]
        error_sockets: list[socket.socket]
        while True:
            logging.debug('telnet waiting data')
            read_sockets, write_sockets, error_sockets = select.select([self._telnet, self._resend], [], [])
            for _socket in read_sockets:
                if _socket == self._telnet:
                    # so we received a request
                    _data, _addr = self._telnet.recvfrom(BUFF_SIZE)
                    logging.info('telnet received  request %d bytes ==>%s',
                                 len(_data), _data.decode('ascii'))
                    # we should resend it
                    logging.info('resending %d bytes to %s:%d',
                                 len(_data), self.bl_addr.decode(), self.port)
                    self._resend.send(_data)
                if _socket == self._resend:
                    # so we received a reply
                    _data, _addr = self._resend.recvfrom(BUFF_SIZE)
                    logging.info('telnet received response %d bytes ==>%s',
                                 len(_data), _data.decode('ascii'))

                    logging.debug('sending %d bytes to %s:%d',
                                  len(_data), self.gw_addr.decode(), self.gwt_port)
                    self._telnet.send(_data)
                    logging.info('telnet sent back response to client')

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
