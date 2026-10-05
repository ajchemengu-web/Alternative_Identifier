# Manufacturing and Build Procedures: Stair-Climbing Transforming Hexapod

| | |
|---|---|
| Document | MFG-HEX-001, revision A (draft for review) |
| Applies to | Prototype builds (P1 leg rig, P2 full prototype, P3 small validation batch) |
| Requirements | [REQUIREMENTS.md](REQUIREMENTS.md) (REQ-HEX-001) |
| Status | Draft. No hardware exists yet. Values marked **TBC** must be set from supplier data sheets or test. Torque, fastener and print values are placeholders to be replaced, not recommendations |

---

## 1. Purpose and phase gates

This procedure takes the design from simulation to a working, tested, documented robot. Work is gated: do not
start a phase until the previous exit criteria are met and signed off.

| Phase | Build | Exit criteria |
|---|---|---|
| P0 | Simulation (done) | Mission passes; requirements baselined (REQ-HEX-001 rev A) |
| P1 | **Single-leg test rig** | AR-001..009 measured on real actuators; wheel-as-foot contact confirmed; torque/thermal margins known; open items O1, O3 closed; simulation updated with real servo data |
| P2 | One full prototype | Stands, transforms both ways and drives on a tether; PR-003, PR-005 met; no structural damage |
| P3 | Small batch (3-5 units) | Staged stair tests passed (1, 2, 4 steps); PR-001..009 met; RL-001 (50 missions) met; hazard analysis (SF-005) signed off |
| P4 | Pilot production (only if productising) | Supplier qualification, injection-moulded/machined parts, production test fixtures, regulatory path (O5, O6) |

## 2. Document and configuration control

1. Every part, subassembly and the whole robot has a **part number, revision and serial number**. Keep a
   single master BOM in version control next to the code; the simulation config
   (`hexapod_sim/config.py`) is a controlled document: any design change updates it in the same change.
2. **Engineering change**: describe the change, the requirement it affects, and re-run the simulation and tests
   before approval. Record who approved it.
3. Each robot gets a **build traveler** (section 9): a paper or digital record that follows it through every
   step below, with dated, initialled results.
4. Firmware, planner version and calibration data are recorded against the serial number.

## 3. Bill of materials and procurement

| Group | Items | Notes |
|---|---|---|
| Actuators | 18 joint servos/actuators (AR-001/002), 4 wheel motors with encoders and brakes/holding (AR-004) | Longest lead time and largest cost: order first (risk R1) |
| Structure | Coxa/femur/tibia links, hip brackets, torso frame, wheel hubs | See section 5 for tolerances |
| Wheels | 4 x 100 mm wheels with elastomer tyre | Friction target in EN-002 |
| Electronics | Real-time controller, high-level computer, IMU, depth sensor, cliff sensors, current sensing, motor drivers | CP-001, SN-001..005 |
| Power | Battery pack with protection board, fuses, main contactor/e-stop, DC-DC converters | PW-001..005 |
| Wiring | Flexible high-cycle cable across joints, locking connectors | RL-002 |
| Hardware | Fasteners, thread-locker, bearings/bushings, cable clips | Use one fastener family to limit tooling |

**Procurement rules**
1. Buy from suppliers that provide data sheets with rated peak and continuous torque, backlash and a
   dimensional drawing. Reject actuators without them.
2. Order **spares**: at least 25% extra actuators, plus 2 spare of each wheel and link.
3. Record supplier, lot/date code and serial number of every actuator and battery cell in the traveler.

### 3.1 Incoming inspection

| Item | Check | Accept | Action on reject |
|---|---|---|---|
| Each actuator | Visual, free rotation, power on, command a sweep across range, measure no-load current | Smooth, no noise/jam, within data sheet | Return/replace |
| **Sample (or all, at prototype volume)** | Stall-torque check with a torque arm and scale at 25%, 50%, 100% of rated; measure backlash with a dial gauge | Torque >= data sheet x 0.9; backlash <= 1.0 deg (AR-007) | Quarantine lot |
| Battery | Cell voltage and internal resistance, protection board function | Within data sheet, balanced | Return |
| Printed/machined parts | Dimensional check of critical features (section 5) | Within tolerance | Rework or scrap |
| Sensors | Power-up and output check | Valid readings | Replace |

## 4. Fabrication

Prototype parts may be 3D printed or machined. Choose per part by load; structural links are the first
candidates for metal.

| Part | Prototype process | Production candidate |
|---|---|---|
| Femur, tibia, hip brackets (highest loads) | CNC aluminium, or carbon-fibre-filled nylon print for first fit-checks only | CNC or die cast aluminium |
| Torso frame | Sheet/plate aluminium or composite | Same |
| Covers, cable guides | Printed PETG/nylon | Injection moulded |
| Wheel hubs | Machined aluminium with moulded tyre | Same |

