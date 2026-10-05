"""MuJoCo wrapper: servo control from the choreographer, logging, video."""
from __future__ import annotations

from dataclasses import dataclass, field
import math

import mujoco
import numpy as np

from .choreo import BodyPose, Choreographer, Phase
from .config import RobotConfig, StairConfig
from .kinematics import LEGS, WHEEL_LEGS, fk, ik, leg_geometries
from .model import build_xml
from .plans import rover_stance_body, world_feet

PHYS_DT = 0.002
CTRL_EVERY = 5            # control at 100 Hz
JOINTS = [f"{leg}_{k}" for leg in LEGS for k in ("q1", "q2", "q3")]


@dataclass
class Log:
    t: list = field(default_factory=list)
    phase: list = field(default_factory=list)
    p: list = field(default_factory=list)
    rpy: list = field(default_factory=list)
    tau: list = field(default_factory=list)       # 18 joint torques
    qd: list = field(default_factory=list)        # 18 joint velocities
    wtau: list = field(default_factory=list)      # 4 wheel torques
    wqd: list = field(default_factory=list)       # 4 wheel speeds
    ik_viol: list = field(default_factory=list)
    n_feet: list = field(default_factory=list)    # feet in ground contact
    cmd_pitch: list = field(default_factory=list)

    def arrays(self):
        return {k: np.array(v) for k, v in self.__dict__.items()}


