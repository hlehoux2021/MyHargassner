import queue, logging
from typing import Annotated
import annotated_types
from time import sleep


class SharedData():
    gw_port: Annotated[int, annotated_types.Gt(0)]
    bl_port: Annotated[int, annotated_types.Gt(0)]
    gw_addr: Annotated[bytes, annotated_types.MaxLen(15)]
    bl_addr: Annotated[bytes, annotated_types.MaxLen(15)]

    def __init__(self):
        self.gw_port = 0    # source port from which gateway is sending
        self.gw_addr= b''   # to save the gateway ip adress when discovered
        self.bl_addr= b''   # to save the boiler ip address when discovered
        self.bl_port= 0     # destination port to which boiler is listening

class SharedDataReceiver(SharedData):
#    gw_port: Annotated[int, annotated_types.Gt(0)]
#    bl_port: Annotated[int, annotated_types.Gt(0)]
#    gw_addr: Annotated[bytes, annotated_types.MaxLen(15)]
#    bl_addr: Annotated[bytes, annotated_types.MaxLen(15)]
    rq: queue.Queue

    def __init__(self):
        super().__init__()
#        self.gw_port = 0    # source port from which gateway is sending
#        self.gw_addr= b''   # to save the gateway ip adress when discovered
#        self.bl_addr= b''   # to save the boiler ip address when discovered
#        self.bl_port= 0     # destination port to which boiler is listening
        self.rq = queue.Queue()

    def handleReceiveQueue(self):
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


#from threading import Thread
#
#class Test(Thread, SharedDataReceiver):
#    def __init__(self):
#        super().__init__()
#        self.rq = queue.Queue()
#
#    def run(self):
#        while True:
#            self.handleReceiveQueue()
#            sleep(1)
#----------------------------------------------------------#
#logging.basicConfig(filename='trace2.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s', filemode='a')
#logging.info('Started')
#
# q= SharedDataReceiver()

#t=Test()
