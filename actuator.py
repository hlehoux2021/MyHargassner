"""
This module defines MqttActuator, a class for controlling MQTT-enabled devices.
"""


from threading import Thread
import typing
import logging

from paho.mqtt.client import Client, MQTTMessage
from ha_mqtt_discoverable import Settings, DeviceInfo
from ha_mqtt_discoverable.sensors import Select, SelectInfo

import hargconfig
from shared import ChanelReceiver
from pubsub.pubsub import PubSub, ChanelQueue

class MqttBase():
    """
    common base class for MqttInformer and MqttActuator
    """
    config: hargconfig.HargConfig
    mqtt_settings: Settings.MQTT
    device_info: DeviceInfo

    def __init__(self):
        self.config= hargconfig.HargConfig()
        #TODO remove password from code. note, this is an experimental dev jeedom without internet access
        self.mqtt_settings= Settings.MQTT(host="192.168.100.8",
                username="jeedom",
                password="eBg3UokK76KOWEDDUTWGEXUHxntZpV9XUDGQ8C5Xub0v4o4pE0fS2ofPxDa52A2i")

    def name(self):
        return self.__class__.__name__


class MqttActuator(ChanelReceiver, MqttBase):
    """
    MqttActuator is a class for controlling devices via MQTT.
    It extends MqttBase to provide functionality for sending commands to devices.
    """
    _device_info: DeviceInfo
    _selects: dict[str, Select] = {}  # Store all Select instances
    _main_client: Client | None = None  # Store the main MQTT client
    _boiler_config: dict[str, list[str]] | None = None
    _parameter_ids: dict[str, str] = {}  # Maps parameter names to their PR codes

    def __init__(self, communicator: PubSub, device_info: DeviceInfo):
        """
        Initializes the MqttActuator with device information.
        device_info: DeviceInfo - Information about the device to control (passed by caller)
        """
        logging.debug("MqttActuator instantiated")
        logging.debug("MqttActuator.__init__ called")
        ChanelReceiver.__init__(self, communicator)  # Initialize ChanelReceiver
        MqttBase.__init__(self)  # Initialize MqttBase

        self._device_info = device_info

    def _parse_parameter_response(self, data: bytes) -> dict[str, list[str]]:
        """Parse parameter responses from the boiler (PR001, PR011, etc)
        
        Args:
            data: Raw response from the boiler, can contain multiple parameters
                 separated by \r\n

        Returns:
            dict[str, list[str]]: A dictionary with parameter names as keys and lists of non-zero values
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
                    logging.debug(f"Mapped parameter '{key}' to {parameter_id}")
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

    def decode_boiler_config(self, msg: str):
        """Decode the boiler configuration message.

        Args:
            msg: String containing the boiler configuration, possibly prefixed with 'BoilerConfig:'
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
    def discover(self):
        """wait for the boiler configuration to be discovered"""
        self._msq = self._com.subscribe(self._channel, self.name())
        logging.debug("MqttActuator.discover called, subscribed to channel %s", self._channel)
        
        while (self._boiler_config == None):
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

    # Callback for select state changes
    def callback(self, client: Client, data: str, message: MQTTMessage):
        try:
            payload = message.payload.decode()
            if not self._boiler_config or data not in self._boiler_config:
                logging.error(f"Received callback for unknown parameter: {data}")
                return

            valid_options = self._boiler_config[data]
            if payload not in valid_options:
                logging.error(f"Invalid option '{payload}' for {data}. Valid options: {valid_options}")
                return

            # Find the position of the selected option in the list (0-based index is what we want)
            option_index = valid_options.index(payload)
            
            # Get the parameter ID for this parameter name
            if data not in self._parameter_ids:
                logging.error(f"No parameter ID found for {data}")
                return
                
            # Construct the command in the format $par set "PRxxx;6;index"
            param_id = self._parameter_ids[data]
            command = f'$par set "{param_id};6;{option_index}"\r\n'
            logging.info(f"Sending command: {command}")
            
            # TODO: Send the command through the appropriate channel
            # self._com.publish(self._channel, command)
            
        except Exception as e:
            logging.error(f"Error processing {data} selection: {str(e)}")

    def create_subscribers(self):
        """
        Creates MQTT subscribers for the actuator.
        Creates one Select entity for each parameter in the boiler configuration.
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

    def service(self):
        """
        Starts the MQTT actuator and keeps it running forever.
        This method should be called to begin operation.
        Uses MQTT client's loop_forever() which properly handles
        reconnections and doesn't block the process.
        """

        logging.debug("MqttActuator.service called")
        # Discover the boiler configuration
        self.discover()
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
            logging.error(f"Error in MQTT loop: {str(e)}")
            if self._main_client:
                self._main_client.disconnect()
            # Disconnect all select clients
            for select in self._selects.values():
                select.mqtt_client.disconnect()
            raise

EntityType = typing.TypeVar("EntityType", bound= MqttActuator)



class Threaded(typing.Generic[EntityType]):
    """
    A generic class that runs an entity in a separate thread.

    Args:
        entity (EntityType): The entity instance to be run in a thread. The entity must implement a `service()` method.

    Attributes:
        _entity (EntityType): The entity being threaded.
        _thread (Thread): The thread running the entity's service method.
    """
    def __init__(self, entity: EntityType) -> None:
        """
        Initializes the Threaded class with the given entity and prepares the thread.

        Args:
            entity (EntityType): The entity instance to be threaded.
        """
        logging.debug(f"Threaded<{type(entity).__name__}> instantiated")
        logging.debug("Threaded.__init__ called")
        self._entity = entity
        self._thread = Thread(target=self._entity.service)

    def start(self) -> None:
        """
        Starts the thread, running the entity's service method in a separate thread.
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
    def __init__(self, communicator: PubSub, device_info: DeviceInfo):
        """
        Initializes the ThreadedMqttActuator with the given device information.

        Args:
            device_info (DeviceInfo): The device information for the actuator.
        """
        logging.debug("ThreadedMqttActuator instantiated")
        logging.debug("ThreadedMqttActuator.__init__ called")
        # Create a new PubSub communicator for this instance
        communicator = PubSub()
        entity = MqttActuator(communicator, device_info)
        super().__init__(entity)