**Fabrication procedure (each part)**
1. Verify the drawing revision matches the BOM.
2. Fabricate. For prints: record material, nozzle, layer height, orientation and infill in the traveler (print
   load-bearing links with continuous fibre or high infill and orient layers to carry bending: **TBC**).
3. Deburr, remove supports, clean bearing seats.
4. Inspect critical dimensions (section 5); record measured values.
5. Mark the part number, revision and serial/lot. Reject or rework nonconforming parts and log a
   nonconformance (section 9).

## 5. Critical dimensions and tolerances

The simulation showed reach is marginal at the top of the stairs (up to 1.9 cm short). Small length errors
therefore directly reduce stair capability, so these dimensions are **controlled**:

| Dimension | Nominal | Tolerance | Why |
|---|---|---|---|
| Femur length (joint axis to joint axis) | 200 mm | +/-0.5 mm | Reach |
| Tibia length (joint axis to wheel/foot centre) | 240 mm | +/-0.5 mm | Reach |
| Coxa offset | 40 mm | +/-0.5 mm | Reach |
| Hip positions on torso (x, y) | x = +/-150, 0; y = +/-120 mm | +/-0.5 mm | Stance symmetry, stability margin |
| Wheel radius (loaded) | 50 mm | +/-0.5 mm | Footing height, rover speed |
| Joint axis perpendicularity | | 0.2 deg | Wheel plane lies in the leg plane |
| Left/right mass balance | | within 5% | Tip margin |
| Total mass | 5.84 kg | <= 6.5 kg (PR-011) | Torque margin |

**Mass control.** Weigh every subassembly and compare with the masses in `config.py` (coxa 0.12, femur 0.17,
tibia 0.14 kg per leg, wheel 0.15 kg, torso 2.6 kg). A subassembly more than 10% over budget triggers a
review, because torque need scales with mass.

## 6. Subassembly build

### 6.1 Leg (6 per robot)
1. Fit bearings/bushings in the femur and tibia joints. Check free rotation.
2. Mount the coxa actuator in the hip bracket. Torque the fasteners to the specified value (**TBC**, per
   fastener class), apply thread-locker.
3. Fit the femur actuator to the coxa link, then the tibia actuator to the femur link, with the horn
   at the **centred position** (see 7.1).
4. Fit the wheel motor and wheel (corner legs) or the rubber foot (middle legs) to the tibia end.
5. Route the cable through the joints with service loops sized for full range; clamp so the cable never bends
   at a connector. Check range of motion by hand through every limit (section 3 of REQUIREMENTS.md).
6. Weigh. Record. Bench-test the leg: power it, run a full-range sweep, record current.

### 6.2 Torso
1. Install the frame, battery tray and mounting for the six hips.
2. Mount the controller, high-level computer, motor drivers, power distribution, emergency cut-off and fuses.
3. Install the IMU rigidly with its axes aligned to the body (record the mounting offset).
4. Mount the depth sensor and cliff sensors; record their positions for calibration.
5. Wire per the harness drawing; check continuity and insulation; label every connector.

## 7. Final assembly and calibration

1. Mount the six legs on the torso on a **rigid assembly jig** that holds the hips at the correct positions.
2. Connect harnesses. Confirm no strain at full range of motion.
3. **Power-up sequence** (current-limited bench supply first, then battery): controller only, then sensors,
   then actuators one leg at a time. Stop at any unexpected current.

### 7.1 Calibration
| Calibration | Method | Recorded |
|---|---|---|
| Joint zero | Hold each leg in a **zeroing jig** (the spider-stance pose from `spider_stance_body`); set encoder zero | Offsets per joint |
| Joint limits | Command slowly to each software limit; confirm overtravel margin (AR-006) | Limits |
| Servo gains | Start from the simulation values (position gain 80 N·m/rad, damping 2.0 N·m·s/rad) scaled to actuator units; tune on the rig | Gains |
| IMU | Level on a flat table, record gravity vector | Offsets |
| Depth sensor | Measure against a calibrated stair mock-up | Extrinsics, error |
| Wheels | Measure rolled distance per revolution | Effective radius |
| Mass and centre of mass | Weigh; balance on two scales to locate the centre of mass | Mass, CoM |

## 8. Test and acceptance

Run in this order. **Stop and fix** after any failure; do not continue to the next stage.

