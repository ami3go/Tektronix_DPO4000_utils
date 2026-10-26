#!/usr/bin/env bash
# Diagnose DPO4054 USBTMC enumeration, permissions, driver binding, and Python
# backend availability. Optional probes are explicit because they open the
# physical instrument.

set -u

VID="0699"
PID="0401"
PROBE=0
CLEAR_HALT=0

usage() {
  echo "Usage: $0 [--probe] [--clear-halt]"
  echo "  --probe       send the read-only *IDN? query through /dev/usbtmcN"
  echo "  --clear-halt  clear Linux USBTMC bulk endpoint halts, then probe"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --probe) PROBE=1 ;;
    --clear-halt) CLEAR_HALT=1; PROBE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

echo "=== 1. USB enumeration (${VID}:${PID}) ==="
lsusb -d "${VID}:${PID}" || true
echo

echo "=== 2. Locate the device in sysfs ==="
DEV_PATH=""
for idv in /sys/bus/usb/devices/*/idVendor; do
  [ -f "$idv" ] || continue
  candidate=$(dirname "$idv")
  [ "$(cat "$idv" 2>/dev/null)" = "$VID" ] || continue
  [ "$(cat "$candidate/idProduct" 2>/dev/null)" = "$PID" ] || continue
  DEV_PATH="$candidate"
  break
done

if [ -z "$DEV_PATH" ]; then
  echo "No Tektronix ${VID}:${PID} device found."
  exit 1
fi
echo "Device: $DEV_PATH"
echo "Product: $(cat "$DEV_PATH/product" 2>/dev/null || echo unknown)"
echo "Serial:  $(cat "$DEV_PATH/serial" 2>/dev/null || echo unknown)"

BUSNUM=$(cat "$DEV_PATH/busnum" 2>/dev/null || true)
DEVNUM=$(cat "$DEV_PATH/devnum" 2>/dev/null || true)
RAW_NODE=""
if [ -n "$BUSNUM" ] && [ -n "$DEVNUM" ]; then
  RAW_NODE=$(printf "/dev/bus/usb/%03d/%03d" "$BUSNUM" "$DEVNUM")
  echo "Raw node: $RAW_NODE"
fi

IFACE_PATH=""
for candidate in "$DEV_PATH"/*:*.*; do
  [ -d "$candidate" ] || continue
  [ "$(cat "$candidate/bInterfaceClass" 2>/dev/null)" = "fe" ] || continue
  [ "$(cat "$candidate/bInterfaceSubClass" 2>/dev/null)" = "03" ] || continue
  IFACE_PATH="$candidate"
  break
done

if [ -n "$IFACE_PATH" ]; then
  echo "USBTMC interface: $(basename "$IFACE_PATH")"
  if [ -e "$IFACE_PATH/driver" ]; then
    echo "Driver: $(readlink -f "$IFACE_PATH/driver")"
  else
    echo "Driver: unbound"
  fi
else
  echo "USBTMC interface: not found"
fi
echo

echo "=== 3. Device-node permissions ==="
ls -la /dev/usbtmc* 2>&1 || true
[ -n "$RAW_NODE" ] && ls -la "$RAW_NODE" 2>&1 || true
echo "Current user: $(id)"
echo

echo "=== 4. Python backend availability ==="
python3 - <<'PY'
import importlib.util
print("pyvisa:", "available" if importlib.util.find_spec("pyvisa") else "missing")
print("pyvisa_py:", "available" if importlib.util.find_spec("pyvisa_py") else "missing")
print("pyusb:", "available" if importlib.util.find_spec("usb") else "missing")
PY
python3 - <<'PY' 2>&1 || true
try:
    import pyvisa
except ImportError:
    print("PyVISA resource list unavailable")
else:
    try:
        manager = pyvisa.ResourceManager("@py")
        print("PyVISA-py resources:", manager.list_resources())
        manager.close()
    except Exception as exc:
        print(f"PyVISA-py resource list failed: {type(exc).__name__}: {exc}")
PY
echo

USBTMC_NODE=""
for candidate in /dev/usbtmc*; do
  [ -c "$candidate" ] || continue
  USBTMC_NODE="$candidate"
  break
done

if [ "$CLEAR_HALT" -eq 1 ]; then
  echo "=== 5. Clear USBTMC bulk endpoint halts ==="
  if [ -z "$USBTMC_NODE" ]; then
    echo "No /dev/usbtmcN node found." >&2
    exit 1
  fi
  USBTMC_NODE="$USBTMC_NODE" python3 - <<'PY'
import fcntl
import os

node = os.environ["USBTMC_NODE"]
fd = os.open(node, os.O_RDWR)
try:
    # _IO(USBTMC_IOC_NR=91, 6/7), from linux/usb/tmc.h.
    fcntl.ioctl(fd, 0x5B06)  # USBTMC_IOCTL_CLEAR_OUT_HALT
    fcntl.ioctl(fd, 0x5B07)  # USBTMC_IOCTL_CLEAR_IN_HALT
    print(f"Cleared bulk endpoint halts on {node}")
finally:
    os.close(fd)
PY
  echo
fi

if [ "$PROBE" -eq 1 ]; then
  echo "=== 6. Native USBTMC read-only identity probe ==="
  if [ -z "$USBTMC_NODE" ]; then
    echo "No /dev/usbtmcN node found." >&2
    exit 1
  fi
  USBTMC_NODE="$USBTMC_NODE" python3 - <<'PY'
import os

node = os.environ["USBTMC_NODE"]
fd = os.open(node, os.O_RDWR)
try:
    os.write(fd, b"*IDN?\n")
    response = os.read(fd, 4096).decode("ascii", errors="replace").strip()
    print(response)
    if "TEKTRONIX,DPO4" not in response.upper():
        raise SystemExit("Unexpected instrument identity")
finally:
    os.close(fd)
PY
fi
