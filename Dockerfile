FROM ubuntu:24.04

ENV ROS_DISTRO=jazzy
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Tokyo
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV PATH="/usr/local/nvidia/bin:/usr/local/cuda/bin:/usr/src/tensorrt/bin:${PATH}"

# 1. 必須ツールのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    locales \
    curl \
    gnupg \
    gnupg2 \
    lsb-release \
    software-properties-common \
    build-essential \
    git \
    wget \
    sudo \
    python3-pip \
    x11-apps \
    vim \
    && locale-gen en_US en_US.UTF-8 \
    && update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# CUDA aptリポジトリの設定
RUN wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb \
    && dpkg -i cuda-keyring_1.1-1_all.deb \
    && rm cuda-keyring_1.1-1_all.deb

# Jetson aptリポジトリの設定
RUN curl -fsSL https://repo.download.nvidia.com/jetson/jetson-ota-public.asc | gpg --dearmor | tee /etc/apt/keyrings/nvidia-jetson.gpg > /dev/null \
    && echo 'deb [signed-by=/etc/apt/keyrings/nvidia-jetson.gpg] https://repo.download.nvidia.com/jetson/x86_64/noble r39.2 main' | tee /etc/apt/sources.list.d/nvidia-jetson-apt-source.list

# ROS 2 Jazzy リポジトリの追加
RUN add-apt-repository universe \
    && curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu noble main" | tee /etc/apt/sources.list.d/ros2.list > /dev/null

# ROS 2 と開発ツールのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-jazzy-desktop \
    ros-${ROS_DISTRO}-rmw-cyclonedds-cpp \
    ros-${ROS_DISTRO}-teleop-twist-keyboard \
    ros-${ROS_DISTRO}-rqt-* \
    python3-colcon-common-extensions \
    python3-rosdep \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 競合するOpenCVの削除
RUN apt-get update && apt-get remove -y libopencv* opencv* || true

# Isaac ROS rosdep定義の初期化
RUN rosdep init \
    && mkdir -p /etc/ros/rosdep/sources.list.d \
    && curl -o /etc/ros/rosdep/sources.list.d/nvidia-isaac.yaml https://raw.githubusercontent.com/NVIDIA-ISAAC-ROS/isaac-ros-cli/release-4.6/docker/rosdep/extra_rosdeps.yaml \
    && echo "yaml file:///etc/ros/rosdep/sources.list.d/nvidia-isaac.yaml" | tee /etc/ros/rosdep/sources.list.d/00-nvidia-isaac.list \
    && rosdep update

# Isaac ROS CLI のインストール
RUN curl -fsSL https://isaac.download.nvidia.com/isaac-ros/repos.key | gpg --dearmor -o /usr/share/keyrings/nvidia-isaac-ros.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/nvidia-isaac-ros.gpg] https://isaac.download.nvidia.com/isaac-ros/release-4.6 noble main" | tee /etc/apt/sources.list.d/nvidia-isaac-ros.list > /dev/null \
    && apt-get update \
    && apt-get install -y isaac-ros-cli \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# .bashrc への環境変数の書き込み
RUN echo 'export PATH="/usr/local/nvidia/bin:/usr/local/cuda/bin:/usr/src/tensorrt/bin:${PATH}"' >> /root/.bashrc \
    && echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc \
    && echo "source /usr/share/colcon_argcomplete/hook/colcon-argcomplete.bash" >> /root/.bashrc \
    && echo "export RMW_IMPLEMENTATION=rmw_fastrtps_cpp" >> /root/.bashrc \
    && echo "export FASTRTPS_DEFAULT_PROFILES_FILE=/workspaces/dds_cfg/fastdds.xml" >> /root/.bashrc

WORKDIR /workspaces/isaac_ros-dev
CMD ["bash"]