# EPAOA Motion Compatibility reference implementation

This repository contains an executable implementation of the EPAOA Motion Compatibility Profile introduced in the European Physical AI Operations Architecture.

The implementation keeps source devices, canonical Robot Control semantics and target devices separate:

```text
source native                 canonical EPAOA                    target native
─────────────                 ───────────────                    ─────────────
SO101 leader (deg) ────────► joint position (rad) ────────────► SO101 follower (deg)
                         └──► joint position (rad) ────────────► URDF simulation (rad)

SO101 normalized ───────────► expressive head SI semantics ────► Reachy Mini / MuJoCo
Quest controls (0..1/-1..1) ► joint position (rad) ────────────► SO101 follower (deg)
```

Equal array lengths or equal motor names are never treated as proof of compatibility.

## Files

- `motion_compatibility.py` — dependency-free profile registry, validation, conversion and simulation state.
- `motion_profiles/so101-leader-to-so101-follower.json` — SO101 physical reference mapping.
- `motion_profiles/so101-leader-to-urdf-simulation.json` — same source mapped to the browser URDF target.
- `motion_profiles/quest-controller-to-so101-follower.json` — reference mapping from normalized Quest controller channels to SO101 joints.
- `motion_profiles/so101-leader-to-reachy-mini.json` — heteromorphic mapping from a normalized SO101 leader to Reachy Mini expressive head/antenna motion.
- `reachy_mini_target.py` — optional adapter for the official Reachy Mini SDK.
- `tests/test_motion_compatibility.py` — executable E2 reference tests.

The canonical EPAOA schema lives in the EPAOA repository as
`schemas/motion-compatibility-profile.schema.json`.

## Safety and evidence boundary

A successful Motion Compatibility decision means only that a declared source,
mapping and target representation are compatible. It is **not** permission to
move.

The intended command path is:

```text
source
  ↓
Motion Compatibility Profile
  ↓
canonical Robot Control command
  ↓
target-native command
  ↓
local Safety Authority / limits
  ↓
actuator
```

No conversion silently clips out-of-range values. Missing DOFs, mapping digest
changes and unsupported ranges fail closed.

The live `TeleoperationManager` also fingerprints the active LeRobot leader
and follower calibration objects with SHA-256 so the session can retain the
actual calibration identities alongside the compatibility and mapping IDs.

## Laptop / simulation-only development

For a developer laptop, start the webserver without provisioning, cameras, NetworkManager, Bluetooth, Blockly hardware or teleoperation auto-start:

```bash
LEROBOT_SIMULATION_ONLY=1 PORT=8000 python webserver.py
```

Then open:

```text
http://localhost:8000/viewer?source=simulation
```

This mode intentionally leaves the EPAOA Motion Compatibility registry and URDF simulation APIs enabled while skipping robot-cell hardware services. It is the recommended way to run the reference implementation on a laptop.

## API

List profiles:

```http
GET /api/motion/profiles
```

Resolve without moving anything:

```http
POST /api/motion/resolve
Content-Type: application/json

{
  "profile_id": "MC-SO101-LEADER-SO101-FOLLOWER-V1",
  "values": {
    "shoulder_pan": 10,
    "shoulder_lift": 0,
    "elbow_flex": 0,
    "wrist_flex": 0,
    "wrist_roll": 0,
    "gripper": 0
  }
}
```

The response contains both the canonical command in radians and the
target-native command.

Dispatch through the profile:

```http
POST /api/motion/command
Content-Type: application/json
```

The target is selected by the profile's `adapter_mapping_ref`, not by the
source.

## SO101 leader → SO101 follower

The existing in-process LeRobot loop remains unchanged by default.

Enable the compatibility boundary explicitly:

```bash
export LEROBOT_MOTION_PROFILE=MC-SO101-LEADER-SO101-FOLLOWER-V1
python webserver.py
```

The 60 Hz path then becomes:

```text
LeRobot SO101 leader action (degrees)
        ↓
EPAOA profile
        ↓
canonical joint positions (radians)
        ↓
EPAOA profile
        ↓
LeRobot SO101 follower targets (degrees)
        ↓
existing robot action processor
        ↓
SO101 follower
```

