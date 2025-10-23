# Paho MQTT "bad char in struct format" Debug Investigation

## Problem Summary

The application crashes with this error:
```
struct.error: bad char in struct format
```

This occurs in paho-mqtt's `_handle_publish()` method at line 4099.

## Stack Trace

```python
File "/usr/local/lib/python3.11/dist-packages/paho/mqtt/client.py", line 4099, in _handle_publish
    (slen, packet) = struct.unpack(pack_format, self._in_packet['packet'])
struct.error: bad char in struct format
```

## Code Analysis

### The Failing Code (paho/mqtt/client.py:4098-4099)

```python
pack_format = f"!H{len(self._in_packet['packet']) - 2}s"
(slen, packet) = struct.unpack(pack_format, self._in_packet['packet'])
```

### What Creates the Format String

The `pack_format` is an f-string that looks like: `"!H{N}s"` where:
- `!` = Network byte order (big-endian)
- `H` = Unsigned short (2 bytes) - reads the topic length
- `{N}s` = String of N bytes - reads the remaining packet
- `N` = `len(self._in_packet['packet']) - 2`

### When the Error Occurs

The error **"bad char in struct format"** happens when:

1. **Negative length**: If `len(packet) - 2 < 0`, the format becomes `"!H-1s"` which is invalid
   - This happens when the packet is less than 2 bytes long

2. **Invalid characters in the number**: If somehow the calculation produces a non-numeric result
   - Less likely, but possible with data corruption

## Debug Patch

I've created [paho_mqtt_debug_patch.py](paho_mqtt_debug_patch.py) which:

1. **Monkey patches** paho's `_handle_publish()` method
2. **Logs everything** before the failing `struct.unpack()`:
   - Packet length
   - Packet data (hex and repr)
   - Calculated pack_format
   - Header, QoS, retain flags
3. **Detects negative lengths** and returns an error code instead of crashing
4. **Catches struct.error** and logs the exact failure details

## How to Use the Debug Patch

### In test_mqtt_actuator.py (already applied):

```python
# Apply BEFORE importing anything that uses paho-mqtt
import paho_mqtt_debug_patch
paho_mqtt_debug_patch.apply_patch()

# Now import MQTT-using modules
from ha_mqtt_discoverable import DeviceInfo
from myhargassner.mqtt_actuator import MqttActuator
```

### In production code:

Add to the top of your main module:

```python
import paho_mqtt_debug_patch
paho_mqtt_debug_patch.apply_patch()
```

## Expected Debug Output

When the error occurs, you'll see:

```
===============================================================================
PAHO MQTT DEBUG - _handle_publish() called
===============================================================================
Packet length: 1
Packet data (hex): 41
Packet data (repr): b'A'
Header: 0x30
QoS: 0
Retain: False
Dup: False
Calculated pack_format: '!H-1s'
Format length part: -1
ERROR: format_len is NEGATIVE! (-1)
This happens when packet length (1) < 2
This is the root cause of 'bad char in struct format'!
===============================================================================
```

## Hypothesis: Root Cause

Based on the code analysis, the most likely causes are:

### 1. **Packet Fragmentation** (Most Likely)
   - The MQTT packet arrives in fragments
   - paho reads an incomplete packet (< 2 bytes)
   - Tries to unpack before the full packet is received

### 2. **MQTT Protocol Violation**
   - The broker sends a malformed PUBLISH packet
   - The packet is shorter than the minimum valid length
   - Could be caused by:
     - Broker bug
     - Network corruption
     - Connection issues during transmission

### 3. **Topic or Payload Encoding Issues**
   - Special characters in topic names (accents: é, è, etc.)
   - UTF-8 encoding issues
   - The packet parser gets confused and reads the wrong length

## Testing Strategy

1. **Run test_mqtt_actuator.py with debug patch**
   ```bash
   cd myhargassner/tests
   python3 test_mqtt_actuator.py
   ```

2. **Trigger the error** by changing values in Home Assistant

3. **Check the debug logs** for:
   - Packet length when it fails
   - Packet hex data
   - Which entity triggered it (Select or Number?)
   - Pattern: Does it always fail on the same parameter?

4. **Analyze patterns**:
   - Does it fail on first callback or randomly?
   - Is it always the same topic?
   - Is the packet always a specific length?

## Next Steps

Once we have the debug output:

1. **If packet length < 2**: paho-mqtt packet reading bug
2. **If pack_format has weird characters**: Data corruption issue
3. **If it's always the same topic**: Topic name encoding issue
4. **If random**: Network/broker instability

## Files

- [paho_mqtt_debug_patch.py](paho_mqtt_debug_patch.py) - The monkey patch
- [test_mqtt_actuator.py](test_mqtt_actuator.py) - Test program (now with patch applied)
- [PAHO_MQTT_DEBUG_README.md](PAHO_MQTT_DEBUG_README.md) - This file

## Related Issues

- GitHub Issue #2: https://github.com/hlehoux2021/MyHargassner/issues/2
- Branch: `paho-debugging`
