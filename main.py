#! /usr/bin/sudo /usr/bin/env "PATH=$PATH VIRTUAL_ENV=$VIRTUAL_ENV" python
"""
Main program to run the telnet proxy, boiler listener, gateway listener
and mqqt
"""

# 100.84: <broadcast>	50000->35601	HargaWebApp
# 100.84: <broadcast>	50002->50001	hargassner.diagnostics.request
# 100.84: <broadcast>	50000->35601	get services
# 100.13: 100.84	35601->50000	HSV/CL etc *.cgi
# 100.84: 100.13	51975-->23	$login token
# 100.13: 100.84	23-->51975	$xxyyzz
# 100.13: 100.84	23->51975	F2\r\n
# 100.84: 100.13	51975->23	$login key AAAABBBBCCCCDDDDEEEEFFFF0000AAAAAA\r\n
# 100.13: 100.84	23->51975	zclient login (9999)\r\n$ack\r\n

import logging
import argparse
import time
import threading
from telnetproxy import ThreadedTelnetProxy
from boiler import ThreadedBoilerListenerSender
from gateway import ThreadedGatewayListenerSender
from mqtt import MqttInformer

from pubsub.pubsub import PubSub

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

if command_line_args.GW_IFACE:
    GW_IFACE = bytes(command_line_args.GW_IFACE,'ascii')

if command_line_args.BL_IFACE:
    BL_IFACE = bytes(command_line_args.BL_IFACE,'ascii')

#if command_line_args.port is not None:
#    UDP_PORT = int(command_line_args.port)


# Set LOG_LEVEL based on command-line arguments, using boolean flags and elif for exclusivity
if command_line_args.debug:
    LOG_LEVEL = logging.DEBUG
elif command_line_args.info:
    LOG_LEVEL = logging.INFO
elif command_line_args.warning:
    LOG_LEVEL = logging.WARNING
elif command_line_args.error:
    LOG_LEVEL = logging.ERROR
elif command_line_args.critical:
    LOG_LEVEL = logging.CRITICAL


#----------------------------------------------------------#
logging.basicConfig(filename='trace.log', level=LOG_LEVEL,
                    format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
                    filemode='a',
                    force=True)

logging.info('Started')

#----------------------------------------------------------#

#from queue import Queue,Empty

pub = PubSub()

class PubSubListener(threading.Thread):
    """ Class defining a listener used in a thread """

    def __init__(self, chanel_name, full_thread_name, communicator):
        """
        Constructor for this listener
        parameters :
        - thread_name : name of this listener
        - chanel_name : name of the channel to listen
        - full_thread_name : long name for this thread
        - communicator : pubsub message dispatching system.
        """

        threading.Thread.__init__(self, name=full_thread_name)
        self.full_thread_name = full_thread_name
        self.message_queue = communicator.subscribe(chanel_name)

    def run(self):
        """ Method called by start() method of the thread. """

        logging.info("Run start, listen to messages with a pause of 100ms between each one...")

        is_running = True
        counter = 0
        while is_running:
            message = next(self.message_queue.listen())
            logging.info("receives : id : %d : %s",
                  message['id'], message['data'])
            time.sleep(0.1)
            is_running = message['data'] != "End"
            counter += 1

pln= PubSubListener('test', 'PubSubListener', pub)
pln.start()

# MqttInfomer will receive info on the mq queue
#mi = MqttInformer(pub)

# create a telnet proxy. this will forward info to the mq queue
tln= ThreadedTelnetProxy(pub, GW_IFACE, BL_IFACE, port=23,)

# create a BoilerListener
# it will discover the boiler and forward its addr:port to Telnet Proxy through the tln queue
bls= ThreadedBoilerListenerSender(pub, BL_IFACE, GW_IFACE,delta=100)

# create a gateway listener
# it will forward info to MqttInformer through the mq queue
# it will discover the IGW and forward its addr:port to Boiler Listener through the bls queue
gls= ThreadedGatewayListenerSender(pub, GW_IFACE, BL_IFACE, UDP_PORT,delta=100)

tln.start()
bls.start()
gls.start()
#mi.start()
