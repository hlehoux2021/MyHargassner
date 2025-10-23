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

    This version ONLY logs and then calls the original - no double processing!
    """
    # ============ DEBUGGING START ============
    packet_data = self._in_packet['packet']
    packet_len = len(packet_data)
    header = self._in_packet['command']

    # Log which client instance this is
    import threading
    thread_id = threading.current_thread().ident
    client_id = id(self)

    logging.error("=" * 80)
    logging.error(f"PAHO MQTT DEBUG - _handle_publish() called")
    logging.error(f"Client ID: {client_id} | Thread ID: {thread_id}")
    logging.error("=" * 80)
    logging.error(f"Packet length: {packet_len}")
    logging.error(f"Packet data (hex): {packet_data.hex()}")
    logging.error(f"Packet data (repr): {packet_data!r}")
    logging.error(f"Header: 0x{header:02x}")

    # Decode header flags
    dup = ((header & 0x08) >> 3) != 0
    qos = (header & 0x06) >> 1
    retain = (header & 0x01) != 0

    logging.error(f"QoS: {qos}")
    logging.error(f"Retain: {retain}")
    logging.error(f"Dup: {dup}")

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
        logging.error("=" * 80)
        # Don't call original - it will fail. Return error instead.
        return MQTTErrorCode.MQTT_ERR_PROTOCOL

    # Check for other invalid characters
    if not format_len.bit_length() <= 63:  # Max safe integer
        logging.error(f"ERROR: format_len is too large! ({format_len})")
        logging.error("=" * 80)
        return MQTTErrorCode.MQTT_ERR_PROTOCOL

    # Let's also pre-calculate what the SECOND pack_format will be
    # to see if THAT's the problematic one
    try:
        # Simulate first unpack
        (test_slen, test_packet) = struct.unpack(pack_format, bytes(packet_data))
        second_pack_format = f"!{test_slen}s{len(test_packet) - test_slen}s"
        logging.error(f"PREDICTED second pack_format: '{second_pack_format}'")
        logging.error(f"Second format topic length: {test_slen}")
        logging.error(f"Second format payload length: {len(test_packet) - test_slen}")

        # Check if second format is valid
        if test_slen < 0 or (len(test_packet) - test_slen) < 0:
            logging.error(f"ERROR: Second pack_format will have NEGATIVE length!")
    except Exception as e:
        logging.error(f"Could not pre-calculate second pack_format: {e}")

    logging.error(f"About to call ORIGINAL _handle_publish() - no double processing")
    logging.error("=" * 80)
    # ============ DEBUGGING END ============

    # Now call the original method to do the actual work
    # We only logged above - didn't consume any data
    try:
        return _original_handle_publish(self)
    except struct.error as e:
        logging.error("=" * 80)
        logging.error(f"STRUCT.ERROR CAUGHT from original method: {e}")
        logging.error(f"Failed at pack_format: '{pack_format}'")
        logging.error(f"Packet data: {packet_data!r}")
        logging.error(f"Packet hex: {packet_data.hex()}")
        logging.error(f"Packet type: {type(packet_data)}")

        # Try to figure out WHERE in _handle_publish it failed
        import traceback
        tb_lines = traceback.format_exc().split('\n')
        for line in tb_lines:
            if 'pack_format' in line or 'struct.unpack' in line:
                logging.error(f"Traceback detail: {line}")

        logging.error("=" * 80)
        raise  # Re-raise to see full stack trace


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
