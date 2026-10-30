# /// script
# requires-python = ">=3.10"
# dependencies = ["pyserial>=3.5"]
# ///
"""Record the payload IMU (firmware/imu_logger) over USB.

  bundle mode (a real drop): writes the pipeline's observation-bundle IMU files
      uv run scripts/imu_record.py --out data/real/<session>/obs/<trial> --duration 20
      -> imu.csv (t_mcu,ax,ay,az,gx,gy,gz), led_events.csv (t_mcu,state), imu_raw.log, imu_header.txt
  allan mode (static calibration log, hours): same files, plus a progress line every minute
      uv run scripts/imu_record.py --out data/real/allan/<date> --duration 21600 --allan

t_mcu is the ESP32 timer in seconds, unchanged (the pipeline aligns MCU and camera clocks itself via the
LED edges, so no host-side time is mixed in). Lines that fail to parse are counted and skipped, never
repaired.
"""
import argparse
import sys
import time
from pathlib import Path

import serial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--out", required=True)
    ap.add_argument("--duration", type=float, required=True, help="seconds to record")
    ap.add_argument("--allan", action="store_true", help="long static log: progress output every minute")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    s = serial.Serial(a.port, 921600, timeout=1)
    s.reset_input_buffer()
    s.write(b"h")  # ask the firmware to re-print its header
    n_imu = n_led = n_bad = 0
    t_first = t_last = None
    header = []
    t_end = time.time() + a.duration
    t_report = time.time() + 60
    with open(out / "imu.csv", "w") as fi, open(out / "led_events.csv", "w") as fl, open(out / "imu_raw.log", "w") as fr:
        fi.write("t_mcu,ax,ay,az,gx,gy,gz\n")
        fl.write("t_mcu,state\n")
        while time.time() < t_end:
            raw = s.readline()
            if not raw:
                continue
            line = raw.decode("ascii", "replace").strip()
            fr.write(line + "\n")
            f = line.split(",")
            try:
                if f[0] == "I" and len(f) == 8:
                    vals = [float(x) for x in f[1:]]
                    fi.write(",".join(f[1:]) + "\n")
                    n_imu += 1
                    t_first = vals[0] if t_first is None else t_first
                    t_last = vals[0]
                elif f[0] == "L" and len(f) == 3:
                    float(f[1]); int(f[2])
                    fl.write(f"{f[1]},{f[2]}\n")
                    n_led += 1
                elif line.startswith("#"):
                    header.append(line)
                    if "ERROR" in line or "WARN" in line:
                        print(line, file=sys.stderr)
                else:
                    n_bad += 1
            except ValueError:
                n_bad += 1
            if a.allan and time.time() >= t_report:
                t_report += 60
                rate = (n_imu - 1) / (t_last - t_first) if n_imu > 1 and t_last > t_first else 0
                print(f"[{time.strftime('%H:%M:%S')}] {n_imu} samples, {rate:.1f} Hz, bad lines {n_bad}", flush=True)
    (out / "imu_header.txt").write_text("\n".join(header) + "\n")
    rate = (n_imu - 1) / (t_last - t_first) if n_imu > 1 and t_last > t_first else 0
    print(f"done: {n_imu} IMU samples ({rate:.1f} Hz mean), {n_led} LED toggles, {n_bad} unparsed lines -> {out}")


if __name__ == "__main__":
    main()
