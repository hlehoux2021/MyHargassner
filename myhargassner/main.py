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


def stop_components(components: list[threading.Thread]) -> None:
    """
    Stop the components of a session and release their resources.

    Requests shutdown of every component, waits for the started ones to exit,
    then closes their sockets. Safe to call with components that were created
    but not started (e.g. when the session failed while starting).

    Args:
        components: Threaded components of the session, in creation order
    """
    logging.info("Orchestrating shutdown of all components...")
    for component in components:
        component.request_shutdown()  # type: ignore[attr-defined]
    # Note: PubSubListener doesn't have request_shutdown yet

    # Wait for all threads to exit cleanly (with timeout)
    logging.info("Waiting for threads to exit...")
    for component in components:
        if component.ident is None:
            continue  # never started
        component.join(timeout=5)
        if component.is_alive():
            logging.warning("%s did not exit cleanly", component.name)

    # Release the sockets explicitly: do not rely on garbage collection
    for component in components:
        close = getattr(component, 'close', None)
        if close is None:
            continue
        try:
            close()
        except Exception as e:
            logging.warning("Error closing %s: %s", component.name, e)
    logging.info("All components stopped")


def main():
    """Main entry point with restart orchestration."""
    restart_count = 0

    # optional PubSubListener for testing messages
    # pln = PubSubListener('chosen_channel_to_spy', 'PubSubListener', session_pub)
    #pln.start()
    while True: # restart_count < max_restarts:
        restart_count += 1
        logging.info("System session starting (session #%d)", restart_count)
        components: list[threading.Thread] = []  # stopped at the end of the session, whatever happens
        pause = 2  # Brief pause before restart

        try:
            # Create fresh PubSub for this session
            session_pub = PubSub(max_queue_in_a_channel=9999)

            # Create all components
            mi = ThreadedMqttInformer(app_config, session_pub)
            components.append(mi)
            # the gateway listener relays to the boiler only once the boiler listener is bound
            boiler_ready = threading.Event()
            bls = ThreadedBoilerListenerSender(app_config, session_pub, delta=100, boiler_ready=boiler_ready)
            components.append(bls)
            gls = ThreadedGatewayListenerSender(app_config, session_pub, delta=100, boiler_ready=boiler_ready)
            components.append(gls)
            tln = ThreadedTelnetProxy(app_config, session_pub, port=23)
            components.append(tln)

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

        except KeyboardInterrupt:
            logging.info("Keyboard interrupt, exiting...")
            break
        except Exception as e:
            logging.error("Unexpected error: %s", e, exc_info=True)
            pause = 5  # Wait before retry on error
        finally:
            # Orchestrate graceful shutdown of ALL components, also after an error,
            # so that the next session does not compete with this one
            stop_components(components)

        logging.info("Waiting for next IGW connection...")
        time.sleep(pause)

    logging.info("System exiting after %d sessions", restart_count)

if __name__ == '__main__':
    main()
