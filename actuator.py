"""
This module defines MqttActuator, a class for controlling MQTT-enabled devices.
"""


from threading import Thread

from typing import Optional, Dict, List, Generic, TypeVar

import logging

from paho.mqtt.client import Client, MQTTMessage
from ha_mqtt_discoverable import Settings, DeviceInfo  # type: ignore
from ha_mqtt_discoverable.sensors import Select, SelectInfo  # type: ignore

import hargconfig
from shared import ChanelReceiver, BUFF_SIZE
from pubsub.pubsub import PubSub
from telnethelper import TelnetClient

class MqttBase():
    """
    common base class for MqttInformer and MqttActuator
    """
    config: hargconfig.HargConfig
    mqtt_settings: Settings.MQTT
    _device_info: DeviceInfo

    def __init__(self):
        """
        Initialize the MqttBase class.
        Sets up the configuration and MQTT settings with default values.
        Initializes device info as None.
        """
        self.config = hargconfig.HargConfig()
        #TODO remove password from code.
        self.mqtt_settings = Settings.MQTT(host="192.168.100.8",
                username="jeedom",
                password="eBg3UokK76KOWEDDUTWGEXUHxntZpV9XUDGQ8C5Xub0v4o4pE0fS2ofPxDa52A2i")

    def name(self) -> str:
        """
        Get the class name of the instance.

        Returns:
            str: The name of the class.
        """
        return self.__class__.__name__

    def _create_device_info(self, _name: str) -> None:
        """
        Create device information for MQTT discovery.

        Args:
            _name (str): The name to use for the device.
        """
        lstr = list()
        lstr.append(_name)
        self._device_info = DeviceInfo(
                            name=_name,
                            manufacturer="Hargassner",
                            sw_version="1.0",
                            hw_version="1.0",
                            identifiers=lstr)


