import json, sys, time
from pathlib import Path
from dpo4000_utils import DPO4054
out = Path(sys.argv[1]); r = {}
s = DPO4054(sys.argv[2], auto_connect=True, timeout_ms=8000)
sess = s.ensure_connected()
q = lambda c: sess.query(c).strip()
try:
    before = sess.query("SET?")
    for k in ("TRIGGER:A:MODE?", "TRIGGER:A:TYPE?", "TRIGGER:A:EDGE:SOURCE?", "TRIGGER:A:LEVEL?", "TRIGGER:STATE?", "ACQUIRE:MODE?", "HORIZONTAL:SCALE?"):
        r[k] = q(k)
    orig_mode = r["TRIGGER:A:MODE?"]
    r["stopafter"] = s.get_stop_after()
    s.set_stop_after("RUNSTOP")
    sess.write("ACQUIRE:STATE RUN"); time.sleep(2.0); r["norm_mode_count_after_2s"]=s.get_acquisition_count(); r["norm_trig_state"]=q("TRIGGER:STATE?"); sess.write("ACQUIRE:STATE STOP"); time.sleep(0.5)
    sess.write("TRIGGER:A:MODE AUTO")
    sess.write("ACQUIRE:STATE RUN")
    samples, states = [], []
    for _ in range(6):
        time.sleep(0.5); samples.append(s.get_acquisition_count()); states.append(q("TRIGGER:STATE?"))
    r["counts_while_run"] = samples; r["trig_states"] = states
    sess.write("ACQUIRE:STATE STOP"); time.sleep(0.5)
    r["count_after_stop"] = [s.get_acquisition_count(), (time.sleep(0.5), s.get_acquisition_count())[1]]
finally:
    sess.write("ACQUIRE:STATE STOP"); time.sleep(0.3)
    sess.write(f"TRIGGER:A:MODE {orig_mode}")
    s.set_stop_after("SEQUENCE"); time.sleep(0.5)
    after = sess.query("SET?")
    r["set_identical"] = before == after
    if before != after:
        r["set_diff"] = [(x, y) for x, y in zip(before.split(";"), after.split(";")) if x != y][:20]
    s.disconnect()
(out / ("hil76_trig_"+sys.argv[3]+".json")).write_text(json.dumps(r, indent=2)); print(json.dumps(r, indent=2))
