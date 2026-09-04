# 🤖 SO-101 Robot 3D Viewers

Two high-quality 3D visualization options for the SO-101 robot arm.

## 🎯 Viewers

### 1. `/viewer` - **URDF-Based Viewer** (Bambot Quality) ⭐
**Recommended for realistic visualization**

- ✅ Uses actual URDF robot description
- ✅ Real CAD meshes (STL files)
- ✅ Physically accurate geometry
- ✅ Professional rendering quality
- ✅ Matches bambot implementation

**Features:**
- Real-time joint control with sliders
- WebSocket live updates from robot
- Sync with physical robot
- Reset to home position
- Random pose generation
- Smooth animations
- Professional lighting & shadows

**Tech Stack:**
- Three.js r160
- urdf-loader for URDF parsing
- ES6 modules
- Modern WebGL rendering

### 2. `/simulator` - **Simple Geometric Viewer**
**Lightweight alternative**

- Simple geometric shapes
- Fast loading
- No external dependencies
- Good for basic visualization

## 🚀 Quick Start

1. **Start the webserver:**
```bash
./webserver.py
```

2. **Open the URDF viewer:**
```
http://localhost/viewer
```

Or from another device:
```
http://<raspberry-pi-ip>/viewer
```

## 🎮 Controls

**Mouse:**
- **Left-click + drag**: Orbit camera around robot
- **Right-click + drag**: Pan camera
- **Scroll wheel**: Zoom in/out

**Sidebar:**
- **Joint sliders**: Move individual joints (0-360°)
- **Reset to Home**: Return all joints to 180° (neutral position)
- **Sync with Robot**: Fetch current positions from physical robot
- **Random Pose**: Generate random joint angles

## 📁 File Structure

```
teleop_lerobot/
├── templates/
│   ├── robot_viewer.html      # URDF-based viewer (bambot quality)
│   └── robot_simulator.html   # Simple geometric viewer
├── static/
│   ├── URDFs/                 # Symlink to bambot URDF files
│   │   ├── so101.urdf         # Robot description
│   │   └── assets/            # STL mesh files
│   └── so101.urdf             # Standalone copy
└── webserver.py               # FastAPI server
```

## 🔧 Technical Details

### URDF Viewer Implementation

**Robot Configuration** (matching bambot):
```javascript
{
    'Rotation': { id: 1, min: 0, max: 360, initial: 180 },    // Base rotation
    'Pitch': { id: 2, min: 0, max: 360, initial: 180 },       // Shoulder pitch
    'Elbow': { id: 3, min: 0, max: 360, initial: 180 },       // Elbow flex
    'Wrist_Pitch': { id: 4, min: 0, max: 360, initial: 180 }, // Wrist pitch
    'Wrist_Roll': { id: 5, min: 0, max: 360, initial: 180 },  // Wrist roll
    'Jaw': { id: 6, min: 0, max: 360, initial: 180 }          // Gripper
}
```

**Camera Setup:**
- Position: [-30, 10, 30]
- FOV: 12°
- Orbit target: [1, 2, 0]
- Scale: 15x

**Lighting:**
- Ambient: 0.4 intensity
- 2x Directional lights with shadows
- 1024x1024 shadow maps
- PCF soft shadows

### API Endpoints

**Get robot positions:**
```
GET /api/robot/positions
```
Returns current joint angles from physical robot.

**WebSocket updates:**
```
ws://localhost/ws
```
Real-time position updates when robot moves.

## 🎨 Comparison: Viewer vs Simulator

| Feature | URDF Viewer | Simple Simulator |
|---------|-------------|------------------|
| **Visual Quality** | ⭐⭐⭐⭐⭐ Professional | ⭐⭐⭐ Good |
| **Accuracy** | ⭐⭐⭐⭐⭐ CAD-accurate | ⭐⭐⭐ Approximate |
| **Load Time** | ⭐⭐⭐ ~2-3s | ⭐⭐⭐⭐⭐ Instant |
| **File Size** | ~15 MB (meshes) | < 100 KB |
| **Dependencies** | urdf-loader | None |
| **Use Case** | Production, demos | Development, testing |

## 🔌 Integration with Blockly

The viewer can be used to:
1. **Monitor** Blockly program execution
2. **Debug** joint movements visually
3. **Preview** programs before running on hardware
4. **Record** demonstrations for training

### Example: Live Updates During Blockly Execution

When a Blockly program runs, the viewer can show real-time updates:

```javascript
// In webserver.py - broadcast robot state via WebSocket
await state.broadcast_status({
    "type": "robot_update",
    "positions": [45, 90, 135, 180, 225, 270]
});
```

The viewer will automatically animate to these positions.

## 🐛 Troubleshooting

### Viewer shows "Load Error"
- Check that `/static/URDFs/` symlink exists
- Verify URDF file is accessible: `ls -la static/URDFs/so101.urdf`
- Check browser console for specific error

### STL meshes not loading
- Ensure symlink points to correct location:
  ```bash
  ls -la static/URDFs/assets/*.stl
  ```
- Verify webserver has read permissions

### Joint movements not smooth
- Check browser performance (GPU acceleration enabled?)
- Reduce shadow quality in code if needed
- Close other browser tabs

### WebSocket not connecting
- Verify webserver is running
- Check firewall settings
- Confirm correct IP/port

## 📚 References

- **Bambot Project**: https://github.com/yourusername/bambot
- **urdf-loader**: https://github.com/gkjohnson/urdf-loader
- **Three.js**: https://threejs.org/
- **URDF Specification**: http://wiki.ros.org/urdf

## 🎯 Future Enhancements

Potential improvements:
- [ ] Inverse kinematics (click to move end-effector)
- [ ] Trajectory playback from recordings
- [ ] Collision detection visualization
- [ ] VR/AR support
- [ ] Multi-robot scenes
- [ ] Export to glTF format
- [ ] Custom camera presets
- [ ] Screenshot/video recording

## 📝 Notes

- Initial joint angles are set to 180° (neutral position)
- Joint limits come from URDF file (usually 0-360°)
- Scale factor of 15x matches bambot visualization
- Coordinate system: X=forward, Y=up, Z=right (ROS convention)
