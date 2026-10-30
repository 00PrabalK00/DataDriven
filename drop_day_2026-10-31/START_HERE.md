# Drop day kit (Oct 31): real drops of 18 CFD-ranked canopies

Everything needed for the real drops. Designs were chosen by the CFD surrogate and confirmed by the full
simulator (best < middle < worst, no overlap). Background: `4_reference/README.md`.

## Folder
| Folder / file | What |
|---|---|
| `1_print/templates_letter.pdf` (or `_a4`) | 18 cutting stencils, one per page, true size |
| `1_print/contact_sheet.png` | overview of all 18 |
| `drop_log.csv` | the 54 drops in the order to do them; fill in one row per drop |
| `2_imu_firmware/` | ESP32 + BNO085 logger (source + built `firmware.bin`) |
| `3_scripts/imu_record.py` | records the IMU over USB; `allan.py` = IMU noise calibration |
| `4_reference/` | design table (`tiers.csv`), tier figure, SVG templates, full test instructions |

## 1. Print and cut (18 canopies)
- [ ] Print **page 1 only** at **"Actual size" / 100%**. Measure the 100 mm bar. If correct, print the rest.
- [ ] Cut along the **centre of the black line**.
- [ ] Knife-cut the **red slits** between the end ticks (no material removed).
      B1, B4, B6, M2, M4: slits < 1 mm, **do not cut**: treat them as no slits.
- [ ] Punch the **6 blue crosshairs** (line attachment points).
- [ ] Write the code (B1 ... W6) on every canopy.
- [ ] 6 lines per canopy, each **0.35 m**, tied to the payload's 6 slots.

## 2. Payload and IMU
- [ ] Wire the BNO085 to the ESP32-S3: **SDA to GPIO5, SCL to GPIO6, 3V3, GND** (the firmware also auto-detects other pins).
      Sync LED on **GPIO21**, visible to the camera.
- [ ] Flash: `pio run -d firmware/imu_logger -t upload` (or ask Claude to do it).
- [ ] 1-min test: `uv run scripts/imu_record.py --out data/real/test --duration 60`
- [ ] **Weigh the payload** with lines and a canopy (the simulation assumed 95 g). Write it down.
- [ ] Optional, the night before: Allan variance log, payload completely still for 3+ h:
      `uv run scripts/imu_record.py --out data/real/allan/2026-10-31 --duration 10800 --allan`

## 3. Set-up
- Release height **4.0 m**. Payload flown **disc up, box down**.
- Camera **1.8 m** from the drop line, lens **0.8 m** high, aimed **0.45 m above the landing pad** (pad in frame).
- Hold the payload still >= 1 s before release.

## 4. Dropping
- Follow `drop_log.csv` **in order** (randomised blocks: every block drops every design once).
- Log **every** drop, failed ones too. Never redo a drop silently: add a new row and note why.
- Per drop: start the IMU recording, then release, then stop. Note the file names in the log.
- Watch for: slits fluttering open, big swings, tangles. Write it in `notes`.

## Not ready yet (tell Claude)
- RealSense model: the camera recorder script will be written once the model is known.
- LED mounting position.
