#!/usr/bin/env python3
"""
Monkey patch for paho-mqtt to debug the 'bad char in struct format' error.

This patches the _handle_publish() method to add extensive logging
before the struct.unpack() call that's failing.
"""

import logging
import struct
from paho.mqtt.client import Client, MQTTMessage, MQTTErrorCode, MQTTv5

# Store the original method
_original_handle_publish = Client._handle_publish


def _debug_handle_publish(self) -> MQTTErrorCode:
    """
    Patched version of _handle_publish() with extensive debugging.

    This logs all the values that go into creating the pack_format string
    to help identify why struct.unpack() is failing.
    """
    header = self._in_packet['command']
    message = MQTTMessage()
    message.dup = ((header & 0x08) >> 3) != 0
    message.qos = (header & 0x06) >> 1
    message.retain = (header & 0x01) != 0

    # ============ DEBUGGING START ============
    packet_data = self._in_packet['packet']
    packet_len = len(packet_data)

    logging.error("=" * 80)
    logging.error("PAHO MQTT DEBUG - _handle_publish() called")
    logging.error("=" * 80)
    logging.error(f"Packet length: {packet_len}")
    logging.error(f"Packet data (hex): {packet_data.hex()}")
    logging.error(f"Packet data (repr): {packet_data!r}")
    logging.error(f"Header: 0x{header:02x}")
    logging.error(f"QoS: {message.qos}")
    logging.error(f"Retain: {message.retain}")
    logging.error(f"Dup: {message.dup}")

    # Calculate what pack_format will be
    format_len = packet_len - 2
    pack_format = f"!H{format_len}s"

    logging.error(f"Calculated pack_format: '{pack_format}'")
    logging.error(f"Format length part: {format_len}")

    # Check if format_len is negative (this would cause the error!)
    if format_len < 0:
        logging.error(f"ERROR: format_len is NEGATIVE! ({format_len})")
        logging.error(f"This happens when packet length ({packet_len}) < 2")
        logging.error("This is the root cause of 'bad char in struct format'!")
        return MQTTErrorCode.MQTT_ERR_PROTOCOL

    # Check for other invalid characters
    if not format_len.bit_length() <= 63:  # Max safe integer
        logging.error(f"ERROR: format_len is too large! ({format_len})")
        return MQTTErrorCode.MQTT_ERR_PROTOCOL

    logging.error(f"Attempting struct.unpack with format: '{pack_format}'")
    # ============ DEBUGGING END ============

    try:
        (slen, packet) = struct.unpack(pack_format, packet_data)

        logging.error(f"SUCCESS: First unpack succeeded")
        logging.error(f"Topic length (slen): {slen}")
        logging.error(f"Remaining packet length: {len(packet)}")

        # Second unpack
        pack_format = f"!{slen}s{len(packet) - slen}s"
        logging.error(f"Second pack_format: '{pack_format}'")

        (topic, packet) = struct.unpack(pack_format, packet)

        logging.error(f"SUCCESS: Second unpack succeeded")
        logging.error(f"Topic (bytes): {topic!r}")
        logging.error(f"Payload length: {len(packet)}")

    except struct.error as e:
        logging.error(f"STRUCT.ERROR CAUGHT: {e}")
        logging.error(f"Failed pack_format: '{pack_format}'")
        logging.error(f"Packet data at failure: {packet_data!r}")
        logging.error("=" * 80)
        raise  # Re-raise to see full stack trace

    if self._protocol != MQTTv5 and len(topic) == 0:
        return MQTTErrorCode.MQTT_ERR_PROTOCOL

    # Handle topics with invalid UTF-8
    try:
        print_topic = topic.decode('utf-8')
        logging.error(f"Topic (decoded): {print_topic}")
    except UnicodeDecodeError:
        print_topic = f"TOPIC WITH INVALID UTF-8: {topic!r}"
        logging.error(f"Topic decode error: {print_topic}")

    message.topic = topic

    if message.qos > 0:
        pack_format = f"!H{len(packet) - 2}s"
        (message.mid, packet) = struct.unpack(pack_format, packet)

    # Continue with the rest of the original method
    # (properties handling, payload, callbacks, etc.)
    # For now, we'll call the original to complete the process
    logging.error("Calling original _handle_publish to complete processing")
    logging.error("=" * 80)

    # Restore state and call original
    self._in_packet['packet'] = self._in_packet['packet']  # Already consumed
    return _original_handle_publish(self)


def apply_patch():
    """Apply the debugging patch to paho.mqtt.Client"""
    logging.info("=" * 80)
    logging.info("Applying paho-mqtt debugging patch to _handle_publish()")
    logging.info("=" * 80)
    Client._handle_publish = _debug_handle_publish
    logging.info("Patch applied successfully!")


def remove_patch():
    """Remove the debugging patch"""
    logging.info("Removing paho-mqtt debugging patch")
    Client._handle_publish = _original_handle_publish
    logging.info("Original method restored")


if __name__ == "__main__":
    print("This is a monkey patch module for debugging paho-mqtt.")
    print("Import and call apply_patch() before creating MQTT clients.")
    print()
    print("Example:")
    print("    import paho_mqtt_debug_patch")
    print("    paho_mqtt_debug_patch.apply_patch()")
    print("    # ... create and use MQTT clients ...")
