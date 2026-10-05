# Product Requirements Specification: Stair-Climbing Transforming Hexapod

| | |
|---|---|
| Document | REQ-HEX-001, revision A (draft for review) |
| Status | Draft. Derived from simulation only; no hardware has been built |
| Source of numbers | `robotics/hexapod_sim` (config + `results/`). Each simulation-derived value names its source |
| Companion | [MANUFACTURING.md](MANUFACTURING.md) |

**Conventions.** *Shall* = mandatory. *Should* = desirable. **TBC** = to be confirmed by hardware test or
a decision; do not treat as final. Verification method (V): **T** test, **A** analysis,
**I** inspection, **D** demonstration. Priority: **M** must, **S** should.

---

## 1. Purpose and scope

A small (about 6 kg), unmanned home robot that normally rolls on four wheels, transforms into a six-legged
"spider" at a staircase, climbs it, and transforms back. Its purpose is to **test the transforming-robot
concept**: whether changing shape is worth it, and what hardware it needs. It is a research prototype, not a
consumer product. It carries no person and, in this revision, no payload other than its own electronics.

**Out of scope for revision A:** stair descent, turning on stairs, outdoor use, carrying a human, any
vehicle styling shell, mass production.

## 2. Operational concept

| Mode | Description |
|---|---|
| Rover | Wheels folded under the hips, middle legs stowed, body 14 cm high. Skid-steer on four wheels. |
| Transform | At least 4 feet always on the ground. About 13 s each way (simulation). |
| Spider | Body 20 cm high, wheels braked and used as feet, alternating-tripod crawl (3 feet always down). |
| Safe/idle | Powered down or holding; legs in rover stance. |

Typical mission: drive to the stairs, detect them, align square to the first riser, transform, climb, detect
the top landing, transform back, continue driving.

## 3. Reference configuration (from simulation)

| Parameter | Value | Source |
|---|---|---|
| Total mass | 5.84 kg (torso 2.6 kg) | `config.py` |
| Torso | 40 x 18 x 6 cm | `config.py` |
| Legs | 6 x 3-DOF; coxa 4 cm, femur 20 cm, tibia 24 cm | `config.py` |
| Wheels | 4 corner legs, 10 cm diameter, 4 cm wide; 2 middle legs rubber feet | `config.py` |
| Actuators | 18 joint servos + 4 wheel motors | `model.py` |
| Joint range | coxa +/-103 deg; femur -52 to +137 deg; tibia -166 to +11 deg | `config.py` |
| Body height | rover 14 cm, spider 20 cm | `config.py` |

The simulation showed the leg lengths are **geometry-critical**: shorter legs (16/20 cm) could not reach the
rear footholds on a 35 degree staircase. Treat link lengths as controlled dimensions (see MANUFACTURING.md, section 5).

## 4. Requirements

### 4.1 Functional

| ID | Requirement | V | Pri |
|---|---|---|---|
| FR-001 | The robot shall drive on level floors in rover mode using four driven wheels. | D | M |
| FR-002 | The robot shall detect a staircase ahead and measure its rise and tread before transforming. | T | M |
| FR-003 | The robot shall align square to the first riser (within 5 deg) before transforming. | T | M |
| FR-004 | The robot shall transform from rover to spider and back without human assistance. | D | M |
| FR-005 | The robot shall climb a staircase upward in spider mode and detect the top landing. | D | M |
| FR-006 | After climbing, the robot shall return to rover mode and resume driving on the landing. | D | M |
| FR-007 | The robot shall refuse to transform or climb when stair measurements are out of range (section 4.2) and report why. | T | M |
| FR-008 | The robot should provide a remote/manual override for every mode change. | D | S |

### 4.2 Performance

Values marked "sim" were met in simulation (`results/summary.json`, `results/robustness.json`); hardware
must meet them with the stated margin.

