#!/bin/bash

# 1. .envファイルの読み込み
if [ -f .env ]; then
    echo "Loading variables from .env file..."
    export $(grep -v '^#' .env | xargs)
else
    echo "Warning: .env file not found. Using default values."
    IMAGE_NAME="isaac-ros-4.6-base"
    CONTAINER_NAME="isaac-ros-dev"
    ROS_DOMAIN_ID=0
fi

# 2. ISAAC_ROS_WSの確認
if [ -z "${ISAAC_ROS_WS}" ]; then
    echo "ERROR: Please set ISAAC_ROS_WS environment variable to the path of your Isaac ROS workspace."
    exit 1
fi

# 3. Dockerイメージのビルド
if ! docker image inspect ${IMAGE_NAME} > /dev/null 2>&1; then
    echo "Docker image '${IMAGE_NAME}' not found. Building the image..."
    docker build -t ${IMAGE_NAME} .
else
    echo "Docker image '${IMAGE_NAME}' already exists."
fi

# 4. コンテナの起動
docker run -it \
    --name ${CONTAINER_NAME} \
    --gpus all \
    --network host \
    --ipc host \
    -e DISPLAY=$DISPLAY \
    -e NVIDIA_DRIVER_CAPABILITIES=all \
    -e NVIDIA_VISIBLE_DEVICES=all \
    -e ROS_DOMAIN_ID=${ROS_DOMAIN_ID} \
    -e ISAAC_ROS_WS=/workspaces/isaac_ros-dev \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v ${ISAAC_ROS_WS}/../dds_cfg:/workspaces/dds_cfg \
    -v ${ISAAC_ROS_WS}:/workspaces/isaac_ros-dev \
    ${IMAGE_NAME}