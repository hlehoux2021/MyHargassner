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
from myhargassner.pubsub.pubsub import PubSub

# Project imports
from myhargassner.appconfig import AppConfig
from myhargassner.telnetproxy import ThreadedTelnetProxy
from myhargassner.boiler import ThreadedBoilerListenerSender
from myhargassner.gateway import ThreadedGatewayListenerSender
from myhargassner.mqtt_informer import ThreadedMqttInformer

#pylint: disable=broad-exception-caught

#----------------------------------------------------------#

app_config = AppConfig()

# Check for required password
if not app_config.mqtt_password:
    print("ERROR: MQTT password must be set in the configuration file or via command-line argument.")
    sys.exit(1)

# Set up logging using AppConfig
app_config.setup_logging()
logging.info('Started MyHargassner')

#----------------------------------------------------------#

#from queue import Queue,Empty

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


def wait_for_restart_trigger(pub: PubSub) -> str:
    """
    Wait for restart request from any component via PubSub.

    Args:
        pub: PubSub instance to subscribe to system channel

    Returns:
        str: Reason for restart
    """
    # Subscribe to system channel for restart messages
    system_queue = pub.subscribe('system', 'MainRestartMonitor')

    try:
        while True:
            try:
                # Wait for restart request message
                iterator = system_queue.listen(timeout=1.0)
                message = next(iterator)

                if message and message['data'] == 'RESTART_REQUESTED':
                    logging.info("Restart request received via PubSub")
                    return "System_Restart_Request"

            except StopIteration:
                # No message received, continue waiting
                continue

    finally:
        # Cleanup subscription
        pub.unsubscribe('system', system_queue)


def main():
    """Main entry point with restart orchestration."""
    restart_count = 0

    # optional PubSubListener for testing messages
    # pln = PubSubListener('chosen_channel_to_spy', 'PubSubListener', session_pub)
    #pln.start()
    while True: # restart_count < max_restarts:
        restart_count += 1
        logging.info("System session starting (session #%d)", restart_count)

        try:
            # Create fresh PubSub for this session
            session_pub = PubSub(max_queue_in_a_channel=9999)

            # Create all components

            mi = ThreadedMqttInformer(app_config, session_pub)
            bls = ThreadedBoilerListenerSender(app_config, session_pub, delta=100)
            gls = ThreadedGatewayListenerSender(app_config, session_pub, delta=100)
            tln = ThreadedTelnetProxy(app_config, session_pub, port=23)

            # Start all threads
            logging.info("Starting all components...")

            bls.start()
            gls.start()
            tln.start()
            mi.start()

            # Wait for restart request from any component
            logging.info("System running, waiting for restart request...")
            restart_reason = wait_for_restart_trigger(session_pub)
            logging.info("Restart requested: %s", restart_reason)

            # Orchestrate graceful shutdown of ALL components
            logging.info("Orchestrating shutdown of all components...")

            # Request shutdown via request_shutdown() method
            gls.request_shutdown()
            bls.request_shutdown()
            tln.request_shutdown()
            mi.request_shutdown()
            # Note: PubSubListener doesn't have request_shutdown yet

            # Wait for all threads to exit cleanly (with timeout)
            logging.info("Waiting for threads to exit...")
            gls.join(timeout=5)
            bls.join(timeout=5)
            tln.join(timeout=5)
            mi.join(timeout=5)

            # Check for zombie threads
            if gls.is_alive():
                logging.warning("GatewayListener did not exit cleanly")
            if bls.is_alive():
                logging.warning("BoilerListener did not exit cleanly")
            if tln.is_alive():
                logging.warning("TelnetProxy did not exit cleanly")
            if mi.is_alive():
                logging.warning("MqttInformer did not exit cleanly")

            logging.info("All components stopped")
            logging.info("Waiting for next IGW connection...")
            time.sleep(2)  # Brief pause before restart

        except KeyboardInterrupt:
            logging.info("Keyboard interrupt, exiting...")
            break
        except Exception as e:
            logging.error("Unexpected error: %s", e, exc_info=True)
            time.sleep(5)  # Wait before retry on error

    logging.info("System exiting after %d sessions", restart_count)

if __name__ == '__main__':
    main()
