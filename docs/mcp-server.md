# DPO-MCP-01: optional read-only MCP foundation

Status: **implementation started — headless stdio tools only; no physical HIL evidence**.

This is the initial step toward DPO4000 MCP support. It deliberately has no
network listener, configuration-changing tool, raw SCPI interface, arbitrary
recipe execution, unattended test activity or GUI session adapter.

## Install / run

Python 3.11 or newer is required for the MCP extra; the regular DPO4000 driver
continues to support Python 3.10.

```bash
python -m pip install -e ".[mcp]"
dpo4000-mcp --help
dpo4000-mcp
```

The last command starts an MCP **stdio** server with instrument I/O disabled.
It publishes only a metadata-only `scope_get_status` tool that succeeds
without a VISA connection; other tools refuse hardware access.

To enable read-only instrument operations, an operator must first ensure the
oscilloscope is free of other sessions and intentionally start:

```bash
dpo4000-mcp --resource 'TCPIP0::192.0.2.42::INSTR' --allow-instrument-io
```

The above address is a **documentation-only example**, not a real bench host.
The server makes no connection until the first instrument tool call. Its
stdio output is reserved exclusively for MCP messages.

MCP client command: `dpo4000-mcp` plus the arguments above. The client
launches the process locally; there is no HTTP endpoint.

## Tools

- `scope_get_status`: metadata only, no VISA traffic
- `scope_get_instrument_identity`: public `query_identity`
- `scope_get_channels`: public readback of CH1–CH4
- `scope_get_measurement_slots`: public MEAS1–MEAS8 readback
- `scope_get_trigger_configuration`: public trigger readback
- `scope_get_acquisition_configuration`: public acquisition readback
- `scope_capture_preconfigured`: strict query-only preconfigured waveform,
  at most 1000 samples, with at most 256 decimated preview points

The waveform tool uses the existing
`read_preconfigured_waveform(ReadOnlyVisaSession(...))` path. It does not
select the source, modify DATA:START/STOP, change the encoding, or initiate
acquisition. Larger records fail closed, not truncated.

All instrument calls pass through a single-thread retained-session gateway.
At most one call may execute: concurrent requests receive BUSY. A cancelled
client request cannot unlock the physical operation before PyVISA returns.
Transport failures invalidate the retained session; the next operation may
reconnect under the existing driver's transport policies.

## Explicit limitations / follow-up gates

**Desk and other VISA clients are NOT coordinated by this first milestone.**
The server-local lock protects only calls within its own process. It does not
prevent a second process from connecting. Do not operate Desk Live View and
this headless server against the same hardware concurrently.

The proposed next milestones are:

1. DPO-MCP-02: shared Desk/headless instrument gateway and cross-process
   ownership coordination. No multiple VISA sessions for one instrument.
2. DPO-MCP-03: complete simulator/fake-VISA contract suite and strict I/O
   audit, including waveform transfer and fault injection.
3. DPO-MCP-04: authenticated HTTP service and access policy, disabled by
   default; only then evaluate LAN exposure.
4. DPO-MCP-05: authorized controlled acquisitions, A15/A16 recipe orchestration,
   A18 evidence and A21 DPOZ/NPZ artifacts.
5. DPO-MCP-06: hardware qualification on both USB and Ethernet with
   retained, independently reviewed evidence and resource limits.

The server is **not hardware qualified**. Never infer a HIL PASS from offline
tests, CI, a running server or a successful fake-scope response.

## Offline verification

```bash
python -m pip install -e ".[dev,mcp]"
pytest -q tests/test_mcp_gateway.py tests/test_mcp_protocol.py
ruff check dpo4000_utils/mcp_server tests/test_mcp_gateway.py tests/test_mcp_protocol.py
```

The official MCP Python SDK v2 uses `MCPServer` in `mcp.server`.
The stdio transport is the initial local host integration; Streamable HTTP
remains a planned follow-on and requires an explicit security review.