| ID | Requirement | Basis | V | Pri |
|---|---|---|---|---|
| PR-001 | Climb a staircase with 18 cm rise, 26 cm tread, 90 cm width, at least 4 steps. | sim passes, 20/20 randomised runs | T | M |
| PR-002 | Goal: climb up to 20 cm rise. Staircase sweep passed 11/12 geometries (15-22 cm rise, 22-30 cm tread). | sim, `sweeps.json` | T | S |
| PR-003 | Transformation time (either direction) shall be at most 15 s. | sim 13 s | T | M |
| PR-004 | Climb time for 4 steps shall be at most 30 s. | sim 24 s | T | M |
| PR-005 | Rover speed shall be at least 0.3 m/s on level floor. | sim 0.3 m/s | T | M |
| PR-006 | Body roll shall stay within 5 deg and pitch within 40 deg during the climb. | sim 1.4 / 35 deg | T | M |
| PR-007 | Lateral deviation from the stair centreline shall stay within 5 cm. | sim 1.9 cm (11 cm without correction) | T | M |
| PR-008 | The static stability margin (centre of mass to support-polygon edge) shall be at least 4 cm at every instant of the climb. | sim min 5.9 cm | A,T | M |
| PR-009 | At least three feet shall be in firm ground contact whenever a leg is lifted. | design rule | T | M |
| PR-010 | The robot shall drive over thresholds up to 2 cm in rover mode. | wheel radius 5 cm, **TBC** | T | S |
| PR-011 | Total mass shall not exceed 6.5 kg. | sim 5.84 kg + 10% | I | M |
| PR-012 | The robot shall complete at least 3 stair missions plus 30 min of rover driving per charge. | **TBC** (see 4.4) | T | S |

### 4.3 Actuation

Torque needs come from simulation peaks. The sweep was erratic below about 5 N·m, so ratings below carry margin
over the **worst randomised trial (femur 9.7 N·m)**, not the typical 6.0 N·m.

| ID | Requirement | Basis | V | Pri |
|---|---|---|---|---|
| AR-001 | **Full-size build only.** Femur and tibia servos shall deliver at least 20 N·m peak (about 200 kg·cm). Basis: nominal peak 6.0 N·m; worst of 20 randomised runs 9.7 N·m; but a second randomised batch (seed 1, 15 runs) had one slip event that reached the 15 N·m test clamp and pitched the body to 78 deg. The requirement therefore sits above 15 N·m, and the slip event itself is an open item (O2). | T | M |
| AR-002 | Coxa (yaw) servos shall deliver at least 8 N·m peak. | sim 4.1 typical; 10 N·m was reached on 30 cm-tread stairs | T | M |
| AR-003 | Each leg joint shall hold its stance load (at least 4 N·m) continuously without thermal shutdown for 10 min. | **TBC** (rig test) | T | M |
| AR-004 | Wheel motors shall deliver at least 3 N·m and hold position when braked (hold used as foot). | `config.py` wheel limit | T | M |
| AR-005 | Joint position resolution shall be 0.1 deg or better, with joint-angle feedback. | design | I,T | M |
| AR-006 | Joints shall provide the ranges in section 3 plus 5 deg of mechanical overtravel, with software limits inside them. | `config.py` | I | M |
| AR-007 | Joint backlash shall be at most 1.0 deg. Simulation assumes none. | **TBC** | T | M |
| AR-008 | The low-level control loop shall run at 100 Hz or faster with at most 10 ms command-to-motion latency. | sim 100 Hz | T | M |
| AR-009 | Servos shall report current (torque) so overload and slip can be detected. | design | T | M |

> **Cost driver.** At full size the torque class in AR-001/AR-002 is far above hobby servos (about 35-50 kg·cm).
> Expect quasi-direct-drive actuators; their mass may also break the 5.8 kg budget (check data sheets).
> The half-scale research baseline in section 8 needs only hobby-class actuators.

### 4.4 Power and energy

| ID | Requirement | Basis | V | Pri |
|---|---|---|---|---|
| PW-001 | A removable battery pack with a protection board (over/under-voltage, over-current, short circuit, temperature). | safety | I,T | M |
| PW-002 | Initial pack size about 40 Wh (for example 4S Li-ion/LiPo). **TBC.** The simulation proxy gives only about 0.4 Wh per stair mission (1.0 kJ climb + 2 x 0.16 kJ transform), but it ignores servo inefficiency, idle current and electronics, so the real figure must be measured on the rig and the pack resized. | sim proxy, **TBC** | T | M |
| PW-003 | The power bus shall tolerate simultaneous peak servo demand without brown-out (peak current **TBC** from rig test). | **TBC** | T | M |
| PW-004 | Supply shall include a hardware emergency cut-off reachable without approaching the legs. | safety | D | M |
| PW-005 | Battery state of charge shall be monitored; the robot shall not start a climb below a charge reserve sufficient to finish it (reserve **TBC**). | design | T | M |

### 4.5 Sensing and compute

