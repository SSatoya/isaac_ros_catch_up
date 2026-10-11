#!/usr/bin/env python3

"""
Head Camera -> RT-DETR -> FoundationPose

入力:
    /head_camera/color/image_raw
    /head_camera/color/camera_info
    /head_camera/aligned_depth_to_color/image_raw

出力:
    /pose_estimation/output

処理概要:

    RGB + Depth + CameraInfo
                |
                v
        NitrosCameraDropNode
        (ExactTime同期)
                |
                +--------------------+
                |                    |
                v                    v
          RT-DETR前処理          Depth
                |
                v
             RT-DETR
                |
                v
        Detection2D -> Mask
                |
                v
          Mask Resize
                |
                +---------+
                          |
                          v
                    FoundationPose
                          |
                          v
                    6DoF Pose
"""


import launch
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode


# ============================================================
# 固定設定
# ============================================================

# Head Cameraの入力解像度
INPUT_WIDTH = 1280
INPUT_HEIGHT = 720

# RT-DETRの入力解像度
RT_DETR_WIDTH = 640
RT_DETR_HEIGHT = 640

# 1280x720 -> 640x360 にResizeした後、
# RT-DETR用に640x640へPadする。
INPUT_TO_RT_DETR_RATIO = INPUT_WIDTH / RT_DETR_WIDTH


