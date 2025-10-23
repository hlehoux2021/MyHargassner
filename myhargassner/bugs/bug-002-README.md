# Test MQTT Actuator & Dual-Loop Bug Fix

## Summary

This directory contains a test program that helped identify and fix a critical **dual-loop concurrency bug** in `mqtt_actuator.py`.

## The Bug

### Problem
`mqtt_actuator.service()` was calling `client.loop()` while **ha-mqtt-discoverable** had already started a background thread running its own MQTT loop. This created a race condition where:

- **MainThread**: Calling `client.loop()`
- **paho-mqtt-client- thread**: Running `loop_forever()` in background

Both threads processed the same MQTT packets, causing:
- Duplicate callback invocations
- Race conditions in packet processing
- `struct.error: bad char in struct format` crashes

### Root Cause

When `ha-mqtt-discoverable` creates Select/Number entities, it automatically starts a background thread to handle MQTT processing. The application code should **NOT** call `client.loop()` - it should just wait and let the background thread do its work.

### The Fix

**File**: `myhargassner/mqtt_actuator.py` (lines 576-588)

**Before (Broken)**:
```python
while not self._shutdown_requested:
    rc = self._main_client.loop(timeout=self._appconfig.loop_timeout())
    # ❌ Creates dual-loop with ha-mqtt-discoverable's background thread
```

**After (Fixed)**:
```python
# IMPORTANT: Do NOT call client.loop() here!
# ha-mqtt-discoverable already started a background thread (paho-mqtt-client-)
# when creating Select/Number entities. Calling loop() here would create
# a DUAL-LOOP situation causing race conditions.
while not self._shutdown_requested:
    time.sleep(1)  # ✅ Just wait, background thread handles everything
```

## Test Program

### test_mqtt_actuator.py

Test program that:
- ✅ Reuses the **REAL** `MqttActuator` class (no code duplication)
- ✅ Mocks only dependencies (TelnetClient, PubSub)
- ✅ Creates 6 real boiler parameters (4 selects + 2 numbers)
- ✅ Tests actual callbacks with Home Assistant integration
- ✅ Helped reproduce and identify the dual-loop bug

**How it works**:
1. Creates mock boiler configuration data
2. Instantiates real MqttActuator with mocked dependencies
3. Creates MQTT entities in Home Assistant
4. Listens for commands and processes them through real callbacks

**Usage**:
```bash
cd myhargassner/tests
python3 test_mqtt_actuator.py
```

Then change values in Home Assistant to test the callbacks.

## Debug Tools

### paho_mqtt_debug_patch.py

Monkey-patches paho-mqtt's `_handle_publish()` to add extensive logging:
- Packet data (hex and repr)
- Pack format strings
- Thread IDs and call stacks
- Pre-validation of format strings

**Usage**:
```python
import paho_mqtt_debug_patch
paho_mqtt_debug_patch.apply_patch()
```

This helped us discover:
1. Two different threads were calling `_handle_publish()`
2. Same Client ID, different Thread IDs = race condition
3. Call stacks showed `loop()` + `loop_forever()` running simultaneously

## Test Results

### Before Fix
```
ERROR: Client ID: 1980636816 | Thread: MainThread (ID: 1968239616)
ERROR: Client ID: 1980636816 | Thread: paho-mqtt-client- (ID: 1996288832)
ERROR: struct.error: bad char in struct format
CRITICAL: MQTT Actuator encountered a critical error and terminated.
```

### After Fix
```
INFO: MQTT background thread already running. Waiting for shutdown signal...
INFO: Starting MQTT service - waiting for messages...
```
✅ No crashes
✅ Single thread processing
✅ All entities working perfectly

## Investigation Timeline

1. **Initial symptom**: `struct.error: bad char in struct format`
2. **First hypothesis**: Bytearray compatibility issue on Raspberry Pi
3. **Debug patch revealed**: Duplicate `_handle_publish()` calls
4. **Thread analysis showed**: Same client, different threads
5. **Call stack proved**: Dual-loop (MainThread + background thread)
6. **Root cause**: `mqtt_actuator.service()` calling `loop()` unnecessarily
7. **Solution**: Remove `loop()` call, let ha-mqtt-discoverable's thread handle it

## Key Learnings

1. **ha-mqtt-discoverable auto-starts background thread** - Don't call `loop()` yourself!
2. **Race conditions can corrupt data** - The bytearray bug was actually corrupted packet data
3. **Test programs are invaluable** - Being able to reproduce the bug was key
4. **Thread IDs reveal concurrency issues** - Logging thread info helped identify the problem

## Files in This Directory

- **test_mqtt_actuator.py** - Test program (keep for future debugging)
- **paho_mqtt_debug_patch.py** - Debug tool (keep for future MQTT issues)
- **README.md** - This file

## Related

- **GitHub Issue**: #2
- **Branch**: paho-debugging
- **Fixed in**: mqtt_actuator.py lines 576-588