| # | Test | Method | Pass criterion | Req |
|---|---|---|---|---|
| T1 | Electrical safety | Insulation and continuity, fuse and e-stop function | E-stop removes all actuator power | SF-001, PW-004 |
| T2 | Joint range and holding | Sweep each joint; hold stance load for 10 min | Ranges as spec, no thermal fault | AR-003, AR-006 |
| T3 | Per-leg torque | Torque arm at 25/50/100% | >= AR-001/002 | AR-001/002 |
| T4 | Stand | Tethered; spider stance, then rover stance | Level within 2 deg, no overheating | PR-006 |
| T5 | Transform | Tethered, both ways, 10 cycles | <= 15 s, >= 3 feet always down, no collisions | FR-004, PR-003, PR-009 |
| T6 | Rover drive | Straight line and thresholds | >= 0.3 m/s; clears a 2 cm threshold | PR-005, PR-010 |
| T7 | Stair detection | Against a measured stair mock-up | +/-1 cm | SN-001, FR-002 |
| T8 | Staged climb | **1 step, then 2, then 4**, tethered, soft landing | Per PR-001..008; log torques | PR-001..008 |
| T9 | Fault handling | Cut perception link, trigger tilt, low battery | Stops safely | CP-002, SF-003, PW-005 |
| T10 | Endurance | 50 complete missions | No structural failure | RL-001 |

For each test, record: serial number, firmware/planner version, date, operator, raw data file, pass/fail.
Compare the logged torques and attitude with the simulation (`results/summary.json`); a large difference means
the simulation model needs updating (feed the finding back into `config.py`).

## 9. Quality records

Per robot, keep: the build traveler, inspection data (section 5 measurements), calibration data, test results
(section 8), and any **nonconformance reports** (what was wrong, disposition, root cause, corrective action).
Records are retained for the life of the unit and indexed by serial number.

## 10. Safety during build and test

1. **Battery.** Handle only with the protection board fitted. Charge in a fire-safe container, supervised.
   Never charge a damaged pack. Store partially charged.
2. **Mechanical.** Legs can pinch and crush. Before working near the legs, disconnect the battery or engage the
   emergency cut-off and confirm the actuators are unpowered. Support the body on blocks before power-up.
3. **Stair tests.** Tether to a rated anchor; soft landing zone; clear exclusion area; a second person holds the
   e-stop. Never test descent or untethered until separately approved.
4. **Tools and PPE.** Eye protection for machining, printing post-processing and tests.
5. **Stop conditions.** Any smell of burning, swelling battery, unexpected motion or loud noise: remove power
   immediately and log it.

## 11. Packaging, labelling and shipping

1. Label each unit: part number, serial, revision, battery information, date.
2. Remove the battery for transport and protect the legs (fold to rover stance and brace).
3. Lithium batteries are regulated dangerous goods for shipping (UN 38.3 test summary, correct UN numbers and
   labelling). Confirm requirements with the carrier before every shipment. **TBC.**

## 12. Maintenance and service

| Item | Inspection | Interval (**TBC**) |
|---|---|---|
| Wheel tyres | Wear, delamination | Every 10 missions |
| Joint cables | Fatigue, chafing | Every 25 missions |
| Fasteners | Re-torque check, thread-locker marks | Every 25 missions |
| Actuator gears | Backlash, noise, temperature | Every 50 missions |
| Battery | Capacity, swelling | Each charge / monthly |

Replace a leg as a unit (RL-003). After any repair, repeat T2-T5 for the affected leg and re-calibrate it.

## 13. Risk register (top risks)

| ID | Risk | Likelihood / Impact | Mitigation | Owner |
|---|---|---|---|---|
| R1 | Required actuators (about 12 N·m peak, AR-001) are expensive, heavy or have long lead times | High / High | Order first; evaluate quasi-direct-drive; reduce mass; P1 rig before buying 18 | TBC |
| R2 | Reach is marginal at stairs top (sim, O2); real link errors reduce it | Medium / High | Tight length tolerances (section 5); lengthen legs or improve hand-over; re-run robustness | TBC |
| R3 | Real servo backlash, latency or back-drive breaks the gait | Medium / High | Measure on P1; update the simulation; adjust gains | TBC |
| R4 | Falling on stairs damages the robot or injures someone | Medium / High | Tether, soft landing, stop conditions, tip-over detection (SF-003/006) | TBC |
| R5 | Battery energy/peak current underestimated | Medium / Medium | Measure on P1; size pack from data (PW-002/003) | TBC |
| R6 | Joint cables fail from flexing | Medium / Medium | High-cycle cable, service loops, cycle test (RL-002) | TBC |
| R7 | Wheel-as-foot slips on real stair edges | Medium / High | Test materials on rig; adjust foothold margin; foot-contact sensing (SN-005) | TBC |
| R8 | Perception errors cause a bad foothold | Medium / High | Reject out-of-range stairs (FR-007); verify landing detection (SN-001) | TBC |

## 14. Open items

1. Choose actuator supplier and confirm AR-001/002 availability and cost (R1).
2. Define P1 rig design: single leg on a load frame with force plate and thermal logging.
3. Decide structural materials per part (section 4).
4. Set fastener/torque specifications and print/machining parameters (all **TBC** above).
5. Confirm target market and applicable standards (REQUIREMENTS.md, O5/O6) before P3.
6. Assign owners for risks R1-R8.