def generate_launch_description():

    # ========================================================
    # Launch Arguments
    # ========================================================

    # FoundationPoseで使用する物体メッシュ
    #
    # 現在はIsaac ROSのサンプルMustard meshをデフォルトにしている。
    # 実際の対象物を使う場合は、
    # --mesh_file_path:=/path/to/object.obj
    # で変更する。
    mesh_file_path = LaunchConfiguration('mesh_file_path')

    # FoundationPose Refine TensorRT engine
    refine_engine_file_path = LaunchConfiguration(
        'refine_engine_file_path'
    )

    # FoundationPose Score TensorRT engine
    score_engine_file_path = LaunchConfiguration(
        'score_engine_file_path'
    )

    # RT-DETR TensorRT engine
    rt_detr_engine_file_path = LaunchConfiguration(
        'rt_detr_engine_file_path'
    )


    # ========================================================
    # 1. NitrosCameraDropNode
    # ========================================================
    #
    # RGB、CameraInfo、Depthの3つをExactTimeで同期する。
    #
    # 今回は既に、
    #
    #   RGB timestamp
    #   Depth timestamp
    #   CameraInfo timestamp
    #
    # が完全一致することを確認済みである。
    #
    # また、Depthは実カメラ側が32FC1であり、
    # CameraDropNodeを単体で動作させて
    #
    #   32FC1 -> NitrosCameraDropNode -> 32FC1
    #
    # が成立することも確認済みである。
    #
    # 最初の動作確認ではフレームdropを行わず、
    # X=0, Y=1として全フレームを通す。
    #
    # 本番では例えば X=28, Y=30 として
    # 約30 Hzへdropすることも可能。
    #
    drop_node = ComposableNode(
        name='camera_drop',
        package='isaac_ros_nitros_topic_tools',
        plugin=(
            'nvidia::isaac_ros::nitros::NitrosCameraDropNode'
        ),
        parameters=[{
            # X out of Y messages are dropped.
            # 今回は全フレームを通す。
            'X': 0,
            'Y': 1,

            # RGB + CameraInfo + Depthを同期するモード。
            'mode': 'mono+depth',

            # Depthは32FC1。
            #
            # 実際にCameraDropNode単体で
            # 32FC1を通過できることを確認済み。
            'depth_format_string': 'nitros_image_32FC1',
        }],
        remappings=[
            # ----------------------------
            # Input
            # ----------------------------

            # RGB
            ('image_1',
             '/head_camera/color/image_raw'),

            # CameraInfo
            ('camera_info_1',
             '/head_camera/color/camera_info'),

            # Depth
            ('depth_1',
             '/head_camera/aligned_depth_to_color/image_raw'),

            # ----------------------------
            # Output
            # ----------------------------

            # RGB
            ('image_1_drop',
             'rgb/image_rect_color'),

            # CameraInfo
            ('camera_info_1_drop',
             'rgb/camera_info'),

            # Depth
            ('depth_1_drop',
             'depth_image'),
        ],
    )


    # ========================================================
    # 2. RGB Resize
    # ========================================================
    #
    # 元画像:
    #
    #     1280 x 720
    #
    # をRT-DETRの入力サイズに合わせる。
    #
    # keep_aspect_ratio=Trueなので、
    #
    #     1280 x 720
    #          |
    #          v
    #      640 x 360
    #
    # となる。
    #
    # その後、PadNodeで640x640にする。
    #
    resize_rgb_node = ComposableNode(
        name='resize_rgb',
        package='isaac_ros_image_proc',
        plugin='nvidia::isaac_ros::image_proc::ResizeNode',
        parameters=[{
            'input_width': INPUT_WIDTH,
            'input_height': INPUT_HEIGHT,

            'output_width': RT_DETR_WIDTH,
            'output_height': RT_DETR_HEIGHT,

            'keep_aspect_ratio': True,

            # RT-DETRへ入力するRGB形式
            'encoding_desired': 'rgb8',

            # アスペクト比維持後の画像をそのまま出力する。
            # paddingは次のPadNodeで行う。
            'disable_padding': True,
        }],
        remappings=[
            ('image',
             'rgb/image_rect_color'),

            ('camera_info',
             'rgb/camera_info'),

            ('resize/image',
             'color_image_resized'),

            ('resize/camera_info',
             'camera_info_resized'),
        ],
    )


    # ========================================================
    # 3. RGB Padding
    # ========================================================
    #
    # Resize後:
    #
    #     640 x 360
    #
    # RT-DETRは640x640を要求するため、
    # 右下方向にpaddingを追加する。
    #
    #     640 x 360
    #          |
    #          v
    #     640 x 640
    #
    pad_node = ComposableNode(
        name='pad_rgb',
        package='isaac_ros_image_proc',
        plugin='nvidia::isaac_ros::image_proc::PadNode',
        parameters=[{
            'output_image_width': RT_DETR_WIDTH,
            'output_image_height': RT_DETR_HEIGHT,

            # 右下方向にpaddingする。
            'padding_type': 'BOTTOM_RIGHT',
        }],
        remappings=[
            ('image',
             'color_image_resized'),

            ('padded_image',
             'padded_image'),
        ],
    )


    # ========================================================
    # 4. ImageToTensor
    # ========================================================
    #
    # RGB画像をTensorへ変換する。
    #
    # ここではscale=Falseとしており、
    # ImageToTensorによる画素値のスケーリングを行わない。
    #
    # 出力:
    #
    #     normalized_tensor
    #
    image_to_tensor_node = ComposableNode(
        name='image_to_tensor',
        package='isaac_ros_tensor_proc',
        plugin=(
            'nvidia::isaac_ros::dnn_inference::'
            'ImageToTensorNode'
        ),
        parameters=[{
            'scale': False,
            'tensor_name': 'image',
        }],
        remappings=[
            ('image',
             'padded_image'),

            ('tensor',
             'normalized_tensor'),
        ],
    )


    # ========================================================
    # 5. Interleaved -> Planar
    # ========================================================
    #
    # RGB画像のTensor形式を、
    #
    #     H x W x C
    #
    # から
    #
    #     C x H x W
    #
    # に変換する。
    #
    # RT-DETR TensorRT engineへ入力するための
    # Tensor形式を整える処理である。
    #
    interleaved_to_planar_node = ComposableNode(
        name='interleaved_to_planar',
        package='isaac_ros_tensor_proc',
        plugin=(
            'nvidia::isaac_ros::dnn_inference::'
            'InterleavedToPlanarNode'
        ),
        parameters=[{
            'input_tensor_shape': [
                RT_DETR_WIDTH,
                RT_DETR_HEIGHT,
                3,
            ],
        }],
        remappings=[
            ('interleaved_tensor',
             'normalized_tensor'),

            ('planar_tensor',
             'planar_tensor'),
        ],
    )


    # ========================================================
    # 6. Reshape
    # ========================================================
    #
    # TensorをRT-DETR TensorRT engineが要求する
    # 4次元Tensorへ変形する。
    #
    #     [3, 640, 640]
    #
    #         ->
    #
    #     [1, 3, 640, 640]
    #
    reshape_node = ComposableNode(
        name='reshape',
        package='isaac_ros_tensor_proc',
        plugin=(
            'nvidia::isaac_ros::dnn_inference::'
            'ReshapeNode'
        ),
        parameters=[{
            'output_tensor_name': 'input_tensor',

            'input_tensor_shape': [
                3,
                RT_DETR_HEIGHT,
                RT_DETR_WIDTH,
            ],

            'output_tensor_shape': [
                1,
                3,
                RT_DETR_HEIGHT,
                RT_DETR_WIDTH,
            ],
        }],
        remappings=[
            ('tensor',
             'planar_tensor'),

            ('reshaped_tensor',
             'reshaped_tensor'),
        ],
    )


    # ========================================================
    # 7. RT-DETR Preprocessor
    # ========================================================
    #
    # RT-DETR TensorRT engineへ入力するための
    # 前処理を行う。
    #
    # TensorRTへ渡すTensorは
    #
    #     images
    #     orig_target_sizes
    #
    # となる。
    #
    rtdetr_preprocessor_node = ComposableNode(
        name='rtdetr_preprocessor',
        package='isaac_ros_rtdetr',
        plugin=(
            'nvidia::isaac_ros::rtdetr::'
            'RtDetrPreprocessorNode'
        ),
        remappings=[
            ('encoded_tensor',
             'reshaped_tensor'),
        ],
    )


    # ========================================================
    # 8. RT-DETR TensorRT
    # ========================================================
    #
    # RT-DETRによる物体検出を行う。
    #
    # 今回使用するengine:
    #
    # /workspaces/isaac_ros-dev/
    #   isaac_ros_assets/models/synthetica_detr/
    #   sdetr_grasp.plan
    #
    # 出力:
    #
    #     labels
    #     boxes
    #     scores
    #
    tensor_rt_node = ComposableNode(
        name='rtdetr_tensor_rt',
        package='isaac_ros_tensor_rt',
        plugin=(
            'nvidia::isaac_ros::dnn_inference::'
            'TensorRTNode'
        ),
        parameters=[{
            'engine_file_path':
                rt_detr_engine_file_path,

            'output_binding_names': [
                'labels',
                'boxes',
                'scores',
            ],

            'output_tensor_names': [
                'labels',
                'boxes',
                'scores',
            ],

            'input_tensor_names': [
                'images',
                'orig_target_sizes',
            ],

            'input_binding_names': [
                'images',
                'orig_target_sizes',
            ],

            'force_engine_update': False,
        }],
    )


    # ========================================================
    # 9. RT-DETR Decoder
    # ========================================================
    #
    # TensorRTから出力された
    #
    #     labels
    #     boxes
    #     scores
    #
    # をROSのDetection2DArrayへ変換する。
    #
    rtdetr_decoder_node = ComposableNode(
        name='rtdetr_decoder',
        package='isaac_ros_rtdetr',
        plugin=(
            'nvidia::isaac_ros::rtdetr::'
            'RtDetrDecoderNode'
        ),
    )


    # ========================================================
    # 10. Detection2DArray Filter
    # ========================================================
    #
    # RT-DETRが検出した複数の物体から、
    # FoundationPoseへ渡す対象を選択する。
    #
    # FoundationPoseの標準core launchと同じ
    # Detection2DArrayFilterを使用する。
    #
    detection2d_array_filter_node = ComposableNode(
        name='detection2d_array_filter',
        package='isaac_ros_foundationpose',
        plugin=(
            'nvidia::isaac_ros::foundationpose::'
            'Detection2DArrayFilter'
        ),
        remappings=[
            ('detection2_d_array',
            'detections_output'),
        ],
    )


    # ========================================================
    # 11. Detection2D -> Segmentation Mask
    # ========================================================
    #
    # RT-DETRのBounding Boxから、
    # FoundationPoseが使用する2D segmentation maskを生成する。
    #
    # 元画像が1280x720であり、
    # RT-DETR処理時の縮小率が2なので、
    #
    #     mask = 640 x 360
    #
    # とする。
    #
    detection2d_to_mask_node = ComposableNode(
        name='detection2d_to_mask',
        package='isaac_ros_foundationpose',
        plugin=(
            'nvidia::isaac_ros::foundationpose::'
            'Detection2DToMask'
        ),
        parameters=[{
            'mask_width':
                int(INPUT_WIDTH / INPUT_TO_RT_DETR_RATIO),

            'mask_height':
                int(INPUT_HEIGHT / INPUT_TO_RT_DETR_RATIO),
        }],
        remappings=[
            ('segmentation',
            'rt_detr_segmentation'),
        ],
    )


    # ========================================================
    # 12. Segmentation Mask Resize
    # ========================================================
    #
    # RT-DETR由来の640x360 maskを、
    # FoundationPoseが使用する元画像サイズ
    #
    #     1280 x 720
    #
    # へ戻す。
    #
    resize_mask_node = ComposableNode(
        name='resize_mask',
        package='isaac_ros_image_proc',
        plugin='nvidia::isaac_ros::image_proc::ResizeNode',
        parameters=[{
            'input_width':
                int(INPUT_WIDTH / INPUT_TO_RT_DETR_RATIO),

            'input_height':
                int(INPUT_HEIGHT / INPUT_TO_RT_DETR_RATIO),

            'output_width':
                INPUT_WIDTH,

            'output_height':
                INPUT_HEIGHT,

            # Maskは元画像と同じサイズに戻す。
            'keep_aspect_ratio': False,

            'disable_padding': False,
        }],
        remappings=[
            ('image',
             'rt_detr_segmentation'),

            ('camera_info',
             'camera_info_resized'),

            ('resize/image',
             'segmentation'),

            ('resize/camera_info',
             'camera_info_segmentation'),
        ],
    )


    # ========================================================
    # 13. FoundationPose Refine TensorRT
    # ========================================================
    #
    # FoundationPoseのRefine networkをTensorRTで実行する。
    #
    # 使用engine:
    #
    # /workspaces/isaac_ros-dev/
    #   isaac_ros_assets/models/foundationpose/
    #   refine_trt_engine.plan
    #
    # FoundationPose本体から生成されたTensorを
    # TensorRT engineへ入力する。
    #
    refine_trt_node = ComposableNode(
        name='refine_trt',
        package='isaac_ros_tensor_rt',
        plugin=(
            'nvidia::isaac_ros::dnn_inference::'
            'TensorRTNode'
        ),
        parameters=[{
            'engine_file_path':
                refine_engine_file_path,

            'input_tensor_names': [
                'input_tensor1',
                'input_tensor2',
            ],

            'input_binding_names': [
                'input1',
                'input2',
            ],

            'output_tensor_names': [
                'output_tensor1',
                'output_tensor2',
            ],

            'output_binding_names': [
                'output1',
                'output2',
            ],

            'force_engine_update': False,

            'verbose': False,

            # FoundationPose core launchと同じ値。
            'max_batch_size': 42,
        }],
        remappings=[
            ('tensor_pub',
             'refine/tensor_pub'),

            ('tensor_sub',
             'refine/tensor_sub'),
        ],
    )


    # ========================================================
    # 14. FoundationPose Score TensorRT
    # ========================================================
    #
    # FoundationPoseのScore networkをTensorRTで実行する。
    #
    # 使用engine:
    #
    # /workspaces/isaac_ros-dev/
    #   isaac_ros_assets/models/foundationpose/
    #   score_trt_engine.plan
    #
    score_trt_node = ComposableNode(
        name='score_trt',
        package='isaac_ros_tensor_rt',
        plugin=(
            'nvidia::isaac_ros::dnn_inference::'
            'TensorRTNode'
        ),
        parameters=[{
            'engine_file_path':
                score_engine_file_path,

            'input_tensor_names': [
                'input_tensor1',
                'input_tensor2',
            ],

            'input_binding_names': [
                'input1',
                'input2',
            ],

            'output_tensor_names': [
                'output_tensor',
            ],

            'output_binding_names': [
                'output1',
            ],

            'force_engine_update': False,

            'verbose': False,

            # FoundationPose core launchと同じ値。
            'max_batch_size': 252,
        }],
        remappings=[
            ('tensor_pub',
             'score/tensor_pub'),

            ('tensor_sub',
             'score/tensor_sub'),
        ],
    )


    # ========================================================
    # 15. FoundationPose
    # ========================================================
    #
    # FoundationPose本体。
    #
    # 入力:
    #
    #   RGB
    #   Depth
    #   CameraInfo
    #   Segmentation Mask
    #
    # を利用して、対象物の6DoF姿勢を推定する。
    #
    # FoundationPoseでは、
    #
    #   Refine TensorRT
    #   Score TensorRT
    #
    # も利用する。
    #
    foundationpose_node = ComposableNode(
        name='foundationpose',
        package='isaac_ros_foundationpose',
        plugin=(
            'nvidia::isaac_ros::foundationpose::'
            'FoundationPoseNode'
        ),
        parameters=[{
            # 対象物の3D mesh。
            #
            # 現在はLaunch Argumentから指定する。
            'mesh_file_path':
                mesh_file_path,

            # Refine networkへの入力Tensor名
            'refine_input_tensor_names': [
                'input_tensor1',
                'input_tensor2',
            ],

            # Score networkへの入力Tensor名
            'score_input_tensor_names': [
                'input_tensor1',
                'input_tensor2',
            ],
        }],
        remappings=[
            # Depth
            ('pose_estimation/depth_image',
             'depth_image'),

            # RGB
            ('pose_estimation/image',
             'rgb/image_rect_color'),

            # CameraInfo
            ('pose_estimation/camera_info',
             'rgb/camera_info'),

            # Segmentation mask
            ('pose_estimation/segmentation',
             'segmentation'),

            # 6DoF pose output
            ('pose_estimation/output',
             '/pose_estimation/output'),
        ],
    )


    # ========================================================
    # ComposableNodeContainer
    # ========================================================
    #
    # ここまでで定義した全ComposableNodeを、
    # 1つのMulti-Threaded Component Container上で実行する。
    #
    # component_container_mtを使用することで、
    # 複数のノードを並列実行できる。
    #
    foundationpose_container = ComposableNodeContainer(
        package='rclcpp_components',
        name='head_camera_foundationpose_container',
        namespace='',
        executable='component_container_mt',

        composable_node_descriptions=[
            # Camera input
            drop_node,

            # RT-DETR preprocessing
            resize_rgb_node,
            pad_node,
            image_to_tensor_node,
            interleaved_to_planar_node,
            reshape_node,

            # RT-DETR
            rtdetr_preprocessor_node,
            tensor_rt_node,
            rtdetr_decoder_node,

            # Detection -> Mask
            detection2d_array_filter_node,
            detection2d_to_mask_node,
            resize_mask_node,

            # FoundationPose networks
            refine_trt_node,
            score_trt_node,

            # FoundationPose
            foundationpose_node,
        ],

        output='screen',
    )


    # ========================================================
    # Launch Description
    # ========================================================

    return LaunchDescription([

        # ----------------------------------------------------
        # Mesh
        # ----------------------------------------------------
        DeclareLaunchArgument(
            'mesh_file_path',
            default_value=(
                '/workspaces/isaac_ros-dev/'
                'isaac_ros_assets/isaac_ros_foundationpose/'
                'Mustard/textured_simple.obj'
            ),
            description=(
                'Path to the 3D mesh used by FoundationPose.'
            ),
        ),

        # ----------------------------------------------------
        # FoundationPose Refine engine
        # ----------------------------------------------------
        DeclareLaunchArgument(
            'refine_engine_file_path',
            default_value=(
                '/workspaces/isaac_ros-dev/'
                'isaac_ros_assets/models/foundationpose/'
                'refine_trt_engine.plan'
            ),
            description=(
                'Path to FoundationPose refine TensorRT engine.'
            ),
        ),

        # ----------------------------------------------------
        # FoundationPose Score engine
        # ----------------------------------------------------
        DeclareLaunchArgument(
            'score_engine_file_path',
            default_value=(
                '/workspaces/isaac_ros-dev/'
                'isaac_ros_assets/models/foundationpose/'
                'score_trt_engine.plan'
            ),
            description=(
                'Path to FoundationPose score TensorRT engine.'
            ),
        ),

        # ----------------------------------------------------
        # RT-DETR engine
        # ----------------------------------------------------
        DeclareLaunchArgument(
            'rt_detr_engine_file_path',
            default_value=(
                '/workspaces/isaac_ros-dev/'
                'isaac_ros_assets/models/synthetica_detr/'
                'sdetr_grasp.plan'
            ),
            description=(
                'Path to RT-DETR TensorRT engine.'
            ),
        ),

        # ----------------------------------------------------
        # Container
        # ----------------------------------------------------
        foundationpose_container,
    ])