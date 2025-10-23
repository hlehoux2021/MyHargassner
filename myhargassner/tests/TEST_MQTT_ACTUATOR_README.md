# Test MQTT Actuator

This test program demonstrates how to test the **REAL** `MqttActuator` implementation without duplicating code.

## What It Does

This program:
1. **Reuses the actual MqttActuator class** from [myhargassner/mqtt_actuator.py](myhargassner/mqtt_actuator.py)
2. **Mocks only the dependencies** (TelnetClient and PubSub communicator)
3. **Creates real MQTT devices** that appear in Home Assistant
4. **Tests the real callbacks** (`callback_select` and `callback_number`)
5. **Runs the real service loop** to handle MQTT commands

## Key Benefits

✅ **No code duplication** - Tests the actual implementation, not a copy
✅ **Guaranteed accuracy** - Any changes to MqttActuator are automatically tested
✅ **Real MQTT integration** - Actually connects to MQTT broker and creates HA entities
✅ **Mock boiler** - Simulates boiler responses without needing real hardware

## Test Entities Created

The program creates **6 real boiler parameters** from production logs:

### Select Entities (4)
1. **Mode** (PR001)
   - Options: Manu, Arr, Ballon, Auto, Arr combustion
   - Initial: Manu

2. **Zone 1 Mode** (PR011)
   - Options: Arr, Auto, Réduire, Confort, 1x Confort, Refroid.
   - Initial: Arr

3. **Zone 2 Mode** (PR012)
   - Options: Arr, Auto, Réduire, Confort, 1x Confort, Refroid.
   - Initial: Arr

4. **Tampon Démarrer chrgt** (PR040)
   - Options: Non, Oui
   - Initial: Non

### Number Entities (2)
5. **Zone 1 Temp. ambiante jour** (ID: 4)
   - Range: 14.0 - 26.0 °C
   - Step: 0.5
   - Initial: 20.0
   - Default: 20.0

6. **Zone 1 Température ambiante de réduit** (ID: 5)
   - Range: 8.0 - 24.0 °C
   - Step: 0.5
   - Initial: 18.0
   - Default: 16.0

## How to Run

```bash
python3 test_mqtt_actuator.py
```

The program will:
1. Load MQTT configuration from `myhargassner.ini`
2. Create a "Test Hargassner Boiler" device
3. Register 6 real boiler parameters with Home Assistant (4 selects + 2 numbers)
4. Start listening for MQTT commands
5. Log all callback invocations

Press `Ctrl+C` to stop.

### Expected Output

```
2025-10-23 16:29:37,222 - root - INFO - Total parameters found: 6
2025-10-23 16:29:37,222 - root - INFO - MockTelnetClient connected
2025-10-23 16:29:37,248 - ha_mqtt_discoverable.sensors - INFO - Changing selection of Mode to Manu
2025-10-23 16:29:37,250 - ha_mqtt_discoverable.sensors - INFO - Changing selection of Zone 1 Mode to Arr
2025-10-23 16:29:37,251 - ha_mqtt_discoverable.sensors - INFO - Changing selection of Zone 2 Mode to Arr
2025-10-23 16:29:37,253 - ha_mqtt_discoverable.sensors - INFO - Changing selection of Tampon Démarrer chrgt to Non
2025-10-23 16:29:37,254 - ha_mqtt_discoverable.sensors - INFO - Setting Zone 1 Temp. ambiante jour to 20.0
2025-10-23 16:29:37,255 - ha_mqtt_discoverable.sensors - INFO - Setting Zone 1 Température ambiante de réduit to 18.0
2025-10-23 16:29:37,255 - root - INFO - Starting MQTT loop - waiting for messages...
```

## Architecture

```
TestMqttActuator (wrapper)
    │
    ├─> MqttActuator (REAL implementation)
    │       ├─> create_select()     [REAL method]
    │       ├─> create_number()     [REAL method]
    │       ├─> callback_select()   [REAL callback]
    │       ├─> callback_number()   [REAL callback]
    │       └─> service()           [REAL service loop]
    │
    ├─> MockPubSub (mocked dependency)
    │       └─> MockChanelQueue
    │              └─> Provides test boiler config
    │
    └─> MockTelnetClient (mocked dependency)
            └─> Simulates boiler command responses
```

## Mock Implementation Details

