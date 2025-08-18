"""
Module for MQTT client to handle to boiler
"""


import logging
from queue import Empty
from ha_mqtt_discoverable import Settings, DeviceInfo
from ha_mqtt_discoverable.sensors import Sensor, SensorInfo

import hargconfig
from actuator import MqttBase

from pubsub.pubsub import PubSub,ChanelQueue



class MySensor(Sensor):
    def __init__(self,_name: str, _id: str, _dict: dict, _config:hargconfig.HargConfig, _device_info: DeviceInfo, _mqtt: Settings.MQTT):
        if _id in _dict:
            _state= _dict[_id]
        else:
            _state= ""
        if _id in _config.wanted:
            _info= SensorInfo(name= _name,
                              state= _state,
                              unique_id= _id+"/"+_dict["BL_ADDR"],
                              unit_of_measurement= _config.desc[_id]['unit'],
                              device=_device_info)
        else:
            _info= SensorInfo(name= _name,
                              state= _state,
                              unique_id= _id+"/"+_dict["BL_ADDR"],
                              device=_device_info)
        _settings= Settings(mqtt=_mqtt, entity= _info)
        super().__init__(_settings)
        if _id in _config.desc:
            self.set_attributes({'description': _config.desc[_id]['desc']})
        
class MqttInformer(MqttBase):
    """
    class MqttInformer provides Boiler information via MQTT to MqttDiscovery plugin in Jeedom or Home Assistant
    it receives data on a ChannelQueue and publishes it to the MQTT broker.
    
    It will create the device_info and sensors from the boiler data.

    Name: will be BL_ADDR ip adress of the boiler

    """
    _msq: ChanelQueue | None = None  # Message queue for receiving messages
    _com: PubSub
    _channel= "info" # Channel to receive info about the boiler

    _dict: dict
    _sensors: dict
    _token: Sensor
    _web_app: Sensor
    _key: Sensor
    _kt: Sensor
#    _ma: ThreadedMqttActuator | None = None
    _device_info: DeviceInfo | None = None
    def __init__(self,communicator: PubSub):
        super().__init__()