| ID | Requirement | V | Pri |
|---|---|---|---|
| SN-001 | A forward depth sensor (camera or ToF) shall measure stair rise/tread to +/-1 cm at 0.5 m range, and detect the stair edge and landing. | T | M |
| SN-002 | An IMU shall provide body roll/pitch/yaw at 100 Hz or faster. | T | M |
| SN-003 | Every joint and wheel shall have position feedback. | I | M |
| SN-004 | Downward cliff/edge sensors shall prevent driving off an unexpected drop in rover mode. | T | M |
| SN-005 | Foot-contact detection (current or load sensing) shall confirm each touchdown before weight is shifted. | T | S |
| CP-001 | A real-time controller shall run joint loops; a higher-level computer shall run perception and planning. | I | M |
| CP-002 | The robot shall run safe (stop, hold) if the high-level computer or perception stops responding for more than 0.5 s. | T | M |

### 4.6 Safety

| ID | Requirement | V | Pri |
|---|---|---|---|
| SF-001 | A hardware emergency stop shall remove power from all actuators; legs are not back-drivable, so a controlled lowering mode shall exist (**TBC** which is safer). | D | M |
| SF-002 | Torque and speed limits shall be enforced in firmware independent of the planner. | T | M |
| SF-003 | Tip-over detection (roll or pitch beyond limits) shall trigger a controlled stop. | T | M |
| SF-004 | The robot shall not transform or climb with a person within 0.5 m of the legs (**TBC** sensing method). | T | M |
| SF-005 | Moving legs create pinch/crush points; guards or low-force limits shall be applied and a hazard analysis completed before unsupervised operation. | A | M |
| SF-006 | All stair tests shall use a tether/safety line and a soft landing zone. | I | M |
| SF-007 | The battery shall comply with the transport and cell-safety standards for its chemistry. | I | M |

### 4.7 Environment and interfaces

| ID | Requirement | V | Pri |
|---|---|---|---|
| EN-001 | Indoor use, 5-35 deg C, dry. | T | M |
| EN-002 | Floors: hard floor and low carpet for rover mode; stair treads with friction coefficient at least 0.8. The simulation's effective foot/wheel-on-stair friction is about 1.0-1.2 (MuJoCo uses the larger of the two surfaces), so slip on slicker stairs is **not yet tested**; the 0.8 figure is **TBC** and must be validated on the rig (risk R7). | T | M |
| EN-003 | Stair width at least 80 cm for the reference stance. | I | M |
| IF-001 | A service port for firmware update and logging. | I | M |
| IF-002 | A wireless link for monitoring and override; encrypted. | T | S |

### 4.8 Software and data

| ID | Requirement | V | Pri |
|---|---|---|---|
| SW-001 | The firmware shall implement the mode state machine: rover, transform, spider, safe; with no transition skipping. | T | M |
| SW-002 | The gait/transform planner shall run the same plan as the validated simulation (`plans.py`) and be regression-tested against it. | T | M |
| SW-003 | The robot shall log joint torques, body attitude, contacts and faults at 100 Hz for every mission. | I | M |
| SW-004 | Camera images shall be processed on board; images shall not be stored or transmitted unless explicitly enabled by the owner. | I | M |
| SW-005 | Updates shall be signed, and a failed update shall leave the previous version bootable. | T | S |

### 4.9 Reliability and maintenance

| ID | Requirement | V | Pri |
|---|---|---|---|
| RL-001 | The prototype shall survive 50 complete stair missions without failure of a structural part, joint or latch. Target for later revisions: 500. | T | M |
| RL-002 | Cable harnesses crossing joints shall survive 100,000 joint cycles (**TBC** test method). | T | M |
| RL-003 | A leg (3 servos) shall be replaceable in under 30 min with hand tools. | D | S |
| RL-004 | Wear items (wheel tyres, servo gears) shall be identified with an inspection interval. | I | M |

## 5. Verification plan (summary)

| Stage | Purpose | Requirements covered |
|---|---|---|
| Simulation (done) | Geometry, torque, gait, transform clearance | PR-001..009, AR-001/002 (estimates) |
| Single-leg rig | Torque, thermal, wheel-as-foot contact, backlash | AR-001..009, PW-003 |
| Powered full prototype on a tether | Transform, stand, drive | FR-001, FR-004, PR-003, PR-005 |
| Staged stair tests (1, 2, 4 steps) | Climb, drift, margin | FR-005/006, PR-001..009 |
| Endurance + safety review | Reliability, E-stop, hazards | RL-001..004, SF-001..007 |

Every test records results against the requirement ID and the hardware serial/revision.

## 6. Traceability to the simulation

