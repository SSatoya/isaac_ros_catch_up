

検証スペック：
- OS: ubuntu 22.04
- CUDA UMD Version: 13.3 
- KMD Version: 610.57.04

```bash
mkdir-p~/workspaces/isaac_ros-dev/src

echo'export ISAAC_ROS_WS="${ISAAC_ROS_WS:-${HOME}/workspaces/isaac_ros-dev/}"'>>~/.bashrc

source~/.bashrc
```

```bash
./container
```

dokcer内
```bash
sudo isaac-ros init venv
newgrp isaac-ros-cli
```

```bash
isaac-ros activate
```

---

- [Pose Estimation](./docs/pose_estimation.md)