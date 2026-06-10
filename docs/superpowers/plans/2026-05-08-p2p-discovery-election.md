# P2P Discovery, Election, and TCP Handshake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement UDP discovery, deterministic worker election, and the TCP election handshake without breaking the existing heartbeat and task-processing path.

**Architecture:** Keep the changes local to the existing Python entry points. `master.py` gains UDP discovery listening and election-ack validation, while `worker.py` gains a startup state machine that discovers masters, selects one, connects over TCP, and then hands control back to the existing heartbeat loop.

**Tech Stack:** Python 3, `socket`, `threading`, `json`, existing newline-delimited payload format.

---

### Task 1: Add discovery and election config

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Add shared discovery constants**

Set explicit constants for the UDP discovery port, discovery timeout window, retry/backoff timing, master name, and a broadcast address. Keep the existing TCP heartbeat port untouched.

- [ ] **Step 2: Preserve current behavior when discovery is skipped**

Make the current worker startup path still work with a manually provided host/port so the existing heartbeat flow can be exercised while the new flow is being introduced.

### Task 2: Implement master-side discovery response

**Files:**
- Modify: `master.py`

- [ ] **Step 1: Add a UDP discovery listener**

Teach the master to listen on the discovery port and reply to `TYPE=DISCOVERY` with a single `TYPE=DISCOVERY_REPLY` message that includes its `MASTER_NAME`, `MASTER_IP`, `MASTER_PORT`, and availability status.

- [ ] **Step 2: Add election ACK validation**

When the worker connects over TCP after election, validate `TYPE=ELECTION_ACK`, confirm the selected master name, and reply with the accepted ACK payload before the existing heartbeat flow continues.

- [ ] **Step 3: Keep the current heartbeat/task handlers unchanged**

Do not disturb the current JSON framing, task queueing, or heartbeat responses outside the new startup handshake path.

### Task 3: Implement worker discovery, election, and handshake

**Files:**
- Modify: `worker.py`

- [ ] **Step 1: Add discovery collection and winner selection**

Broadcast `TYPE=DISCOVERY` when no master is configured, collect replies for the fixed timeout, and choose the winner by lexicographic `MASTER_NAME` so every worker reaches the same result independently.

- [ ] **Step 2: Add TCP connection and election confirmation**

After the winner is chosen, open TCP to the selected master, send `TYPE=ELECTION_ACK`, wait for the accepted ACK, and only then enter the current heartbeat loop.

- [ ] **Step 3: Add timeout and fallback handling**

If no masters reply or the TCP handshake fails, log the stage clearly, back off, and restart discovery instead of crashing.

### Task 4: Update documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the new startup flow**

Explain how workers discover masters, how election is resolved, which ports are used, and how to run a worker with or without a preset master address.

### Task 5: Validate the feature

**Files:**
- None

- [ ] **Step 1: Run a syntax check**

Run: `python -m py_compile config.py master.py worker.py`

Expected: no output and exit code `0`.

- [ ] **Step 2: Run a manual single-master startup**

Run master in one terminal and worker in another.

Expected: worker discovers the master, elects it, confirms the TCP handshake, and then starts the heartbeat loop.

- [ ] **Step 3: Run a malformed-payload smoke check**

Expected: malformed discovery or election payloads are ignored or rejected without taking down the process.
