"""This module contains shared data structures and functions for project"""
import queue
import logging
from pydantic import BaseModel, PositiveInt, Annotated
import annotated_types


class QueueReceiver(BaseModel):
    """
    A class that represents a queue receiver.
    This is used to exchange information discovered about the gateway and the boiler.

    Attributes:
        gw_port (PositiveInt): The source port from which the gateway is sending.
        bl_port (Annotated[int, annotated_types.Gt(0)]): The destination port to which the boiler is listening.
        gw_addr (Annotated[bytes, annotated_types.Len(min_length=0, max_length=15)]): The IP address of the gateway.
        bl_addr (Annotated[bytes, annotated_types.Len(min_length=0, max_length=15)]): The IP address of the boiler.
        rq (Annotated[queue.Queue]): The receive queue.

    Methods:
        handle(): Handles the messages received in the receive queue.
    """

    gw_port: PositiveInt
    bl_port: Annotated[int, annotated_types.Gt(0)]
    gw_addr: Annotated[bytes, annotated_types.Len(min_length=0, max_length=15)]
    bl_addr: Annotated[bytes, annotated_types.Len(min_length=0, max_length=15)]
    rq: Annotated[queue.Queue]

    def __init__(self):
        super().__init__()
        self.gw_port = 0    # source port from which gateway is sending
        self.gw_addr= b''   # to save the gateway ip address when discovered
        self.bl_addr= b''   # to save the boiler ip address when discovered
        self.bl_port= 0     # destination port to which boiler is listening
        self.rq = queue.Queue()

    def handle(self):
        """
        Handles the messages received in the receive queue.

        It processes the messages in the receive queue and updates the corresponding attributes
        based on the message content.
        """
        try:
            msg = self.rq.get(block=True, timeout=10)
            logging.debug('handleReceiveQueue: received %s', msg)
            if msg.startswith('GW_ADDR:'):
                self.gw_addr = msg.split(':')[1]
                logging.debug('handleReceiveQueue: gw_addr=%s', self.gw_addr)
            elif msg.startswith('GW_PORT:'):
                self.gw_port = int(msg.split(':')[1])
                logging.debug('handleReceiveQueue: gw_port=%d', self.gw_port)
            elif msg.startswith('BL_ADDR:'):
                self.bl_addr = msg.split(':')[1]
                logging.debug('handleReceiveQueue: bl_addr=%s', self.bl_addr)
            elif msg.startswith('BL_PORT:'):
                self.bl_port = int(msg.split(':')[1])
                logging.debug('handleReceiveQueue: bl_port=%d', self.bl_port)
            else:
                logging.debug('handleReceiveQueue: unknown message %s', msg)
        except queue.Empty:
            logging.debug('handleReceiveQueue: no message received')
