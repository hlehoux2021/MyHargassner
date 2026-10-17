# Troubleshooting

Commands to run on the Raspberry Pi to diagnose MyHargassner. Run them as root.

## IGW stuck after a session end (`$igw clear`)

**Symptom:** after a session ends (typically `TelnetProxy requesting restart: igw_clear_command` in the log), the IGW repeats `get services` **every 20 s** and never opens a telnet session. The log shows no `Received buffer of 318 bytes from 10.0.0.72` (the boiler reply) after the `get services`.

A healthy IGW sends `get services`, gets the boiler reply, sends a second `get services` a few seconds later, then opens the telnet session.

See "UDP Socket Design" in [TECHNICAL_ARCHITECTURE.md](TECHNICAL_ARCHITECTURE.md) for the background.

### 1. Did the boiler reply after the last restart?

```bash
grep -an "requesting restart\|session starting\|Received buffer of 318 bytes from 10.0.0.72" /var/log/myhargassner.log | tail -20
```

After each `requesting restart` line, a `System session starting (session #N)` line must follow, then a `Received buffer of 318 bytes from 10.0.0.72` line within about a minute (the boiler reply, logged at `verbose` level). If the reply lines stop after a restart, the session is stuck.

The log is kept, so this check also works days after the event. `-a` is needed because the log contains non-text bytes (e.g. the `\0` ending `get services`), which make `grep` treat it as a binary file.

### 2. Which sockets hold the UDP ports?

```bash
sudo ss -uapn '( sport = :50000 or sport = :35601 )'
```

Expected (once the IGW has sent its first packet):

```
State   Recv-Q  Local Address:Port      Peer Address:Port
UNCONN  0       0.0.0.0%eth0:35601      0.0.0.0:*                 GatewayListener (IGW broadcasts)
UNCONN  ...     0.0.0.0%eth0:35601      0.0.0.0:*                 BoilerListener resender (see note)
UNCONN  0       0.0.0.0%eth1:50000      0.0.0.0:*                 BoilerListener (boiler replies)
ESTAB   0       10.0.0.x%eth1:50000     255.255.255.255:35601     GatewayListener resender
```

- The gateway resender must be `ESTAB` with peer `255.255.255.255:35601`: being connected, it can never receive the boiler replies.
- `Recv-Q` must stay at 0 on both `:50000` sockets.
- The BoilerListener resender on `:35601` is bound only once the boiler has replied. It gets a copy of every IGW broadcast and never reads them, so a small `Recv-Q` there is harmless.

**Signature of the bug** (seen on 2026-10-17 with the code before the fix): an unconnected `0.0.0.0%eth1:50000` socket with a large `Recv-Q` (around 212000, the full receive buffer) and a `0.0.0.0:50000` socket without device. The boiler replies pile up in the gateway resender, which never reads them, and the BoilerListener gets nothing.

### 3. Are sockets or threads left over from previous sessions?

```bash
PID=$(systemctl show -p MainPID --value myhargassner)
sudo ss -tlpn '( sport = :23 or sport = :4000 )'   # at most one listener on each port
sudo ss -tpn '( dport = :1883 )' | wc -l           # MQTT connections (+1 header line)
ps -T -p $PID                                      # threads of the process
```

Run them after several sessions: the counts must stay stable from one session to the next. A growing count means a session did not release its resources.

### 4. Force a session end

To test a restart without waiting for an `$igw clear`, unplug the IGW power for about 10 s. When it boots it broadcasts `HargaWebApp` again, which ends the current session. Note that this did not reproduce the stuck IGW with the code before the fix: only an `$igw clear` did.