class HexapodSim:
    def __init__(self, cfg: RobotConfig | None = None,
                 stairs: StairConfig | None = None):
        self.cfg = cfg or RobotConfig()
        self.stairs = stairs or StairConfig()
        self.model = mujoco.MjModel.from_xml_string(build_xml(self.cfg, self.stairs))
        self.data = mujoco.MjData(self.model)
        m = self.model
        self.geo = leg_geometries(self.cfg)
        self.torso = m.body("torso").id
        self.j_qadr = {n: m.joint(n).qposadr[0] for n in JOINTS}
        self.j_vadr = {n: m.joint(n).dofadr[0] for n in JOINTS}
        self.a_id = {n: m.actuator(n).id for n in JOINTS}
        self.wheel_j = {leg: m.joint(f"{leg}_wheel").id for leg in WHEEL_LEGS}
        self.wheel_a = {leg: m.actuator(f"{leg}_wheel").id for leg in WHEEL_LEGS}
        self.wheel_q = {leg: m.jnt_qposadr[self.wheel_j[leg]] for leg in WHEEL_LEGS}
        self.wheel_target = {leg: 0.0 for leg in WHEEL_LEGS}
        self._was_driving = False
        self.rover_body = rover_stance_body(self.cfg)
        self.ch: Choreographer | None = None
        self.log = Log()
        self.events: list = []            # (t, text) notable things
        self.self_contacts: dict = {}     # pair -> (first_t, max_depth)
        self.strikes: dict = {}           # body-part hits on stairs/ground
        self.geom_name = {i: (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, i) or "")
                          for i in range(m.ngeom)}
        self._frames: list = []
        self._renderer = None
        self.video_every = 0
        self.video_size = (640, 360)

    # ------------------------------------------------------------------
    def reset_rover(self, x=0.0, y=0.0, yaw=0.0):
        m, d = self.model, self.data
        mujoco.mj_resetData(m, d)
        a = m.jnt_qposadr[m.joint("root").id]
        d.qpos[a:a + 3] = [x, y, self.cfg.rover_height]
        d.qpos[a + 3:a + 7] = [math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]
        for leg in LEGS:
            q, _ = ik(self.cfg, self.geo[leg], self.rover_body[leg])
            for k, val in zip(("q1", "q2", "q3"), q):
                n = f"{leg}_{k}"
                d.qpos[self.j_qadr[n]] = val
                d.ctrl[self.a_id[n]] = val
        for leg in WHEEL_LEGS:
            d.ctrl[self.wheel_a[leg]] = 0.0
            self.wheel_target[leg] = 0.0
        mujoco.mj_forward(m, d)
        b = BodyPose(np.array([x, y, self.cfg.rover_height]), 0.0, yaw)
        self.ch = Choreographer(self.cfg, [], b,
                                world_feet(self.rover_body, b), self.rover_body)
        self.log = Log()

    # ------------------------------------------------------------------
    def state(self) -> dict:
        d = self.data
        R = d.xmat[self.torso].reshape(3, 3)
        p = d.xpos[self.torso].copy()
        pitch = math.asin(max(-1.0, min(1.0, R[2, 0])))
        roll = math.atan2(R[2, 1], R[2, 2])
        yaw = math.atan2(R[1, 0], R[0, 0])
        foot_xy = {}
        for leg in LEGS:
            q = [d.qpos[self.j_qadr[f"{leg}_{k}"]] for k in ("q1", "q2", "q3")]
            foot_xy[leg] = (p + R @ fk(self.cfg, self.geo[leg], q))[:2]
        return dict(p=p, pitch=pitch, roll=roll, yaw=yaw, foot_xy=foot_xy,
                    ground=self.stairs.height_at(p[0]), R=R)

    def _apply_control(self, targets: dict, ik_cache=None):
        d = self.data
        worst = 0.0
        for leg in LEGS:
            q, v = ik(self.cfg, self.geo[leg], targets[leg])
            worst = max(worst, v)
            for k, val in zip(("q1", "q2", "q3"), q):
                d.ctrl[self.a_id[f"{leg}_{k}"]] = val
        return worst

    def _wheels(self, driving: bool, cmd: dict, dt: float):
        d, R = self.data, self.data.xmat[self.torso].reshape(3, 3)
        body_y = R[:, 1]
        for leg in WHEEL_LEGS:
            q = d.qpos[self.wheel_q[leg]]
            if driving:
                axis = d.xaxis[self.wheel_j[leg]]
                sgn = 1.0 if float(axis @ body_y) >= 0 else -1.0
                tgt = self.wheel_target[leg] + sgn * cmd[leg] * dt
                self.wheel_target[leg] = min(max(tgt, q - 1.0), q + 1.0)
            elif self._was_driving:
                self.wheel_target[leg] = q       # brake where it stopped
            d.ctrl[self.wheel_a[leg]] = self.wheel_target[leg]
        self._was_driving = driving

    # ------------------------------------------------------------------
    def _contacts(self, t):
        m, d = self.model, self.data
        feet = set()
        for i in range(d.ncon):
            c = d.contact[i]
            g1, g2 = int(c.geom1), int(c.geom2)
            n1, n2 = self.geom_name[g1], self.geom_name[g2]
            r1, r2 = m.body_rootid[m.geom_bodyid[g1]], m.body_rootid[m.geom_bodyid[g2]]
            fn = lambda n: n.endswith("_wheel_geom") or n.endswith("_foot")
            if r1 != 0 and r2 != 0:
                if c.dist < -0.002:
                    key = tuple(sorted((n1, n2)))
                    t0, depth = self.self_contacts.get(key, (t, 0.0))
                    self.self_contacts[key] = (t0, max(depth, -c.dist))
                continue
            robot, other = (n1, n2) if r1 != 0 else (n2, n1)
            if fn(robot):
                feet.add(robot)
            elif c.dist < -0.002:
                key = (robot, other)
                t0, depth = self.strikes.get(key, (t, 0.0))
                self.strikes[key] = (t0, max(depth, -c.dist))
        return len(feet)

    def _record(self, t, targets, viol):
        d, st = self.data, self.state()
        m_ = self.model
        L = self.log
        tau = np.array([d.actuator_force[self.a_id[n]] for n in JOINTS])
        qd = np.array([d.qvel[self.j_vadr[n]] for n in JOINTS])
        L.t.append(t)
        L.phase.append(self.ch.phase_name)
        L.p.append(st["p"])
        L.rpy.append([st["roll"], st["pitch"], st["yaw"]])
        L.tau.append(tau)
        L.qd.append(qd)
        L.wtau.append([d.actuator_force[self.wheel_a[l]] for l in WHEEL_LEGS])
        L.wqd.append([d.qvel[m_.jnt_dofadr[self.wheel_j[l]]] for l in WHEEL_LEGS])
        L.ik_viol.append(viol)
        L.n_feet.append(self._contacts(t))
        L.cmd_pitch.append(self.ch.body.pitch)

    # ------------------------------------------------------------------
    def enable_video(self, every_s=0.04, size=(640, 360)):
        self.video_every = every_s
        self.video_size = size

    def _grab(self):
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.model, self.video_size[1],
                                             self.video_size[0])
        cam = mujoco.MjvCamera()
        cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        p = self.data.xpos[self.torso]
        cam.lookat[:] = [p[0] + 0.25, p[1], p[2] - 0.05]
        cam.distance, cam.azimuth, cam.elevation = 2.3, 90, -14
        self._renderer.update_scene(self.data, cam)
        self._frames.append(self._renderer.render().copy())

    def save_video(self, path, fps=25):
        import imageio.v2 as imageio
        with imageio.get_writer(path, fps=fps, codec="libx264",
                                macro_block_size=1) as w:
            for f in self._frames:
                w.append_data(f)

    # ------------------------------------------------------------------
    def run(self, phases, max_time=600.0, until=None):
        """Execute phases (appended to the running script). Returns when the
        script is exhausted, the robot falls, or max_time elapses."""
        ch, d, m = self.ch, self.data, self.model
        source = None if isinstance(phases, (list, tuple)) else phases
        if source is None:
            ch.queue.extend(phases)
        t_end = d.time + max_time
        next_frame = d.time
        while (not ch.done or source) and d.time < t_end:
            st = self.state()
            if source and ch.cur is None and not ch.queue:
                ch.resync(st)                      # re-reference on measurements
                nxt = source.next_phase(ch, st)
                if nxt is None:
                    break
                ch.queue.append(nxt)
            ch.update(d.time, st)
            if ch.done and source is None:
                break
            if ch.done:
                continue                           # ask the planner again
            targets = ch.foot_targets_body()
            viol = self._apply_control(targets)
            driving = ch.mode == "drive"
            self._wheels(driving, ch.wheel_cmd, CTRL_EVERY * PHYS_DT)
            for _ in range(CTRL_EVERY):
                mujoco.mj_step(m, d)
            self._record(d.time, targets, viol)
            if self.video_every and d.time >= next_frame:
                self._grab()
                next_frame += self.video_every
            if abs(st["roll"]) > 1.0 or abs(st["pitch"]) > 1.3:
                self.events.append((d.time, "FELL OVER"))
                return False
            if until is not None and until(st):
                break
        return ch.done
