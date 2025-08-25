"""
MqttActuator is a class for controlling devices via MQTT.
It extends MqttBase to provide functionality for sending commands to devices.
"""

# Standard library imports
import logging
import threading
import socket

from typing import Optional, Dict, Generic, TypeVar, Union

# Third party imports
from paho.mqtt.client import Client, MQTTMessage
from ha_mqtt_discoverable import Settings, DeviceInfo  # type: ignore
from ha_mqtt_discoverable.sensors import Select, SelectInfo, Number, NumberInfo # type: ignore

from myhargassner.pubsub.pubsub import PubSub

# Project imports
from myhargassner.appconfig import AppConfig
from myhargassner.telnethelper import TelnetClient
from myhargassner.core import ChanelReceiver
from myhargassner.mqtt_base import MqttBase


class MqttActuator(ChanelReceiver, MqttBase):
    """
    MqttActuator is a class for controlling devices via MQTT.
    It extends MqttBase to provide functionality for sending commands to devices.
    """

    _selects: Dict[str, Select] = {}  # Stores Select entities by parameter name
    _numbers: Dict[str, Number] = {}  # Stores Number entities by parameter name

    _main_client: Optional[Client] = None
    _boiler_config: Optional[Dict[str, dict]] = None
    _client: Optional[TelnetClient] = None
    src_iface: bytes
    _service_lock: threading.Lock

    def __init__(self, appconfig: AppConfig, communicator: PubSub, device_info: DeviceInfo, src_iface: bytes, lock: threading.Lock) -> None: # pylint: disable=line-too-long
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
        MqttBase.__init__(self, appconfig)  # Initialize MqttBase
        self.src_iface = src_iface
        self._device_info = device_info
        self._service_lock = lock
        self._client = TelnetClient(self.src_iface, b'', buffer_size=self._appconfig.buff_size(), port=4000)

    def _parse_parameter_response(self, data: bytes) -> dict[str, dict]:
        """Parse parameter responses from the boiler, including numeric and select types.

        Args:
            data: Raw response from the boiler, can contain multiple parameters
                 separated by $ (each response starts with $)

        Returns:
            dict[str, dict]:
                For select: { 'Mode': { 'type': 'select', 'options': [...] } }
                For number: { 'Zone 1 Temp. ambiante jour': { 'type': 'number', ... } }
        """
        result: dict[str, dict] = {}
        try:
            text = data.decode('latin1')
            # Explanation:
            # text.split('$') splits the input string text at every $ character.
            # This produces a list of substrings, but the $ is removed from each part.
            # The list comprehension iterates over each substring r from the split.
            # if r.strip() filters out any empty or whitespace-only substrings.
            # f"${r}" adds the $ back to the start of each substring, reconstructing each response to start with $.
            responses = [f"${r}" for r in text.split('$') if r.strip()]
            for response in responses:
                # Remove trailing semicolons and whitespace
                response = response.strip().rstrip(';')
                if not response or response == '$--':
                    continue
                items = response.split(';')
                # Numeric parameter format:
                # $id;type;current;min;max;step;unit;default;0;0;0;name
                # Example: $4;3;19.500;14.000;26.000;0.500;C;20.000;0;0;0;Zone 1 Temp. ambiante jour
                # Format explanation:
                # - id: Numeric parameter ID (e.g., 4)
                # - type: Parameter type (3 for numeric)
                # - current: Current value (e.g., 19.500)
                # - min: Minimum allowed value (e.g., 14.000)
                # - max: Maximum allowed value (e.g., 26.000)
                # - step: Increment step (e.g., 0.500)
                # - unit: Unit of measurement (e.g., C for Celsius)
                # - default: Default value (e.g., 20.000)
                # - 0;0;0: Reserved configuration values
                # - name: Parameter name (e.g., "Zone 1 Temp. ambiante jour")
                if items[0].startswith('$') and items[0][1:].isdigit():
                    try:
                        key = items[0][1:]
                        current = float(items[2])
                        min_val = float(items[3])
                        max_val = float(items[4])
                        increment = float(items[5])
                        unit = items[6]
                        default = float(items[7])
                        name = items[11] if len(items) > 11 else f"Param {key}"
                        result[name] = {
                            'type': 'number',
                            'key': int(key),
                            'current': current,
                            'min': min_val,
                            'max': max_val,
                            'increment': increment,
                            'unit': unit,
                            'default': default
                        }
                    except Exception as e:
                        logging.error(f"Failed to parse numeric parameter: {response} ({e})")
                    continue
                # Select parameter format (PR = Parameter Response):
                # $PRxxx;6;current;max;default;0;0;0;name;value1;value2;...;0;
                # Example: $PR011;6;0;5;1;0;0;0;Zone 1 Mode;Arr;Auto;Réduire;Confort;1x Confort;Refroid.;0;
                # Format explanation:
                # - PRxxx: Parameter ID (e.g., PR011)
                # - 6: Parameter type for select
                # - current: Current selected index (0-based)
                # - max: Maximum index (number of options minus 1)
                # - default: Default option index
                # - 0;0;0: Reserved configuration values
                # - name: Parameter name (e.g., "Zone 1 Mode")
                # - value1,value2,...: Available options (e.g., "Arr", "Auto", etc.)
                # - trailing 0: Protocol terminator
                if items[0].startswith('$PR'):
                    try:
                        logging.debug("Parsing select parameter: %s", response)
                        max_index = int(items[3])  # The max index value (number of options - 1)
                        num_items = max_index + 1  # Total number of options
                        raw_current_index = int(items[2]) if len(items) > 2 else 0
                        default_index = int(items[4]) if len(items) > 4 else 0  # Default option index
                        key = items[8]
                        logging.debug("Select parameter: key=%s,max_index=%d, num_items=%d, current_index=%d, default_index=%d",
                                    key, max_index, num_items, raw_current_index, default_index)
                        # Get all available values (num_items is max_index + 1)
                        all_values = []
                        for i in range(num_items):
                            try:
                                item = items[9 + i]
                                all_values.append(item)
                            except IndexError:
                                logging.warning("Not enough items for value %d in response", i)
                                break
                        logging.debug("All values for %s: %s", key, all_values)
                        # Get current value directly from index
                        current_value = None
                        if 0 <= raw_current_index < len(all_values):
                            current_value = all_values[raw_current_index]
                            logging.debug("Current value from index %d: %s", raw_current_index, current_value)
                        # Remove any remaining empty strings from options list
                        values = [v for v in all_values if v]
                        logging.debug("Filtered values for %s: %s", key, values)
                        # Get default value from index
                        default_value = None
                        if 0 <= default_index < len(all_values):
                            default_value = all_values[default_index]
                            logging.debug("Default value from index %d: %s", default_index, default_value)

                        result[key] = {
                            'type': 'select',
                            'options': values,
                            'command_id': items[0][1:],  # Store the PRxxx ID
                            'current': current_value,
                            'default': default_value,  # Add default value
                            'raw_values': all_values,  # Store all values for debugging
                            'raw_index': raw_current_index,
                            'default_index': default_index  # Store default index for reference
                        }
                        logging.debug("Final parameter config for %s: %s", key, result[key])
                    except Exception as e:
                        logging.error(f"Failed to parse select parameter: {response} ({e})")
                    continue
                logging.warning(f"Unknown parameter format: {response}")
        except Exception as e:
            logging.error('Error parsing parameter responses: %s', str(e))
        return result

    def _display_parameters_config(self, config: dict[str, dict]) -> None:
        """Display all parameters configuration in a readable format (select and number types)."""
        if not config:
            logging.info("No parameters configuration available")
            return
        logging.info("Boiler Parameters Configuration:")
        logging.info("-" * 40)
        for key, value in config.items():
            logging.info("Parameter: %s", key)
            logging.info("Type: %s", value.get('type', 'unknown'))
            if value.get('type') == 'select':
                logging.info("Command ID: %s", value.get('command_id'))
                logging.info("Available values:")
                for idx, v in enumerate(value.get('options', []), 1):
                    logging.info("  %d. %s", idx, v)
            elif value.get('type') == 'number':
                logging.info("Parameter ID: %s", value.get('key'))
                logging.info("Current value: %s", value.get('current'))
                logging.info("Default value: %s", value.get('default'))
                logging.info("Range: %s to %s", value.get('min'), value.get('max'))
                logging.info("Increment: %s", value.get('increment'))
                logging.info("Unit: %s", value.get('unit'))
            # Display all raw values for debugging
            logging.debug("Raw configuration:")
            for k, v in value.items():
                logging.debug("  %s: %s", k, v)
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

    def callback_select(self, client: Client, data: str, message: MQTTMessage) -> None:  # pylint: disable=unused-argument
        """
        Handle MQTT select state change messages.
        """
        logging.debug("MqttActuator.callback_select called with data: %s", data)
        with self._service_lock:
            try:
                param_id = data  # data is already the param_id
                payload = message.payload.decode()
                logging.debug("Received payload: %s for parameter ID: %s", payload, param_id)
                # Find parameter info from boiler config
                if not self._boiler_config:
                    logging.error("No boiler configuration available")
                    return
                param_info = None
                for info in self._boiler_config.values():
                    if info.get('command_id') == param_id:
                        param_info = info
                        break
                if not param_info:
                    logging.error("Received callback for unknown parameter ID: %s", param_id)
                    return
                if param_info.get('type') != 'select':
                    logging.error("Callback received for non-select parameter ID: %s", param_id)
                    return
                options = param_info.get('options', [])
                if payload not in options:
                    logging.error("Invalid option '%s' for %s. Valid options: %s", payload, param_id, options)
                    return
                option_index = options.index(payload)
                command = f'$par set "{param_id};6;{option_index}"\r\n'
                logging.info("Sending command: %s", command)
                new_mode = self._send_command_and_parse_response(command, param_id, value_type='select')
                if new_mode:
                    logging.info('Received new mode for %s: %s', param_id, new_mode)
                    select = self._selects.get(param_id)
                    if select is not None:
                        # Verify the received mode is in the list of options
                        new_mode_str = str(new_mode).strip()
                        if new_mode_str in param_info['options']:
                            logging.debug('Setting select state to: %s', new_mode_str)
                            select.select_option(new_mode_str)
                        else:
                            logging.warning('Received invalid mode %s not in options: %s',
                                         new_mode_str, param_info['options'])
                            # Fall back to the requested value since we know it's valid
                            select.select_option(payload)
                    else:
                        logging.warning("No Select found for parameter ID: %s", param_id)
                else:
                    logging.info('No new mode found for %s in response, keeping requested value: %s',
                               param_id, payload)
                    # If we don't get a response, keep the requested value
                    select = self._selects.get(param_id)
                    if select is not None:
                        select.select_option(payload)
            except Exception as e:
                logging.error("Error processing %s selection: %s", data, str(e))
            logging.debug("MqttActuator.callback_select finished, lock released")

    def create_select(self, param_name: str, param_info: dict) -> None:
        """
        Create and register a Home Assistant MQTT Select entity for a select-type parameter.
        """
        unique_id = f"boiler_{param_name.lower().replace(' ', '_')}"
        select_info = SelectInfo(
            name=param_name,
            unique_id=unique_id,
            device=self._device_info,
            options=param_info['options'],
            optimistic=True
        )
        select_settings = Settings(mqtt=self.mqtt_settings, entity=select_info)
        # Get the command ID to use for the select
        param_id = param_info.get('command_id')
        if not param_id:
            logging.error(f"No command_id found for select parameter {param_name}")
            return
        select = Select(select_settings, self.callback_select, user_data=param_id)
        self._selects[param_id] = select
        select.write_config()
        # Set initial value if available
        if param_info.get('current'):
            try:
                current_value = param_info['current']
                logging.debug("Setting current value for %s to %s via MQTT", param_name, current_value)
                # This will automatically publish to the correct MQTT state topic
                select.select_option(current_value)
            except Exception as e:
                logging.warning("Failed to set current value for select %s: %s", param_name, e)
        elif param_info.get('default'):
            try:
                # Use the configured default value if no current value
                default_value = param_info['default']
                logging.debug("Setting configured default value for %s to %s via MQTT", param_name, default_value)
                select.select_option(default_value)
            except Exception as e:
                logging.warning("Failed to set default value for select %s: %s", param_name, e)
                # Fallback to first option if default value fails
                if param_info.get('options'):
                    try:
                        initial_value = param_info['options'][0]
                        logging.debug("Falling back to first option for %s: %s via MQTT", param_name, initial_value)
                        select.select_option(initial_value)
                    except Exception as e2:
                        logging.warning("Failed to set fallback value for select %s: %s", param_name, e2)

    def callback_number(self, client: Client, data: str, message: MQTTMessage) -> None: #pylint disable=unused-argument
        """
        Handle MQTT number state change messages.
        """
        logging.debug("MqttActuator.callback_number called with data: %s", data)
        with self._service_lock:
            try:
                param_id = data  # data is already the param_id
                payload = message.payload.decode()
                logging.debug("Received payload: %s for parameter ID: %s", payload, param_id)
                if not self._boiler_config:
                    logging.error("No boiler configuration available")
                    return
                param_info = None
                for info in self._boiler_config.values():
                    if str(info.get('key', '')) == param_id:
                        param_info = info
                        break
                if not param_info:
                    logging.error("Received callback for unknown parameter ID: %s", param_id)
                    return
                if param_info.get('type') != 'number':
                    logging.error("Callback received for non-number parameter ID: %s", param_id)
                    return
                try:
                    value = float(payload)
                except Exception as e:
                    logging.error("Invalid payload for number entity: %s (%s)", payload, e)
                    return
                command = f'$par set "{param_id};3;{value}"\r\n'
                logging.info("Sending command: %s", command)
                new_value = self._send_command_and_parse_response(command, param_id, value_type='number')
                if new_value is not None:
                    logging.info('Final new value for param %s (id: %s): %s', data, param_id, new_value)
                    number = self._numbers.get(param_id)
                    if number is not None:
                        try:
                            number.set_value(float(new_value))
                        except Exception as e:
                            logging.warning('Failed to update number entity: %s', e)
                    else:
                        logging.warning("No Number found for parameter ID: %s", param_id)
                else:
                    logging.info('No new value extracted for param %s (id: %s)', data, param_id)
            except Exception as e:
                logging.error("Error in callback_number for %s: %s", data, str(e))
            logging.debug("MqttActuator.callback_number" \
            " finished, lock released")

    def create_number(self, param_name: str, param_info: dict) -> None:
        """
        Create and register a Home Assistant MQTT Number entity for a number-type parameter.
        """
        unique_id = f"boiler_{param_name.lower().replace(' ', '_')}"
        number_info = NumberInfo(
            name=param_name,
            unique_id=unique_id,
            device=self._device_info,
            min=param_info['min'],
            max=param_info['max'],
            step=param_info['increment'],
            unit_of_measurement=param_info['unit'],
            mode="slider",
            optimistic=True
        )
        number_settings = Settings(mqtt=self.mqtt_settings, entity=number_info)
        # Get the numeric ID
        param_id = str(param_info.get('key', ''))
        if not param_id:
            logging.error(f"No key found for number parameter {param_name}")
            return
        number = Number(number_settings, self.callback_number, user_data=param_id)
        if not hasattr(self, '_numbers'):
            self._numbers = {}
        self._numbers[param_id] = number
        number.write_config()
        # Optionally set initial value
        try:
            number.set_value(param_info['current'])
        except Exception:
            pass


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
        self._numbers = {}  # Store all Number instances

        for param_name, param_info in self._boiler_config.items():
            if param_info.get('type') == 'select':
                self.create_select(param_name, param_info)
            elif param_info.get('type') == 'number':
                self.create_number(param_name, param_info)

        # Store the first valid select's MQTT client to use in the service method
        self._main_client = None
        for select in self._selects.values():
            client = getattr(select, 'mqtt_client', None)
            if isinstance(client, Client):
                self._main_client = client
                break
        if self._main_client is None:
            logging.error("No valid MQTT client found in selects.")

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
            logging.debug("self._main_client is: %r", self._main_client)
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
            logging.critical("Error in MQTT loop: %s", str(e))
            if self._main_client:
                self._main_client.disconnect()
            # Disconnect all select clients
            for select in self._selects.values():
                select.mqtt_client.disconnect()
            logging.critical("MQTT Actuator encountered a critical error and terminated.")
            raise

    def _send_command_and_parse_response(self, command: str, param_id: str, *, value_type: str) -> Union[float, str, None]:
        """
        Send a command to the boiler and parse the response for select or number.
        Args:
            command (str): The command to send
            param_id (str): The parameter ID
            value_type (str): 'select' or 'number'
        Returns:
            The new value/mode if found, else None
        """
        self._get_client().send(command.encode('latin1'))
        buffer = b''
        found_ack = False
        max_tries = 20
        tries = 0
        ack_token = '$ack' # if value_type == 'select' else '$a'
        result_float: float | None = None
        result_str: str | None = None
        while not found_ack and tries < max_tries:
            tries += 1
            try:
                chunk = self._get_client().recv()
            except socket.timeout:
                logging.warning('No data received from boiler (try %d/%d)', tries, max_tries)
                # Try to reconnect if connection was closed
                try:
                    self._get_client().connect()
                    # Resend the command after reconnecting
                    self._get_client().send(command.encode('latin1'))
                except Exception as reconnect_error:
                    logging.error('Failed to reconnect: %s', str(reconnect_error))
                    break
                continue
            except socket.error as e:
                logging.error('Socket error during recv: %s', str(e))
                # Try to reconnect on socket errors
                try:
                    self._get_client().connect()
                    # Resend the command after reconnecting
                    self._get_client().send(command.encode('latin1'))
                except Exception as reconnect_error:
                    logging.error('Failed to reconnect: %s', str(reconnect_error))
                    break
                continue
            if not chunk:
                logging.warning('No data received from boiler (try %d/%d)', tries, max_tries)
                continue
            logging.debug('Received chunk: %s', chunk)
            buffer += chunk
            # Split buffer into lines
            while b'\r\n' in buffer:
                line, buffer = buffer.split(b'\r\n', 1)
                line_str = line.decode('latin1', errors='replace').strip()
                if not line_str:
                    continue
                if line_str.startswith('pm'):
                    logging.debug('Discarded pm buffer: %s', line_str)
                    continue
                if line_str == ack_token:
                    found_ack = True
                    logging.debug('Received %s, ending response loop', ack_token)
                    break
                if '$err' in line_str or '$permission denied' in line_str:
                    logging.warning('Received error or permission denied: %s', line_str)
                    found_ack = True
                    break
                if line_str.startswith('zERR'):
                    logging.error('Received zERR response: %s', line_str)
                    break
                # Look for the new value/mode line: zPa N: <param_id> (<name>) = <value>
                if line_str.startswith(f'zPa N: {param_id}'):
                    parts = line_str.split('=', 1)
                    if len(parts) == 2:
                        try:
                            if value_type == 'number':
                                result_float = float(parts[1].strip())
                            else:
                                result_str = parts[1].strip()
                            logging.info('Extracted new value for %s: %s', param_id, parts[1].strip())
                        except Exception:
                            pass
        if not found_ack and tries >= max_tries:
            logging.warning('Exiting response loop after %d tries without %s or error', max_tries, ack_token)
        if value_type == 'number':
            return result_float
        else:
            return result_str

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
        self._thread = threading.Thread(target=self._entity.service, name=thread_name)

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
    def __init__(self, appconfig: AppConfig, communicator: PubSub, device_info: DeviceInfo, src_iface: bytes, lock: threading.Lock) -> None: # pylint: disable=line-too-long
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
        entity = MqttActuator(appconfig, communicator, device_info, src_iface, lock)
        super().__init__(entity)
