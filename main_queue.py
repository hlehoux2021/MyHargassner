"""Module providing the main function To Test the queue receiver."""
import logging
import argparse

from shared import QueueReceiver

#----------------------------------------------------------#
LOG_PATH = "./" #chemin où enregistrer les logs

logging.basicConfig(filename='trace2.log',
                    level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
                    mode='a')
logging.info('Started')


#----------------------------------------------------------#
SOCKET_TIMEOUT= 0.2
BUFF_SIZE= 1024

SRC_IFACE = b'en0' # network interface connected to the gateway
DST_IFACE = b'lo0' # network interface connected to the boiler
UDP_PORT = 35601 # destination port to which gateway is broadcasting

#----------------------------------------------------------#
def parse_command_line():
    """
    Parse the command line arguments.

    Returns:
        args (argparse.Namespace): Parsed command line arguments.
    """
    parser = argparse.ArgumentParser(description='Command line parser')
    parser.add_argument('-s', '--src_iface', type=str, help='Source interface')
    parser.add_argument('-d', '--dst_iface', type=str, help='Destination interface')
    parser.add_argument('-p', '--port', type=int, help='Source port')

    args = parser.parse_args()
    return args

# Utilisation du parseur de ligne de commande
command_line_args = parse_command_line()

if command_line_args.src_iface is not None:
    src_iface = command_line_args.src_iface

if command_line_args.dst_iface is not None:
    dst_iface = command_line_args.dst_iface

if command_line_args.port is not None:
    udp_port = command_line_args.port

#----------------------------------------------------------#

#----------------------------------------------------------#
q= QueueReceiver.QueueReceiver()
q.gw_port= -1    # source port from which gateway is sending
