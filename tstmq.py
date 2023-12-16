import time
from ha_mqtt_discoverable import Settings, DeviceInfo
from ha_mqtt_discoverable.sensors import BinarySensor, BinarySensorInfo

# Configure the required parameters for the MQTT broker
mqtt_settings = Settings.MQTT(host="192.168.100.8",username="jeedom",password="0y96wXQJ0E8KHjEyLdacPq95RGQEOdjpCLDskj7LWWC9EihjCJXbZOFZ9m4KCMWu")

# Define the device. At least one of `identifiers` or `connections` must be supplied
device_info = DeviceInfo(name="My device", identifiers="device_id")

# Associate the sensor with the device via the `device` parameter
# `unique_id` must also be set, otherwise Home Assistant will not display the device in the UI
motion_sensor_info = BinarySensorInfo(name="My motion sensor", device_class="motion", unique_id="my_motion_sensor", device=device_info)

motion_settings = Settings(mqtt=mqtt_settings, entity=motion_sensor_info)

# Instantiate the sensor
motion_sensor = BinarySensor(motion_settings)

# Change the state of the sensor, publishing an MQTT message that gets picked up by HA
#motion_sensor.on()
#motion_sensor.off()

# An additional sensor can be added to the same device, by re-using the DeviceInfo instance previously defined
door_sensor_info = BinarySensorInfo(name="My door sensor", device_class="door", unique_id="my_door_sensor", device=device_info)
door_settings = Settings(mqtt=mqtt_settings, entity=door_sensor_info)

# Instantiate the sensor
door_sensor = BinarySensor(door_settings)

# Change the state of the sensor, publishing an MQTT message that gets picked up by HA
#door_sensor.on()
#door_sensor.off()

# The two sensors should be visible inside Home Assistant under the device `My device`
while True:
	motion_sensor.on()
	time.sleep(3)
	door_sensor.off()
	time.sleep(5)
	motion_sensor.off()
	time.sleep(3)
	door_sensor.on()
	time.sleep(2)