| Simulation result | Where it appears |
|---|---|
| Mission success, 20/20 randomised runs | PR-001 |
| Transform 13 s, climb 24 s | PR-003, PR-004 |
| Lateral drift 1.9 cm with correction | PR-007, SF-003 |
| Torque 6.0 typical / 9.7 worst (20 runs) / >=15 (one slip in a second batch of 15), femur | AR-001 |
| Reach marginal at top of stairs (up to 1.9 cm short) | MANUFACTURING.md, section 5 (link tolerances); open item O2 |
| Servo torque sweep erratic below 5 N·m | AR-001 margin |

## 7. Open items and assumptions

| # | Item |
|---|---|
| O1 | Real servo behaviour (backlash, latency, torque-speed curve, back-drive) is not simulated. AR-003/007/008 must be measured. |
| O2 | Reach is marginal at the top of the stairs. Decide: longer legs, a better hand-over, or a lower pitch limit, then re-run the 100-trial robustness test. |
| O3 | Real battery energy, peak current and thermal limits (PW-002/003). |
| O4 | Descent is out of scope but is a likely requirement for a home robot; it changes safety analysis (SF-001, SF-003). |
| O5 | Target market and therefore the applicable standards and regulations (candidates for confirmation: ISO 13482 personal-care robot safety, IEC 62368-1 equipment safety, EMC rules for the sale region, IEC 62133 / UN 38.3 for the battery). |
| O6 | Whether the end product is a research platform or something sold to consumers. This changes almost every requirement in 4.6-4.9. |

## 8. Research baseline: half-scale platform (proposed revision B)

For research (testing whether and how the transformation works) a **half-scale robot on half-scale
stairs** is proposed. Torque scales as size^4, so the actuator requirement drops about 16x. Evidence:
`results/scale_study.json` (`python scale_study.py`; each row = 1 nominal run + 15 randomised runs).

| Scale | Robot mass (ideal x1 / real-world guess x2-3) | Stair rise | Peak femur torque, nominal | Worst of 15 randomised | Randomised success |
|---|---|---|---|---|---|
| 1.00 | 5.8 kg | 18 cm | 6.0 N·m (61 kg·cm) | >=15 N·m (clamp hit) | 14/15 (one 78 deg pitch excursion) |
| 0.75 (x2 mass) | 4.9 kg | 13.5 cm | 2.4 N·m | 4.7 N·m | 15/15, one 56 deg excursion |
| 0.60 (x2 mass) | 2.5 kg | 10.8 cm | 1.0 N·m | 1.9 N·m | 14/15, one 72 deg excursion |
| **0.50 (x2 mass)** | **1.5 kg** | **9 cm** | **0.47 N·m (4.8 kg·cm)** | **0.52 N·m (5.3 kg·cm)** | **15/15, pitch <= 36 deg** |
| **0.50 (x3 mass)** | **2.2 kg** | **9 cm** | **0.65 N·m (6.6 kg·cm)** | **0.72 N·m (7.3 kg·cm)** | **15/15, pitch <= 38 deg** |
| 0.40 (x2 mass) | 0.75 kg | 7.2 cm | 0.19 N·m | 0.21 N·m | 15/15 |

Half-scale requirements (these replace the full-size values where they differ; all other requirements stand):

| ID | Requirement (half-scale) | Basis |
|---|---|---|
| HS-001 | Test staircase 9 cm rise, 13 cm tread, at least 4 steps, at least 45 cm wide. | scale 0.5 |
| HS-002 | Links: coxa 2 cm, femur 10 cm, tibia 12 cm (+/-0.25 mm); wheels 5 cm diameter. | scale 0.5 of section 3 |
| HS-003 | Body about 20 x 9 x 3 cm; rover height 7 cm; spider height 10 cm. | scale 0.5 |
| HS-004 | Mass at most 2.5 kg. | simulated up to 2.2 kg |
| HS-005 | Leg joint actuators: at least 1.5 N·m (about 15 kg·cm) peak, 2x the worst simulated demand (0.72 N·m), with joint feedback, backlash at most 1.0 deg. | scale study |
| HS-006 | Wheel motors: at least 0.25 N·m holding/drive. | 0.19 N·m scaled limit |
| HS-007 | Rover speed at least 0.15 m/s. | scaled from PR-005 |

**Caveats on this result.** (1) Real actuators and batteries do not shrink with size cubed, hence the
x2 and x3 mass cases; weigh the real parts before trusting a row. (2) The gait runs at the same absolute
timing at every scale, so smaller robots move *relatively* slower and more quasi-statically, which
flatters them: the large-scale slip events may be partly a dynamic effect. (3) This tests the
transformation concept on proportionally smaller stairs; it does not show the robot can climb a standard
home staircase.
