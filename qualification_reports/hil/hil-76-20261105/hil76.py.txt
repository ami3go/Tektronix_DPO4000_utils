import json, sys, time
from pathlib import Path
from dpo4000_utils import DPO4054
from dpo4000_utils.acquisition_state import normalize_stop_after

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
RES = {"tcp": "TCPIP0::192.168.0.5::INSTR", "usb": "USB0::1689::1025::C011280::0::INSTR"}
report = {}
for name, res in RES.items():
    r = report[name] = {"resource": res}
    s = DPO4054(res, auto_connect=True, timeout_ms=8000)
    try:
        sess = s.ensure_connected()
        r["idn"] = sess.query("*IDN?").strip()
        before = sess.query("SET?")
        r["acq_state_raw"] = sess.query("ACQUIRE:STATE?").strip()
        r["numacq_raw"] = sess.query("ACQUIRE:NUMACQ?").strip()
        r["stopafter_raw"] = sess.query("ACQUIRE:STOPAFTER?").strip()
        r["counts"] = []
        for _ in range(5):
            r["counts"].append(s.get_acquisition_count()); time.sleep(0.5)
        orig = s.get_stop_after(); r["stop_after_orig"] = orig
        other = "RUNSTOP" if orig == "SEQUENCE" else "SEQUENCE"
        try:
            s.set_stop_after(other); r["stop_after_set_readback"] = s.get_stop_after()
            r["stop_after_set_raw"] = sess.query("ACQUIRE:STOPAFTER?").strip()
        finally:
            s.set_stop_after(orig)
        time.sleep(0.5)
        r["stop_after_restored"] = s.get_stop_after()
        after = sess.query("SET?")
        r["set_identical"] = before == after
        r["set_len"] = [len(before), len(after)]
        if before != after:
            b = before.split(";"); a = after.split(";")
            r["set_diff"] = [(x, y) for x, y in zip(b, a) if x != y][:20]
        # invalid-input rejection
        try: s.set_stop_after("BOGUS"); r["bogus_rejected"] = False
        except ValueError: r["bogus_rejected"] = True
        r["ok"] = True
    except Exception as e:
        r["ok"] = False; r["error"] = repr(e)
    finally:
        try: s.disconnect()
        except Exception: pass
(out / "hil76.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