### MockTelnetClient
Simulates the Hargassner boiler telnet interface:
- Parses `$par set "PARAM_ID;TYPE;VALUE"` commands
- Returns properly formatted responses:
  - For selects: `zPa N: PR001 (Test Mode) = Auto\r\n$ack\r\n`
  - For numbers: `zPa N: 1 (Test Param) = 22.5\r\n$ack\r\n`

### MockPubSub / MockChanelQueue
Simulates the PubSub messaging system:
- Provides **real boiler configuration from production logs** on first `listen()` call
- Format matches actual boiler parameter strings:
  ```
  $PR001;6;0;4;3;0;0;0;Mode;Manu;Arr;Ballon;Auto;Arr combustion;0;
  $PR011;6;0;5;1;0;0;0;Zone 1 Mode;Arr;Auto;Réduire;Confort;1x Confort;Refroid.;0;
  $4;3;20.000;14.000;26.000;0.500;°C;20.000;0;0;0;Zone 1 Temp. ambiante jour;
  ```

## Testing from Home Assistant

Once running, the test entities will appear in Home Assistant under the **"Test Hargassner Boiler"** device.

You can:
1. Change select values (e.g., set Mode to "Auto", Zone 1 Mode to "Confort")
2. Adjust number values (e.g., set Zone 1 Temp. ambiante jour to 22.5°C)
3. View callback logs in the console

### Example Callback Log

```
2025-10-23 16:29:37,248 - ha_mqtt_discoverable.sensors - INFO - Changing selection of Mode to Manu
2025-10-23 16:29:37,254 - ha_mqtt_discoverable.sensors - INFO - Setting Zone 1 Temp. ambiante jour to 20.0
```

When you change a value in HA, you'll see:
```
2025-10-23 16:35:42,123 - root - INFO - MockTelnetClient received command: $par set "PR001;6;3"
2025-10-23 16:35:42,124 - root - INFO - MockTelnetClient prepared response: zPa N: PR001 (Mode) = Auto
2025-10-23 16:35:42,450 - root - INFO - MockTelnetClient received command: $par set "4;3;22.5"
2025-10-23 16:35:42,451 - root - INFO - MockTelnetClient prepared response: zPa N: 4 (Zone 1 Temp) = 22.5
```

## Configuration

The program uses your existing MQTT configuration from `myhargassner.ini`:
- MQTT host
- MQTT port
- MQTT username/password

Make sure your MQTT broker is running before starting the test.

## Code Structure

**Main file:** [test_mqtt_actuator.py](test_mqtt_actuator.py)

Key classes:
- `MockTelnetClient` (lines 20-100): Simulates boiler telnet interface
- `MockChanelQueue` (lines 102-132): Provides mock configuration messages
- `MockPubSub` (lines 134-162): Mocks the PubSub communicator
- `TestMqttActuator` (lines 164-216): Wrapper that uses REAL MqttActuator

## What Makes This Different

**Before (wrong approach):**
```python
# Duplicated all methods from MqttActuator
class TestMqttActuator:
    def create_select(self, ...):  # Copied code
    def create_number(self, ...):  # Copied code
    def callback_select(self, ...):  # Copied code
    def callback_number(self, ...):  # Copied code
```
❌ Problem: No guarantee the copy matches the real implementation

**After (correct approach):**
```python
# Reuses the REAL MqttActuator
class TestMqttActuator:
    def __init__(self, ...):
        self._actuator = MqttActuator(...)  # Use REAL class
        self._actuator._client = MockTelnetClient(...)  # Mock only dependencies

    def service(self):
        self._actuator.service()  # Call REAL method
```
✅ Solution: Tests actual implementation with mocked dependencies

## Troubleshooting

**No entities appear in Home Assistant:**
- Check MQTT broker is running
- Verify MQTT configuration in `myhargassner.ini`
- Check MQTT broker logs for connection

**ModuleNotFoundError:**
```bash
# Make sure you're in the project root
cd /Users/hlehoux/dev/MyHargassner
python3 test_mqtt_actuator.py
```

**TypeError about 'dict' object is not an iterator:**
- This was fixed by making `MockChanelQueue.listen()` a generator (uses `yield`)

## Next Steps

To test with real callbacks:
1. Make changes in Home Assistant (e.g., set Test Mode to "Manual")
2. Watch the console for callback logs
3. Verify the MockTelnetClient receives the correct command format
4. Check that the MQTT state updates correctly

## License

Same as the main MyHargassner project.