This is intentionally opt-in until a physical acceptance run binds and records
the actual leader/follower calibration fingerprints.

For physical SO101 execution, the checked-in profile is a template. After both
devices are connected and their calibrations are verified, the runtime computes
the calibrated degree envelope for every motor using the same LeRobot 0.6.1
normalization semantics. The admitted source range becomes the overlap of the
leader and follower calibrated envelopes. The resolved profile is then bound to
the exact leader/follower calibration SHA-256 fingerprints and receives a new
runtime profile digest before the 60 Hz motion loop starts.

This means a nominal/static viewer range such as ±100 degrees is never used to
reject a physically valid calibrated leader position.

## SO101 leader/source → URDF simulation

Open:

```text
/viewer?source=simulation
```

Send all six source values through:

```json
{
  "profile_id": "MC-SO101-LEADER-URDF-SIM-V1",
  "values": {
    "shoulder_pan": 45,
    "shoulder_lift": -20,
    "elbow_flex": 10,
    "wrist_flex": 5,
    "wrist_roll": 30,
    "gripper": 0
  }
}
```

to `POST /api/motion/command`.

The server stores the resolved simulation target including compatibility ID,
profile digest, canonical command and target-native URDF joint values. The
viewer polls:

```http
GET /api/motion/simulation/state
```

and applies the target-native radians directly to the URDF joints.

The sliders in simulation mode also use this path, making the browser itself a
simple source for testing.

## SO101 leader → Reachy Mini

Reachy Mini is deliberately treated as a different robot morphology. The reference mapping does not pretend that SO101 arm joints and Reachy Mini joints are equivalent.

The profile is:

```text
MC-SO101-LEADER-REACHY-MINI-V1
```

It expects the SO101 source in LeRobot normalized mode:

```text
shoulder_pan   [-100,100] → head yaw    [-60°,60°]
shoulder_lift  [-100,100] → head pitch  [-35°,35°]
elbow_flex     [-100,100] → head Z      [-20mm,20mm]
wrist_flex     [-100,100] → head roll   [-30°,30°]
wrist_roll     [-100,100] → right antenna [-45°,45°]
gripper        [0,100]    → left antenna  [-45°,45°]
```

The canonical schema is provider-defined as
`teleopworks.robot-control.expressive-head.v1`; all angular values are radians and translation is metres.

The target adapter uses the official Reachy Mini SDK `set_target()` method with a 4×4 head pose and the antenna vector. This is suitable for a reactive control loop. Reachy Mini's own daemon remains responsible for its motor-level safety and hardware-specific limits.

### Test first against Reachy Mini MuJoCo

Install the optional SDK:

```bash
pip install reachy-mini
```

Terminal 1 — start the official Reachy Mini simulator/daemon:

```bash
reachy-mini-daemon --sim
```

The Reachy daemon normally listens on localhost port 8000.

Terminal 2 — run Teleopworks on another port:

```bash
cd /home/kwijk/localdata/teleop_lerobot
source .venv/bin/activate
LEROBOT_SIMULATION_ONLY=1 PORT=8010 python webserver.py
```

Then send a neutral normalized SO101 pose:

```bash
curl -s -X POST http://localhost:8010/api/motion/command \
  -H 'Content-Type: application/json' \
  -d '{
    "profile_id": "MC-SO101-LEADER-REACHY-MINI-V1",
    "values": {
      "shoulder_pan": 0,
      "shoulder_lift": 0,
      "elbow_flex": 0,
      "wrist_flex": 0,
      "wrist_roll": 0,
      "gripper": 50
    }
  }' | python -m json.tool
```

Move the virtual Reachy head, for example:

```bash
curl -s -X POST http://localhost:8010/api/motion/command \
  -H 'Content-Type: application/json' \
  -d '{
    "profile_id": "MC-SO101-LEADER-REACHY-MINI-V1",
    "values": {
      "shoulder_pan": 50,
      "shoulder_lift": -30,
      "elbow_flex": 25,
      "wrist_flex": 20,
      "wrist_roll": 40,
      "gripper": 75
    }
  }' | python -m json.tool
```

For a real Reachy Mini Wireless, set `REACHY_MINI_HOST` to its hostname/IP and `REACHY_MINI_CONNECTION_MODE=network`. The mapping profile and API do not change.

