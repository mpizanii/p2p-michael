# P2P Discovery, Election, and TCP Handshake Design

> **Scope:** Tasks 01, 02, and 03 from the sprint brief. This design adds UDP discovery, deterministic master election, and the initial TCP handshake before the existing heartbeat flow starts.

**Goal:** Let workers start without a preconfigured master IP/port, discover available masters over UDP, elect the same master deterministically, and transition safely to the existing TCP heartbeat loop.

**Architecture:** Workers broadcast a JSON discovery packet over UDP, wait a fixed collection window, and choose the winner by lexicographic `MASTER_NAME`. Masters listen on the UDP discovery port, reply unicast with their name, IP, and TCP port, and accept a TCP `ELECTION_ACK` before the worker enters the heartbeat loop already implemented in `worker.py`.

**Protocol shape:** Keep JSON newline framing for all packets. Discovery uses `TYPE=DISCOVERY` and `TYPE=DISCOVERY_REPLY`. Election confirmation uses `TYPE=ELECTION_ACK` over TCP. Heartbeat remains the current `SERVER_UUID` / `TASK=HEARTBEAT` flow so the later sprint code does not need a rewrite.

**Error handling:** Workers ignore malformed discovery replies, discard messages missing required fields, and restart discovery if no master replies inside the collection window or if the TCP handshake fails. Masters reject malformed election acknowledgements and only start the worker session after a valid confirmation.

**Testing:** Verify the single-master case, the multi-master lexicographic tie-breaker, the no-response timeout path, the malformed reply path, and the TCP handshake path before the heartbeat loop begins.

**Files expected to change:**
- `config.py` for discovery and election constants.
- `master.py` for UDP discovery response and election ACK handling.
- `worker.py` for discovery, election, handshake, and startup flow.
- `README.md` for the updated run instructions and protocol summary.
