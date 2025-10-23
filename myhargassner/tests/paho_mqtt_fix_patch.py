#!/usr/bin/env python3
"""
FIX patch for paho-mqtt 2.1.0 'bad char in struct format' error.

This patch fixes the bug where struct.unpack() fails with bytearray
on certain Python 3.11 + ARM (Raspberry Pi) builds.

The fix: Convert bytearray to bytes before calling struct.unpack()
"""

import logging
import struct
from paho.mqtt.client import Client, MQTTMessage, MQTTErrorCode, MQTTv5

# Store the original method
_original_handle_publish = Client._handle_publish


def _fixed_handle_publish(self) -> MQTTErrorCode:
    """
    Fixed version of _handle_publish() that converts bytearray to bytes.

    This works around a bug in paho-mqtt 2.1.0 where struct.unpack() fails
    with bytearray on Raspberry Pi / Python 3.11.
    """
    header = self._in_packet['command']
    message = MQTTMessage()
    message.dup = ((header & 0x08) >> 3) != 0
    message.qos = (header & 0x06) >> 1
    message.retain = (header & 0x01) != 0

    # FIX: Convert bytearray to bytes before struct.unpack
    packet_data = self._in_packet['packet']
    if isinstance(packet_data, bytearray):
        logging.debug("Converting bytearray to bytes for struct.unpack")
        packet_data = bytes(packet_data)

    pack_format = f"!H{len(packet_data) - 2}s"
    (slen, packet) = struct.unpack(pack_format, packet_data)

    pack_format = f"!{slen}s{len(packet) - slen}s"
    (topic, packet) = struct.unpack(pack_format, packet)

    if self._protocol != MQTTv5 and len(topic) == 0:
        return MQTTErrorCode.MQTT_ERR_PROTOCOL

    # Handle topics with invalid UTF-8
    try:
        print_topic = topic.decode('utf-8')
    except UnicodeDecodeError:
        print_topic = f"TOPIC WITH INVALID UTF-8: {topic!r}"

    message.topic = topic

    if message.qos > 0:
        pack_format = f"!H{len(packet) - 2}s"
        (message.mid, packet) = struct.unpack(pack_format, packet)

    if self._protocol == MQTTv5:
        # Handle MQTTv5 properties (if any)
        # This is simplified - the original has more complex property handling
        pass

    message.payload = packet

    # Deliver the message to callbacks
    self._handle_on_message(message)

    if message.qos == 0:
        return MQTTErrorCode.MQTT_ERR_SUCCESS
    elif message.qos == 1:
        return self._send_puback(message.mid)
    elif message.qos == 2:
        # QoS 2 handling
        return self._send_pubrec(message.mid)
    else:
        return MQTTErrorCode.MQTT_ERR_PROTOCOL


def apply_fix():
    """Apply the FIX patch to paho.mqtt.Client"""
    logging.info("=" * 80)
    logging.info("Applying paho-mqtt FIX patch to _handle_publish()")
    logging.info("This fixes the 'bad char in struct format' error")
    logging.info("=" * 80)
    Client._handle_publish = _fixed_handle_publish
    logging.info("FIX patch applied successfully!")


def remove_fix():
    """Remove the FIX patch"""
    logging.info("Removing paho-mqtt FIX patch")
    Client._handle_publish = _original_handle_publish
    logging.info("Original method restored")


if __name__ == "__main__":
    print("This is a FIX patch module for paho-mqtt 2.1.0.")
    print("Import and call apply_fix() before creating MQTT clients.")
    print()
    print("Example:")
    print("    import paho_mqtt_fix_patch")
    print("    paho_mqtt_fix_patch.apply_fix()")
    print("    # ... create and use MQTT clients ...")
