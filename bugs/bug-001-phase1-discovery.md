# Bug #1 Description: IGW Connection Lifecycle Issue

**Source:** [GitHub Issue #1](https://github.com/hlehoux2021/MyHargassner/issues/1)

**Date:** 2025-10-08

---

## **The Problem**

After several days of operation, MyHargassner loses connection with the IGW (Internet Gateway) when processing these specific commands:
- `$dhcp renew`
- `$igw clear`

## **Root Cause**

The IGW sends these commands, receives responses, then **closes the telnet connection** to restart a fresh connection dialog. MyHargassner doesn't handle this gracefully because:

### 1. **Connection Lifecycle Mismatch**

TelnetProxy is started **once** at application startup and runs forever, but IGW follows a connection pattern where it:
- Sends UDP broadcast "HargaWebApp" before each new telnet session
- Establishes telnet connection on port 23
- Exchanges commands/responses
- Closes connection abruptly after certain commands
- Starts over with a new UDP broadcast

### 2. **State Desynchronization**

When IGW closes the connection:
- TelnetProxy detects it as an error and tries `restart_service1()`
- The restart doesn't clear caller state (`_caller` becomes 0 or stale)
- GatewayListener detects the new UDP broadcast but has no way to signal TelnetProxy
- TelnetProxy is stuck trying to recover from the previous connection
- New IGW connection attempts fail due to state confusion

### 3. **Unknown Command Handling**

`$dhcp renew` and `$igw clear` are treated as "passthrough" (forwarded correctly), but this is just a symptom - the real issue is what happens after these commands when IGW disconnects.

## **Execution Flow Leading to Bug**

```
09:51:28 - IGW sends: $dhcp renew (passthrough)
09:51:32 - IGW sends: $igw clear (passthrough)
09:51:33 - Responses forwarded correctly
[IGW closes connection - 17 second gap]
09:52:09 - IGW broadcasts new "HargaWebApp" (wants fresh connection)
[TelnetProxy still trying to recover from old connection]
[State desynchronization - connection fails]
```

## **Key Architectural Issue**

The fundamental problem is that **TelnetProxy lifecycle is disconnected from IGW connection lifecycle**:
- TelnetProxy runs continuously from startup
- IGW uses ephemeral connections (connect → exchange → disconnect → repeat)
- No coordination between GatewayListener (which detects IGW readiness) and TelnetProxy (which handles the connection)

## **Expected Behavior**

1. IGW sends commands including `$dhcp renew` and `$igw clear`
2. MyHargassner forwards commands and responses correctly
3. IGW closes connection
4. IGW broadcasts new "HargaWebApp" for fresh connection
5. MyHargassner accepts new connection with clean state
6. Communication resumes normally

## **Actual Behavior**

1. IGW sends commands including `$dhcp renew` and `$igw clear`
2. MyHargassner forwards commands and responses correctly
3. IGW closes connection
4. TelnetProxy tries to restart internally with stale state
5. IGW broadcasts new "HargaWebApp" for fresh connection
6. **Connection fails due to state desynchronization**
7. **Communication is broken**

---

## **Next Steps**

Move to Phase 2: Root Cause Analysis and Solution Proposal
