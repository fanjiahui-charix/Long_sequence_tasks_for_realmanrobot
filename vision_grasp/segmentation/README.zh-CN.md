# 视觉抓取分割模块
[English](./README.md) | [简体中文](./README.zh-CN.md)

`vision_grasp/segmentation/` 是 FoundationPose 前面的神经网络分割层。

它的职责很直接：

- 读取当前 RGB 图像
- 跑 YOLO-seg
- 生成干净的 `mask.png`
- 把这个 mask 交给 FoundationPose

如果你后面想做这些事，优先来看这个目录：

- 更换分割模型
- 训练自己的眼镜盒分割模型
- 排查为什么生成的 mask 不对

## 主要文件

- `run_yolo_seg_mask.py`
  单帧分割推理脚本
- `train_yolo_seg.py`
  自定义 YOLO-seg 训练入口
- `datasets/glasses_case_box_seg_example.yaml`
  眼镜盒自定义类别的数据集配置示例

## 当前机器人推荐模型

针对你现在这台 Jetson Xavier NX，当前推荐的官方轻量基线模型是：

- `yolov8n-seg.pt`

原因是你远程机器人已经具备：

- `/usr/bin/python3`
- `ultralytics==8.2.103`
- `torch 2.1.0a0+41361538.nv23.06`
- CUDA 可用

注意：

- `yolov8n-seg.pt` 适合先验证代码链和运行兼容性
- 它**不认识**你自己的 `glasses_case_box` 类别
- 如果你要稳定抓取眼镜盒，后面还是应该训练你自己的 YOLO-seg `best.pt`

## 单独分割命令

```bash
/usr/bin/python3 /home/rm/Long_sequence_tasks/vision_grasp/segmentation/run_yolo_seg_mask.py \
  --rgb /home/rm/Long_sequence_tasks/vision_grasp/runtime/<run_id>/capture/rgb.png \
  --output-mask /tmp/yolo_seg_mask.png \
  --output-vis /tmp/yolo_seg_mask_vis.png \
  --output-json /tmp/yolo_seg_result.json \
  --weights /home/rm/yolov8n-seg.pt \
  --label person
```

输出包括：

- 二值 `mask.png`
- 带实例高亮的可视化图
- 调试用 JSON 元数据

## 接入抓取 pipeline 的命令

```bash
source /home/rm/miniforge3/bin/activate foundationpose

python3 /home/rm/Long_sequence_tasks/vision_grasp/integration/run_pose_grasp_pipeline.py \
  --camera-name camera_middle \
  --camera-frame camera_middle \
  --mesh /home/rm/Long_sequence_tasks/vision_grasp/object_models/glasses_case_box/glasses_case_box.obj \
  --object-label glasses_case_box \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/glasses_case_box_grasp.yaml \
  --mask-backend yolo-seg \
  --seg-weights /home/rm/yolov8n-seg.pt \
  --seg-label glasses_case_box \
  --mask
```

## 数据集目录结构

训练你自己的分割模型时，建议按这个结构准备数据：

```text
vision_grasp/segmentation/datasets/glasses_case_box/
  images/
    train/
    val/
  labels/
    train/
    val/
```

说明：

- 标注格式需要符合 Ultralytics YOLO-seg polygon 格式
- 类别 id `0` 对应 `glasses_case_box`
- 可以直接复制并修改示例 YAML 文件

## 训练命令

```bash
/usr/bin/python3 /home/rm/Long_sequence_tasks/vision_grasp/segmentation/train_yolo_seg.py \
  --data /home/rm/Long_sequence_tasks/vision_grasp/segmentation/datasets/glasses_case_box_seg_example.yaml \
  --model /home/rm/yolov8n-seg.pt \
  --epochs 100 \
  --imgsz 640 \
  --batch 8 \
  --device 0 \
  --name glasses_case_box_seg
```

默认训练输出目录是：

- `vision_grasp/weights/yolo_seg_runs/`

这个目录已经被 Git 忽略，不会被推到 GitHub。

## 训练完成以后

训练好以后，正常使用路径就是：

1. 找到产出的 `best.pt`
2. 把 `--seg-weights` 指向这个文件
3. 设置 `--seg-label glasses_case_box`
4. 重新运行视觉抓取 pipeline