#        self._ma = None
        self._device_info = None
        self._com = communicator
        self._dict = {}
        self._sensors= {}
        
    def _init_sensors(self):
        """This method init the basis sensors"""
        if 'HargaWebApp' in self._dict:
            logging.debug('HargaWebApp in dict --> set')
            self._web_app.set_state(self._dict['HargaWebApp'])
        if 'TOKEN' in self._dict:
            logging.debug('TOKEN in dict --> set')
            self._token.set_state(self._dict['TOKEN'])
        if 'KEY' in self._dict:
            logging.debug('KEY in dict --> set')
            self._key.set_state(self._dict['KEY'])

    def _create_sensor(self, _name: str, _id: str) -> Sensor:
        if _id in self._dict:
            _state= self._dict[_id]
        else:
            _state= ""
        if _id in self.config.wanted:
            _info= SensorInfo(name= _name,
                              state= _state,
                              unique_id= _id+"/"+self._dict["BL_ADDR"],
                              unit_of_measurement= self.config.desc[_id]['unit'],
                              device=self._device_info)
        else:
            _info= SensorInfo(name= _name,
                              state= _state,
                              unique_id= _id+"/"+self._dict["BL_ADDR"],
                              device=self._device_info)
        _settings= Settings(mqtt=self.mqtt_settings, entity= _info)
        _sensor= Sensor(_settings)
        if _id in self.config.desc:
            _sensor.set_attributes({'description': self.config.desc[_id]['desc']})
        return _sensor

    def _create_all_sensors(self):
        # create basis mandatory sensors
        # sensors before normal mode
        self._web_app = MySensor("HargaWebApp","HargaWebApp", self._dict, self.config, self._device_info, self.mqtt_settings)
        self._token = MySensor("Login Token", "TOKEN", self._dict, self.config, self._device_info, self.mqtt_settings)
        self._key = MySensor("Login Key", "KEY", self._dict, self.config, self._device_info, self.mqtt_settings)
        # sensors coming in normal mode
        self._kt = self._create_sensor("KT","KT")
        # sensors wanted from the pm buffer
        for _part in self.config.wanted:
            if _part not in self.config.desc:
                logging.warning(f"Missing description for {_part} in config")
                continue
            _sensor= self._create_sensor(self.config.desc[_part]['name'],_part)
            _sensor.set_state("")
            self._sensors[_part]= _sensor


    def start(self):
        """This method runs the MqttInformer, waiting for message on _info_queue"""
        _stage: str = ''

        self._msq = self._com.subscribe(self._channel, self.name())

        while True:
            try:
                logging.debug('MqttInformer: waiting for messages')
                logging.debug('MQTT ChannelQueue size: %d', self._msq.qsize())
                
                # Use a non-blocking iterator with a timeout
                iterator = self._msq.listen(timeout=3)  
                try:
                    _message = next(iterator)
                except StopIteration:
                    logging.error('StopIteration: No message received, continuing...')
                    continue
                    
                if not _message:
                    logging.debug('MqttInfomer no message received')
                    continue
                msg = _message['data']
                logging.debug('MqttInformer: received %s', msg)
                _str_parts = msg.split('££')
                if not _str_parts or len(_str_parts) < 2:
                    logging.warning('MqttInformer: invalid message format %s', msg)
                    continue
                if _stage == 'device_info_ok':
                    # we are in normal mode, we handle new or modified values
                    logging.debug('normal mode analyse message')
                    if ((_str_parts[0] in self._dict) and (_str_parts[1] != self._dict[_str_parts[0]])) or (not _str_parts[0] in self._dict):
                        # the value is new or has changed
                        logging.info('adding new value:[%s/%s]', _str_parts[0], _str_parts[1])
                        self._dict[_str_parts[0]] = _str_parts[1]
                        if _str_parts[0] == 'HargaWebApp':
                            self._web_app.set_state(_str_parts[1])
                        if _str_parts[0] == 'KT':
                            self._kt.set_state(_str_parts[1])
 #                       if _str_parts[0] == 'SWV':
 #                           self._swv.set_state(_str_parts[1])
                        # treat sensors from telnet pm buffer
                        if _str_parts[0] in self.config.wanted and _str_parts[0] in self._sensors:
                            logging.info('updating state of sensor:%s',_str_parts[0])
                            self._sensors[_str_parts[0]].set_state(_str_parts[1])
                    else:
                        logging.debug('ignored [%s/%s]', _str_parts[0], _str_parts[1])
                else:
                    # device_info is not yes init
                    logging.debug("device_info not ready")
                    self._dict[_str_parts[0]] = _str_parts[1]
                    logging.info('adding new value [%s:%s] to dict', _str_parts[0], _str_parts[1])
                    if 'BL_ADDR' in self._dict:
                        logging.debug("BL_ADDR:%s",self._dict["BL_ADDR"])
                    else:
                        logging.debug("BL_ADDR missing")
                    # temporary version: we use only BL_ADDR to init the device_info
                    # todo enrich the device_info with info from telnet dialog
                    # and implement a way to inform MqttActuator in a differed way
                    if 'BL_ADDR' in self._dict:
                        # we have all the info to init device_info
                        logging.info('Boiler device_info is complete')
                        # Define the device. At least one of `identifiers` or `connections` must be supplied
                        self._create_device_info(self._dict["BL_ADDR"])
                        logging.debug("Device Info initialized")
                        self._create_all_sensors()
                        _stage = 'device_info_ok'
                        # now we init the already available sensors
                        self._init_sensors()
            except Empty:
                logging.debug("handleReceiveQueue: no message received")
            logging.debug('MqttInformer stage is now %s', _stage)
        # whenever we exit the loop, we unsubscribe from the channel
        self._com.unsubscribe(self._channel, self._msq)
        self._msq = None

