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

# Standard library imports
import logging
import threading
import sys
import time

# Third party imports
from pubsub.pubsub import PubSub

# Project imports
from appconfig import AppConfig
from telnetproxy import ThreadedTelnetProxy
from boiler import ThreadedBoilerListenerSender
from gateway import ThreadedGatewayListenerSender
from mqtt_informer import MqttInformer

#----------------------------------------------------------#

app_config = AppConfig()

# Check for required password
if not app_config.mqtt_password():
    print("ERROR: MQTT password must be set in the configuration file or via command-line argument.")
    sys.exit(1)

# Set up logging using AppConfig
app_config.setup_logging()
logging.info('Started MyHargassner')

#----------------------------------------------------------#

#from queue import Queue,Empty

pub = PubSub(max_queue_in_a_channel=9999)

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
mi = MqttInformer(app_config, pub)

# create a telnet proxy. this will forward info to the mq queue
tln = ThreadedTelnetProxy(app_config, pub, port=23)

# create a BoilerListener
# it will discover the boiler and forward its addr:port to Telnet Proxy through the tln queue
bls = ThreadedBoilerListenerSender(app_config, pub, delta=100)

# create a gateway listener
# it will forward info to MqttInformer through the mq queue
# it will discover the IGW and forward its addr:port to Boiler Listener through the bls queue
gls = ThreadedGatewayListenerSender(app_config, pub, delta=100)

tln.start()
bls.start()
gls.start()
mi.start()
