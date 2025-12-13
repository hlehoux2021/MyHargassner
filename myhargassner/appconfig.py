"""
AppConfig: Centralized configuration wrapper for MyHargassner
Provides attribute access, type conversion, and validation helpers.
"""

import logging
import argparse
import configparser
import os

class AppConfig:
    """
    AppConfig: Centralized configuration wrapper for MyHargassner.
    Handles loading, merging, and providing access to configuration values from defaults, 
    config file, and CLI arguments.
    """

    def __init__(self):
        """
        Initialize AppConfig by loading defaults, parsing CLI arguments, reading the config file,
        and merging all sources into a unified configuration dictionary.
        """
        # Set up config defaults
        self.defaults = {
            'network': {
                'gw_iface': 'eth0',
                'bl_iface': 'eth1',
                'udp_port': '35601',
                'socket_timeout': '20.0',  # Socket recv/send timeout (seconds)
                'buff_size': '4096'
            },
            'mqtt': {
                'host': 'localhost',
                'port': '1883',
                'username': '',
                # 'password' is required!
                'topic_prefix': 'myhargassner'
            },
            'logging': {
                'log_path': '/var/log/myhargassner.log',
                'log_level': 'INFO'
            },
            'timeouts': {
                # Shutdown responsiveness timeouts (all in seconds)
                'loop_timeout': '1.0',        # Main loop timeout (select/MQTT) - determines shutdown responsiveness
                'queue_timeout': '1.0',       # Message queue timeout for inter-component communication
                'retry_delay': '5.0',         # Delay before retrying failed operations
                'service_lock_delay': '1.0'   # Delay when service is locked/paused
            }
        }

        # Parse CLI args
        parser = argparse.ArgumentParser()
        parser.add_argument('-d', '--debug', action='store_true', help='Enable debug logging')
        parser.add_argument('-i', '--info', action='store_true', help='info logging level')
        parser.add_argument('-w', '--warning', action='store_true', help='warning logging level')
        parser.add_argument('-e', '--error', action='store_true', help='error logging level')
        parser.add_argument('-c', '--critical', action='store_true', help='critical logging level')
        for section, options in self.defaults.items():
            for key in options:
                parser.add_argument(f'--{key}', dest=f'{section}_{key}')
        self.args = parser.parse_args()

        # Load config file
        self._config = configparser.ConfigParser()
        config_path = os.path.join(os.getcwd(), 'myhargassner.ini')
        print("config_path=", config_path)
        self._config.read(config_path)
        print("password=", self._config.get('mqtt', 'password', fallback='NOT SET'))
        # Merge defaults, then config file, then CLI args
        for section, options in self.defaults.items():
            if section not in self._config:
                self._config[section] = {}
            for key, value in options.items():
                if key not in self._config[section] or not self._config[section][key]:
                    self._config[section][key] = value
        for arg, value in vars(self.args).items():
            if value is not None:
                if '_' in arg:
                    section, key = arg.split('_', 1)
                    if section in self._config:
                        self._config[section][key] = value
                    else:
                        self._config[section] = {key: value}

    def setup_logging(self):
        """
        Configure the Python logging system using the log path and log level from the configuration.
        Uses a standard log message format and supports all standard log levels.
        """

        VERBOSE = 15
        logging.addLevelName(VERBOSE, "VERBOSE")

        def _logger_verbose(self, msg, *args, **kwargs):
            if self.isEnabledFor(VERBOSE):
                self._log(VERBOSE, msg, args, **kwargs)

        # attach method to Logger class
        #logging.Logger.verbose = _logger_verbose
        setattr(logging.Logger, "verbose", _logger_verbose)  # type: ignore[attr-defined]
        # ...existing code...
        log_levels = {
            'debug': logging.DEBUG,
            'verbose': VERBOSE,
            'info': logging.INFO,
            'warning': logging.WARNING,
            'error': logging.ERROR,
            'critical': logging.CRITICAL
        }
        log_level_str = self.log_level.lower()
        log_level = log_levels.get(log_level_str, logging.INFO)
        logging.basicConfig(
            filename=self.log_path,
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
            filemode='a',
            force=True
        )
        # Set specific logger level
        logging.getLogger('ha_mqtt_discoverable').setLevel(logging.WARNING)
        logging.getLogger('paho.mqtt').setLevel(logging.WARNING)

    @property
    def network(self):
        """
        Return the 'network' section of the configuration.
        """
        return self._config['network']

    @property
    def mqtt(self):
        """
        Return the 'mqtt' section of the configuration.
        """
        return self._config['mqtt']

    @property
    def logging(self):
        """
        Return the 'logging' section of the configuration.
        """
        return self._config['logging']

    @property
    def timeouts(self):
        """
        Return the 'timeouts' section of the configuration.
        """
        return self._config['timeouts']

    # Helpers for type conversion and defaults

    def gw_iface(self):
        """
        Return the gateway network interface as bytes (e.g., b'eth0').
        """
        return bytes(self.network.get('gw_iface', 'eth0'), 'ascii')

    def bl_iface(self):
        """
        Return the boiler network interface as bytes (e.g., b'eth1').
        """
        return bytes(self.network.get('bl_iface', 'eth1'), 'ascii')

    def udp_port(self):
        """
        Return the UDP port for gateway/boiler communication as an integer.
        """
        return int(self.network.get('udp_port', 35601))

    @property
    def socket_timeout(self):
        """
        Return the socket timeout value as a float (seconds).
        """
        return float(self.network.get('socket_timeout', 5))

    @property
    def buff_size(self):
        """
        Return the buffer size for network data as an integer (bytes).
        """
        return int(self.network.get('buff_size', 4096))

    @property
    def mqtt_host(self):
        """
        Return the MQTT broker host as a string.
        """
        return self.mqtt.get('host', 'localhost')

    @property
    def mqtt_port(self):
        """
        Return the MQTT broker port as an integer.
        """
        return int(self.mqtt.get('port', 1883))

    @property
    def mqtt_username(self):
        """
        Return the MQTT username as a string.
        """
        return self.mqtt.get('username', '')

    @property
    def mqtt_password(self):
        """
        Return the MQTT password as a string.
        """
        return self.mqtt.get('password', '')

    @property
    def mqtt_topic_prefix(self):
        """
        Return the MQTT topic prefix as a string.
        """
        return self.mqtt.get('topic_prefix', 'myhargassner')

    @property
    def log_path(self):
        """
        Return the log file path as a string.
        """
        return self.logging.get('log_path', './trace.log')

    @property
    def log_level(self):
        """
        Return the log level as an uppercase string (e.g., 'INFO').
        """
        return self.logging.get('log_level', 'INFO').upper()

    # Timeout helpers

    def loop_timeout(self):
        """
        Return the main loop timeout as a float (seconds).
        Used by select() in TelnetProxy and MQTT client loop().
        This value determines how responsive components are to shutdown requests.
        Lower values = faster shutdown but more CPU usage.
        """
        return float(self.timeouts.get('loop_timeout', 1.0))

    def queue_timeout(self):
        """
        Return the message queue timeout as a float (seconds).
        Used for inter-component communication via PubSub message queues.
        Applies to both discovery and normal operation phases.
        """
        return float(self.timeouts.get('queue_timeout', 3.0))

    @property
    def retry_delay(self):
        """
        Return the delay before retrying failed operations as a float (seconds).
        Used when connection attempts or restarts fail.
        """
        return float(self.timeouts.get('retry_delay', 5.0))

    @property
    def service_lock_delay(self):
        """
        Return the delay when service is locked/paused as a float (seconds).
        Used when TelnetProxy service1 is waiting for lock release.
        """
        return float(self.timeouts.get('service_lock_delay', 1.0))

    # Add more helpers as needed for your project
