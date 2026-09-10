# EPAOA Motion Compatibility reference implementation

This repository contains an executable implementation of the EPAOA Motion Compatibility Profile introduced in the European Physical AI Operations Architecture.

The implementation keeps source devices, canonical Robot Control semantics and target devices separate:

```text
source native                 canonical EPAOA                    target native
─────────────                 ───────────────                    ─────────────
SO101 leader (deg) ────────► joint position (rad) ────────────► SO101 follower (deg)
                         └──► joint position (rad) ────────────► URDF simulation (rad)

Quest controls (0..1/-1..1) ► joint position (rad) ────────────► SO101 follower (deg)
```

Equal array lengths or equal motor names are never treated as proof of compatibility.

## Files

- `motion_compatibility.py` — dependency-free profile registry, validation, conversion and simulation state.
- `motion_profiles/so101-leader-to-so101-follower.json` — SO101 physical reference mapping.
- `motion_profiles/so101-leader-to-urdf-simulation.json` — same source mapped to the browser URDF target.
- `motion_profiles/quest-controller-to-so101-follower.json` — reference mapping from normalized Quest controller channels to SO101 joints.
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
the actual leader/follower calibration fingerprints and verifies the declared
operating ranges.

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
