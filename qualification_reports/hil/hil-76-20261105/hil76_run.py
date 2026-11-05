import json, sys, time
from pathlib import Path
from dpo4000_utils import DPO4054
out = Path(sys.argv[1]); r = {}
s = DPO4054("TCPIP0::192.168.0.5::INSTR", auto_connect=True, timeout_ms=8000)
sess = s.ensure_connected()
try:
    before = sess.query("SET?")
    r["state_before"] = sess.query("ACQUIRE:STATE?").strip()
    r["stopafter"] = s.get_stop_after(); s.set_stop_after("RUNSTOP"); r["stopafter_during"] = s.get_stop_after()
    r["trig_state_before"] = sess.query("TRIGGER:STATE?").strip()
    r["count_before"] = s.get_acquisition_count()
    sess.write("ACQUIRE:STATE RUN")
    samples = []
    for _ in range(6):
        time.sleep(0.5); samples.append(s.get_acquisition_count())
    r["counts_while_run"] = samples
    r["state_running"] = sess.query("ACQUIRE:STATE?").strip()
    sess.write("ACQUIRE:STATE STOP"); time.sleep(0.5)
    a = s.get_acquisition_count(); time.sleep(0.5); b = s.get_acquisition_count()
    r["count_after_stop"] = [a, b]
    r["state_after"] = sess.query("ACQUIRE:STATE?").strip()
finally:
    s.set_stop_after("SEQUENCE")
    sess.write("ACQUIRE:STATE STOP"); time.sleep(0.5)
    after = sess.query("SET?")
    r["set_identical"] = before == after
    if before != after:
        r["set_diff"] = [(x, y) for x, y in zip(before.split(";"), after.split(";")) if x != y][:20]
    s.disconnect()
(out / "hil76_run_runstop.json").write_text(json.dumps(r, indent=2)); print(json.dumps(r, indent=2))