class MqttActuator(ChanelReceiver, MqttBase):
    """
    MqttActuator is a class for controlling devices via MQTT.
    It extends MqttBase to provide functionality for sending commands to devices.
    """

    _selects: Dict[str, Select] = {}
    _main_client: Optional[Client] = None
    _boiler_config: Optional[Dict[str, List[str]]] = None
    _parameter_ids: Dict[str, str] = {}
    _client: Optional[TelnetClient] = None

    def __init__(self, communicator: PubSub, device_info: DeviceInfo):
        """
        Initialize the MqttActuator with communication and device settings.

        Args:
            communicator (PubSub): The publish/subscribe communication system
            device_info (DeviceInfo): Information about the device to control

        Note:
            This initializes both the ChanelReceiver and MqttBase parent classes,
            sets up device information, and creates a telnet client connection.
        """
        logging.debug("MqttActuator instantiated")
        logging.debug("MqttActuator.__init__ called")
        ChanelReceiver.__init__(self, communicator)  # Initialize ChanelReceiver
        MqttBase.__init__(self)  # Initialize MqttBase

        self._device_info = device_info
        self._client = TelnetClient(b'localhost', 4000)

    def _parse_parameter_response(self, data: bytes) -> dict[str, list[str]]:
        """Parse parameter responses from the boiler (PR001, PR011, etc)

        Args:
            data: Raw response from the boiler, can contain multiple parameters
                 separated by \r\n

        Returns:
            dict[str, list[str]]: A dictionary with parameter names as keys and lists of values
            Example: {
                'Mode': ['Manu', 'Arr', 'Ballon', 'Auto', 'Arr combustion'],
                'Zone 1 Mode': ['Arr', 'Auto', 'Réduire', 'Confort', '1x Confort', 'Refroid.']
            }
        """
        result: dict[str, list[str]] = {}

        # expected format:
        # $PR001;6;1;4;1;0;0;0;Mode;Manu;Arr;Ballon;Auto;Arr combustion;\r\n
        # $PR011;6;0;5;1;0;0;0;Zone 1 Mode;Arr;Auto;Réduire;Confort;1x Confort;Refroid.;\r\n
        # $--\r\n

        try:
            # Split into individual responses - using latin1 for special characters like é
            responses = data.decode('latin1').split('\r\n')
            # Process each response
            for response in responses:
                # Skip empty responses or end marker
                if not response or response == '$--':
                    continue

                # Split the response into items
                items = response.strip().split(';')

                # Validate format starts with $PR
                if not items[0].startswith('$PR'):
                    logging.error('Invalid format: expected $PR..., got %s', items[0])
                    continue

                parameter_id = items[0][1:]  # Remove the $ prefix
                logging.info('Parsing parameter %s', parameter_id)

                # Get number of items to search
                try:
                    num_items = int(items[1])
                except (ValueError, IndexError):
                    logging.error('Invalid number of items format for %s', parameter_id)
                    continue

                # Get the key (Mode or Zone 1 Mode in the examples)
                try:
                    key = items[8]
                    # Store the mapping between parameter name and its PR code
                    self._parameter_ids[key] = parameter_id
                    logging.debug("Mapped parameter '%s' to %s", key, parameter_id)
                except IndexError:
                    logging.error('No key found at position 8 for %s', parameter_id)
                    continue

                # Get the values (items after the key, excluding zeros and empty values)
                values: list[str] = []
                try:
                    for i in range(num_items):
                        item = items[9 + i]
                        # Skip empty values and zeros
                        if item and item != '0':
                            values.append(item)
                except IndexError:
                    logging.error('Not enough items in the response for %s', parameter_id)
                    continue
                result[key] = values
                logging.info('Successfully parsed %s parameter', parameter_id)

        except Exception as e:
            logging.error('Error parsing parameter responses: %s', str(e))

        return result

    def _display_parameters_config(self, config: dict[str, list[str]]) -> None:
        """Display all parameters configuration in a readable format

        Args:
            config: Dictionary containing the parsed parameter responses
            Example: {
                'Mode': ['Manu', 'Arr', 'Ballon', 'Auto', 'Arr combustion'],
                'Zone 1 Mode': ['Arr', 'Auto', 'Réduire', 'Confort', '1x Confort', 'Refroid.']
            }
        """
        if not config:
            logging.info("No parameters configuration available")
            return
        logging.info("Boiler Parameters Configuration:")
        logging.info("-" * 40)
        for key, values in config.items():
            logging.info("Parameter: %s", key)
            logging.info("Available values:")
            for idx, value in enumerate(values, 1):
                logging.info("  %d. %s", idx, value)
            logging.info("-" * 40)

        logging.info("Total parameters found: %d", len(config))

    def decode_boiler_config(self, msg: str) -> None:
        """
        Decode the boiler configuration message and store it in the instance.

        Args:
            msg (str): Configuration message, possibly prefixed with 'BoilerConfig:'
                      Expected format is a series of parameter definitions in the form:
                      $PR001;6;1;4;1;0;0;0;Mode;Manu;Arr;Ballon;Auto;Arr combustion;

        Note:
            The decoded configuration is stored in self._boiler_config
            and includes parameter names, valid values, and their mappings.
        """
        logging.debug("MqttActuator.decode_boiler_config called with msg: %s", msg)

        # Extract the actual configuration data by removing the prefix if present
        if msg.startswith('BoilerConfig:'):
            msg = msg[len('BoilerConfig:'):]
        # Convert string to bytes with latin1 encoding to match the parser's expectations
        msg_bytes = msg.encode('latin1')
        result = self._parse_parameter_response(msg_bytes)
        if result:
            self._display_parameters_config(result)
            self._boiler_config = result
        else:
            logging.warning("Failed to parse boiler configuration from message")

    # wait for the boiler configuration to be discovered
    def discover(self) -> None:
        """
        Wait for and process the boiler configuration.

        This method subscribes to the communication channel and waits until
        the boiler configuration is received and processed. It uses the
        decode_boiler_config method to parse incoming messages.

        Note:
            - Blocks until configuration is received or an error occurs
            - Uses self._channel for communication
            - Updates self._boiler_config when successful
        """
        self._msq = self._com.subscribe(self._channel, self.name())
        logging.debug("MqttActuator.discover called, subscribed to channel %s", self._channel)

        while self._boiler_config is None:
            logging.debug('Waiting for boiler configuration, calling handle with decode_boiler_config')
            try:
                self.handle(self.decode_boiler_config)
                logging.debug('Handle method completed. Boiler config status: %s',
                            'received' if self._boiler_config else 'not received yet')
            except Exception as e:
                logging.error('Error in discovery loop: %s', str(e))
                break

        logging.debug("MqttActuator.discover finished, unsubscribing from channel")
        self._com.unsubscribe(self._channel, self._msq)
        self._msq = None

    def _get_client(self) -> TelnetClient:
        """
        Get the telnet client, raising an exception if it's not initialized.
        
        Returns:
            TelnetClient: The initialized telnet client
            
        Raises:
            RuntimeError: If the client is not initialized
        """
        if self._client is None:
            raise RuntimeError("TelnetClient is not initialized")
        return self._client

    def callback(self, client: Client, data: str, message: MQTTMessage) -> None:
        """
        Handle MQTT select state change messages.

        This callback processes state changes from Home Assistant and sends
        corresponding commands to the boiler.

        Args:
            client (Client): The MQTT client that received the message
            data (str): The parameter name that changed (user_data from Select entity)
            message (MQTTMessage): The MQTT message containing the new state

        Note:
            The command sent to the boiler has the format:
            $par set "PRxxx;6;index" where:
            - PRxxx is the parameter ID
            - 6 is a fixed value
            - index is the 0-based position of the selected option
        """
        logging.debug("MqttActuator.callback called with data: %s", data)
        try:
            payload = message.payload.decode()
            logging.debug("Received payload: %s", payload)
            if not self._boiler_config or data not in self._boiler_config:
                logging.error("Received callback for unknown parameter: %s", data)
                return

            valid_options = self._boiler_config[data]
            if payload not in valid_options:
                logging.error("Invalid option '%s' for %s. Valid options: %s", payload, data, valid_options)
                return

            # Find the position of the selected option in the list (0-based index is what we want)
            option_index = valid_options.index(payload)
            # Get the parameter ID for this parameter name
            if data not in self._parameter_ids:
                logging.error("No parameter ID found for %s", data)
                return

            # Construct the command in the format $par set "PRxxx;6;index"
            param_id = self._parameter_ids[data]
            command = f'$par set "{param_id};6;{option_index}"\r\n'
            logging.info("Sending command: %s", command)
            # Send the command to the boiler
            self._get_client().send(command.encode('latin1'))
            try:
                _data = self._get_client().recv(BUFF_SIZE)
            except Exception as e:
                logging.error('Failed to receive data: %s', str(e))
                return
            logging.debug('received response %d bytes ==>%s', len(_data), repr(_data))

        except Exception as e:
            logging.error("Error processing %s selection: %s", data, str(e))

    def create_subscribers(self) -> None:
        """
        Create MQTT subscribers for each boiler parameter.

        This method creates Home Assistant MQTT Select entities for each parameter
        in the boiler configuration. Each Select entity:
        - Has a unique ID based on the parameter name
        - Is associated with the device
        - Uses the callback method to handle state changes
        - Is registered for MQTT auto-discovery

        Note:
            - Requires self._boiler_config to be populated
            - Stores Select instances in self._selects
            - Sets self._main_client from the first created Select
        """
        logging.debug("MqttActuator.create_subscribers called")
        if not self._boiler_config:
            logging.warning("No boiler configuration available. Cannot create subscribers.")
            return

        self._selects = {}  # Store all Select instances

        for param_name, options in self._boiler_config.items():
            # Create a unique ID from the parameter name (replace spaces with underscores and lowercase)
            unique_id = f"boiler_{param_name.lower().replace(' ', '_')}"

            select_info = SelectInfo(
                name=param_name,
                unique_id=unique_id,
                device=self._device_info,
                options=options,
                optimistic=True
            )
            select_settings = Settings(mqtt=self.mqtt_settings, entity=select_info)

            # Create the Select instance with the callback, passing param_name as user_data
            select = Select(select_settings, self.callback, user_data=param_name)
            self._selects[param_name] = select

            # Publish config for this select
            select.write_config()

        # Store the first select's MQTT client to use in the service method
        if self._selects:
            self._main_client = next(iter(self._selects.values())).mqtt_client
        else:
            logging.error("No selects were created")

    def service(self) -> None:
        """
        Start and run the MQTT actuator service.

        This method:
        1. Discovers the boiler configuration
        2. Establishes connection to the boiler
        3. Creates MQTT subscribers for each parameter
        4. Starts the MQTT client loop
        5. Handles graceful shutdown on interruption

        The service runs indefinitely until interrupted or an error occurs.
        Uses MQTT client's loop_forever() which properly handles reconnections
        and maintains the MQTT connection.

        Raises:
            RuntimeError: If MQTT client initialization fails
            Exception: For other unexpected errors during operation
        """

        logging.debug("MqttActuator.service called")
        # Discover the boiler configuration
        self.discover()
        # connect to the boiler
        self._get_client().connect()

        # Create all subscribers first
        self.create_subscribers()

        try:
            logging.info("Starting MQTT loop - waiting for messages...")
            # Use the base class's MQTT client loop_forever which handles reconnections
            # and doesn't block like sleep() does
            if not self._main_client:
                raise RuntimeError("No MQTT client available")
            self._main_client.loop_forever()

        except KeyboardInterrupt:
            logging.info("Shutting down MQTT Actuator...")
            if self._main_client:
                self._main_client.disconnect()
            # Disconnect all select clients
            for select in self._selects.values():
                select.mqtt_client.disconnect()
        except Exception as e:
            logging.error("Error in MQTT loop: %s", str(e))
            if self._main_client:
                self._main_client.disconnect()
            # Disconnect all select clients
            for select in self._selects.values():
                select.mqtt_client.disconnect()
            raise