### Stream a physical SO101 leader directly to Reachy Mini

Normal leader/follower teleoperation and leader-only source mode cannot own the same serial leader at the same time. Stop the normal teleoperation first.

The leader-only source manager opens the SO101 leader with LeRobot `use_degrees=False`, so body joints are calibration-normalized to `[-100,100]` and the gripper uses `[0,100]`. Those are exactly the source ranges declared by the Reachy profile.

Start Reachy Mini (or its simulator) on port 8000 and Teleopworks on port 8010. Then:

```bash
curl -s -X POST http://localhost:8010/api/motion/source/start \
  -H 'Content-Type: application/json' \
  -d '{
    "profile_id": "MC-SO101-LEADER-REACHY-MINI-V1",
    "port": "/dev/tty_leader",
    "source_id": "black",
    "fps": 50
  }' | python -m json.tool
```

Use the actual leader ID that owns the calibration file on the laptop. The source manager fails closed if the calibration does not match the connected hardware.

Status:

```bash
curl -s http://localhost:8010/api/motion/source/status | python -m json.tool
```

Stop:

```bash
curl -s -X POST http://localhost:8010/api/motion/source/stop | python -m json.tool
```

The live path is therefore:

```text
SO101 leader
  ↓  LeRobot calibration normalization
[-100,100] / gripper [0,100]
  ↓
MC-SO101-LEADER-REACHY-MINI-V1
  ↓
canonical expressive-head SI command
  ↓
pollen.reachy-mini.head-pose.v1
  ↓
Reachy Mini SDK set_target()
  ↓
Reachy daemon
  ↓
MuJoCo or physical Reachy Mini
```

## Quest controller → SO101

The current executable Quest profile is deliberately simple and explicit. It
maps controller channels to absolute joint targets:

| Quest channel | Canonical/target DOF |
|---|---|
| left stick X | shoulder pan |
| left stick Y | shoulder lift |
| right stick Y | elbow flex |
| left trigger | wrist flex |
| right stick X | wrist roll |
| right trigger | gripper |

A Quest client only has to send the six normalized values to
`POST /api/motion/command` with:

```text
MC-QUEST-CONTROLLER-SO101-FOLLOWER-V1
```

This proves that the source does not have to be a LeRobot leader.

It is an interoperability reference, not the recommended human-interface
mapping for production.

### Tracked 6D Quest pose

A tracked controller pose should **not** be forced through the affine joint
mapping above. The correct extension is:

```text
Quest controller pose
(position m + quaternion + frame)
        ↓
canonical Cartesian Robot Control
        ↓
workspace/frame transform
        ↓
kinematics / retargeting provider
        ↓
SO101 joint target
        ↓
local safety
```

That requires a versioned kinematics/retargeting implementation (for example
Pinocchio or another validated IK provider) and its own Motion Compatibility
Profile. The source/target/API architecture does not change.

## Adding another source or target

A new source does not implement follower details. It only produces the
source-native fields declared in a profile.

A new target is selected by `target.adapter_mapping_ref`. The server currently
implements:

- `lerobot.so101-follower.degrees.v1`
- `teleopworks.browser-urdf.v1`
- `pollen.reachy-mini.head-pose.v1`

A Jetson, different robot, MuJoCo/Isaac simulation or another hardware adapter
can be added behind a new adapter mapping without changing existing sources.

Examples:

```text
SO101 leader ─┬─► SO101
              ├─► browser URDF
              ├─► MuJoCo
              └─► Isaac Sim

Quest ────────┬─► SO101
              └─► simulation

AI policy ───────► canonical command ─► any compatible target
```

## Evidence status

The checked-in mappings currently have deterministic CI/reference evidence
(E2). They do **not** claim physical E4 interoperability or production safety.

A physical E4 run should retain at least:

- compatibility/profile ID and SHA-256 digest;
- mapping ID/version/digest;
- leader Capability Profile and calibration fingerprint;
- follower Capability Profile and calibration fingerprint;
- software version;
- canonical command trace;
- resolved target command trace;
- local safety events;
- measured motion/result.

That gives EPAOA a reproducible physical leader → compatibility → follower
acceptance artifact instead of relying on matching LeRobot configuration.
