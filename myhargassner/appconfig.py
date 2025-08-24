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
                'socket_timeout': '5',
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
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'myhargassner.ini')
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
        LOG_LEVELS = {
            'debug': logging.DEBUG,
            'info': logging.INFO,
            'warning': logging.WARNING,
            'error': logging.ERROR,
            'critical': logging.CRITICAL
        }
        log_level_str = self.log_level().lower()
        log_level = LOG_LEVELS.get(log_level_str, logging.INFO)
        logging.basicConfig(
            filename=self.log_path(),
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
            filemode='a',
            force=True
        )



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

    def socket_timeout(self):
        """
        Return the socket timeout value as a float (seconds).
        """
        return float(self.network.get('socket_timeout', 5))

    def buff_size(self):
        """
        Return the buffer size for network data as an integer (bytes).
        """
        return int(self.network.get('buff_size', 4096))

    def mqtt_host(self):
        """
        Return the MQTT broker host as a string.
        """
        return self.mqtt.get('host', 'localhost')

    def mqtt_port(self):
        """
        Return the MQTT broker port as an integer.
        """
        return int(self.mqtt.get('port', 1883))

    def mqtt_username(self):
        """
        Return the MQTT username as a string.
        """
        return self.mqtt.get('username', '')

    def mqtt_password(self):
        """
        Return the MQTT password as a string.
        """
        return self.mqtt.get('password', '')

    def mqtt_topic_prefix(self):
        """
        Return the MQTT topic prefix as a string.
        """
        return self.mqtt.get('topic_prefix', 'myhargassner')

    def log_path(self):
        """
        Return the log file path as a string.
        """
        return self.logging.get('log_path', './trace.log')

    def log_level(self):
        """
        Return the log level as an uppercase string (e.g., 'INFO').
        """
        return self.logging.get('log_level', 'INFO').upper()

    # Add more helpers as needed for your project
