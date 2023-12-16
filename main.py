#! /usr/bin/sudo /usr/bin/env "PATH=$PATH VIRTUAL_ENV=$VIRTUAL_ENV" python
"""
Main program to run the telnet proxy, boiler listener and gateway listener
"""

# 100.84: <broadcast>	50000->35601	HargaWebApp
# 100.84: <broadcast>	50002->50001	hargassner.diagnostics.request
# 100.84: <broadcast>	50000->35601	get services
# 100.13: 100.84	35601->50000	HSV/CL etc *.cgi
# 100.84: 100.13	51975-->23	$login token
# 100.13: 100.84	23-->51975	$3313C1
# 100.13: 100.84	23->51975	F2\r\n
# 100.84: 100.13	51975->23	$login key 137171BD37643C72131D59797D966A730E\r\n
# 100.13: 100.84	23->51975	zclient login (7421)\r\n$ack\r\n

import logging
import argparse

from telnetproxy import ThreadedTelnetProxy
from boiler import ThreadedBoilerListenerSender
from gateway import ThreadedGatewayListenerSender
from mqtt import MqttInformer

#----------------------------------------------------------#
LOG_PATH = "./" #chemin où enregistrer les logs
LOG_LEVEL= logging.INFO

SOCKET_TIMEOUT= 0.2
BUFF_SIZE= 1024

GW_IFACE = b'eth0' # network interface connected to the gateway
BL_IFACE = b'eth1' # network interface connected to the boiler
UDP_PORT = 35601 # destination port to which gateway is broadcasting

#----------------------------------------------------------#

def parse_command_line():
    """This method parses the command line arguments"""
    parser = argparse.ArgumentParser(description='Command line parser')
    parser.add_argument('-g', '--GW_IFACE', type=str, help='Source interface')
    parser.add_argument('-b', '--BL_IFACE', type=str, help='Destination interface')
    parser.add_argument('-p', '--port', type=int, help='Source port')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('-i', '--info', action='store_true', help='info logging level')
    parser.add_argument('-w', '--warning', action='store_true', help='warning logging level')
    parser.add_argument('-e', '--error', action='store_true', help='error logging level')
    parser.add_argument('-c', '--critical', action='store_true', help='critical logging level')

    args = parser.parse_args()
    return args

# Utilisation du parseur de ligne de commande
command_line_args = parse_command_line()

if command_line_args.GW_IFACE is not None:
    GW_IFACE = bytes(command_line_args.GW_IFACE,'ascii')

if command_line_args.BL_IFACE is not None:
    BL_IFACE = bytes(command_line_args.BL_IFACE,'ascii')

if command_line_args.port is not None:
    UDP_PORT = int(command_line_args.port)

if command_line_args.debug is not None:
    LOG_LEVEL = logging.DEBUG

if command_line_args.info is not None:
    LOG_LEVEL = logging.INFO
if command_line_args.warning is not None:
    LOG_LEVEL = logging.WARNING
if command_line_args.error is not None:
    LOG_LEVEL = logging.ERROR
if command_line_args.critical is not None:
    LOG_LEVEL = logging.CRITICAL


#----------------------------------------------------------#
logging.basicConfig(filename='trace.log', level=LOG_LEVEL,
                    format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
                    filemode='a')

logging.info('Started')

#----------------------------------------------------------#

from queue import Queue,Empty
mq = Queue()

tln= ThreadedTelnetProxy(mq, GW_IFACE, BL_IFACE, 23)
bls= ThreadedBoilerListenerSender(tln.queue(), BL_IFACE, GW_IFACE)
gls= ThreadedGatewayListenerSender(mq, bls.queue(), GW_IFACE, BL_IFACE, UDP_PORT)

tln.start()
bls.start()
gls.start()

mi = MqttInformer(mq)
mi.start()

while True:
    try:
        msg = mq.get(block=True, timeout=10)
        logging.info('handleReceiveQueue: received %s', msg)
        if msg.startswith('toto:'):
            logging.info('ReceiveQueue=%s', msg.split(':')[1])
        else:
            logging.warning('ReceiveQueue: unknown message %s', msg)
    except Empty:
        logging.debug('handleReceiveQueue: no message received')