T = TypeVar("T", bound=MqttActuator)

class Threaded(Generic[T]):
    """
    A generic class that runs an entity in a separate thread.

    Args:
        entity (T): The entity instance to be run in a thread. The entity must implement a `service()` method.

    Attributes:
        _entity (T): The entity being threaded.
        _thread (Thread): The thread running the entity's service method.
    """
    def __init__(self, entity: T) -> None:
        """
        Initialize the Threaded wrapper with an entity to run in a thread.

        Args:
            entity (T): The entity instance to be threaded.
                        Must implement a service() method.

        Note:
            Creates a thread named "Thread-{EntityClassName}" but does not start it.
            The thread will execute the entity's service method when started.
        """
        logging.debug("Threaded<%s> instantiated", type(entity).__name__)
        logging.debug("Threaded.__init__ called")
        self._entity = entity
        thread_name = f"Thread-{type(entity).__name__}"
        self._thread = Thread(target=self._entity.service, name=thread_name)

    def start(self) -> None:
        """
        Start the entity's service in a separate thread.

        This method starts the thread created in __init__, which runs
        the entity's service method. The thread runs independently of
        the calling thread.

        Note:
            This is a non-blocking call. The thread continues to run
            after this method returns.
        """
        logging.debug("Threaded.start called")
        self._thread.start()



class ThreadedMqttActuator(Threaded[MqttActuator]):
    """
    A Threaded wrapper for MqttActuator, allowing it to run in a separate thread.

    Args:
        device (DeviceInfo): The device information used to initialize the MqttActuator.

    Example:
        >>> device_info = DeviceInfo(...)
        >>> threaded_actuator = ThreadedMqttActuator(device_info)
        >>> threaded_actuator.start()
    """
    def __init__(self, communicator: PubSub, device_info: DeviceInfo) -> None:
        """
        Initialize a threaded MQTT actuator for the device.

        Args:
            communicator (PubSub): The publish/subscribe communication system
            device_info (DeviceInfo): Information about the device to control

        This class combines the MqttActuator with the Threaded wrapper to allow
        the actuator to run in its own thread. The actuator is created but not
        started - use the start() method to begin operation.
        """
        logging.debug("ThreadedMqttActuator instantiated")
        logging.debug("ThreadedMqttActuator.__init__ called")
        entity = MqttActuator(communicator, device_info)
        super().__init__(entity)
