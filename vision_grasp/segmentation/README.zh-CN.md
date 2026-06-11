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

## 目录说明

- `run_yolo_seg_mask.py`
  单帧分割推理脚本
- `train_yolo_seg.py`
  自定义 YOLO-seg 训练入口
- `capture_seg_dataset.py`
  交互式 RGB-D 数据采集脚本，支持按键抓图和录视频
- `datasets/glasses_case_box_seg_example.yaml`
  眼镜盒数据集配置模板
- `README.md`
  英文说明
- `README.zh-CN.md`
  中文说明

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

## 一条主线先看懂

你后面真正要跑通的是这条链：

1. 采一帧 RGB-D
2. 用 YOLO-seg 生成 `mask.png`
3. 把 `mask.png` 交给 FoundationPose
4. FoundationPose 输出 `pose.json`
5. 抓取模块根据 `pose.json` 执行机械臂抓取

所以这个目录本质上只负责第 2 步：

- `RGB -> mask.png`

## 第一步：先单独验证分割推理

如果你已经有一张 RGB 图，先不要一上来就整条抓取链都跑。先单独跑分割脚本，确认：

- 模型能否正常加载
- 目标类别是否能被识别
- 输出的 `mask.png` 是否干净

命令：

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

- `/tmp/yolo_seg_mask.png`
  二值 mask
- `/tmp/yolo_seg_mask_vis.png`
  带实例高亮的可视化图
- `/tmp/yolo_seg_result.json`
  调试信息，里面会写：
  - 实际选中的类别
  - 置信度
  - bbox
  - mask 面积

常见用途：

- 想看当前模型到底有没有把目标分出来
- 想排查“为什么 pipeline 里 mask 不对”

## 第二步：把分割接回抓取 pipeline

当前抓取 pipeline 已经支持 `YOLO-seg -> FoundationPose`。

命令：

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

如果你只是想先看感知结果，不要动机械臂，就不要加 `--execute-grasp`。

如果你确认识别和 pose 都对了，再加：

```bash
--execute-grasp
```

## 第三步：准备你自己的分割数据

因为官方 `yolov8n-seg.pt` 不认识你的 `glasses_case_box`，后面需要自己训练。

推荐你按这个目录放数据：

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

- `images/train/`
  训练图片
- `images/val/`
  验证图片
- `labels/train/`
  对应训练图片的 YOLO-seg 标注
- `labels/val/`
  对应验证图片的 YOLO-seg 标注

标注格式要求：

- 使用 Ultralytics YOLO-seg polygon 格式
- 类别 id `0` 对应 `glasses_case_box`

你可以直接复制示例 YAML：

- `/home/rm/Long_sequence_tasks/vision_grasp/segmentation/datasets/glasses_case_box_seg_example.yaml`

然后把里面的 `path` 改成你真实的数据集路径。

## 第四步：怎么采训练数据

对你这个眼镜盒场景，建议数据尽量覆盖这些变化：

- 不同背景
- 不同光照
- 不同桌面材质
- 不同摆放角度
- 不同距离
- 手是否出现在附近
- 是否有部分遮挡

如果你后面目标是“手拿着物体也能稳定分出来”，那训练数据里一定要包含：

- 手拿眼镜盒
- 手在附近但不接触
- 只出现眼镜盒、不出现手

这样模型才学得会把“手”和“眼镜盒”区分开。

经验建议：

- 先做 100 到 300 张标注图，已经足够起步
- 不要一开始只拍特别干净的桌面图
- 要故意加入你现场真正会遇到的坏情况

## 第五步：训练自己的 YOLO-seg 模型

训练命令：

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

参数含义：

- `--data`
  数据集 YAML 路径
- `--model`
  初始模型，可以是官方 `yolov8n-seg.pt`
- `--epochs`
  训练轮数
- `--imgsz`
  训练尺寸
- `--batch`
  batch size
- `--device`
  `0` 表示 CUDA，`cpu` 表示 CPU
- `--name`
  本次训练的运行名

默认训练输出目录：

- `vision_grasp/weights/yolo_seg_runs/`

这个目录已经被 Git 忽略，不会被推到 GitHub。

## 第六步：训练完以后怎么接回抓取链

训练完成后，你最关心的是这个文件：

- `best.pt`

然后把 pipeline 里的这两个参数换掉：

```bash
--seg-weights /path/to/best.pt
--seg-label glasses_case_box
```

完整示例：

```bash
source /home/rm/miniforge3/bin/activate foundationpose

python3 /home/rm/Long_sequence_tasks/vision_grasp/integration/run_pose_grasp_pipeline.py \
  --camera-name camera_middle \
  --camera-frame camera_middle \
  --mesh /home/rm/Long_sequence_tasks/vision_grasp/object_models/glasses_case_box/glasses_case_box.obj \
  --object-label glasses_case_box \
  --config /home/rm/Long_sequence_tasks/vision_grasp/configs/glasses_case_box_grasp.yaml \
  --mask-backend yolo-seg \
  --seg-weights /home/rm/Long_sequence_tasks/vision_grasp/weights/yolo_seg_runs/glasses_case_box_seg/weights/best.pt \
  --seg-label glasses_case_box \
  --mask \
  --execute-grasp
```

## 推荐调试顺序

不要一上来就直接真抓。推荐按这个顺序调：

1. 单独跑 `run_yolo_seg_mask.py`
2. 看 `mask.png` 和 `mask_vis.png`
3. 再跑 `run_pose_grasp_pipeline.py`，但先不加 `--execute-grasp`
4. 检查 FoundationPose 输出的 `pose.json`
5. 最后再加 `--execute-grasp`

这样你能更快知道问题到底卡在：

- 分割
- 位姿估计
- 还是机械臂抓取执行

## 常见问题

### 1. 为什么官方模型分不出眼镜盒

因为官方 `yolov8n-seg.pt` 是通用 COCO 权重，不包含你的自定义类别。

它适合：

- 验证代码能不能跑
- 验证 Xavier NX 环境兼不兼容

它不适合直接稳定分割你的 `glasses_case_box`。

### 2. 为什么 mask 里总带上手

因为你现场真正困难的地方不是“有没有分割”，而是：

- 手和眼镜盒靠得太近
- 手和目标经常连在一起
- 传统深度分割容易粘连

所以训练数据里必须包含“手拿物体”的场景，不然模型学不会拆开。

### 3. 为什么已经有 mask 了，抓取还失败

因为整条链后面还有两步：

- FoundationPose 是否用这个 mask 得到了正确 pose
- 机械臂是否能到达 pregrasp / grasp 位姿

所以：

- `mask 对`
  不等于
- `pose 一定对`
  也不等于
- `机械臂一定抓得到`

### 4. 权重放哪里

建议放在：

- `/home/rm/Long_sequence_tasks/vision_grasp/weights/`

或者训练默认输出目录：

- `vision_grasp/weights/yolo_seg_runs/`

这些目录都已经被 Git 忽略，不会被推到 GitHub。

## 你现在最应该怎么做

如果你现在是第一次接自定义分割，我建议实际顺序就是：

1. 先采一批眼镜盒图片
2. 做分割标注
3. 训练一个 `glasses_case_box` 的 YOLO-seg `best.pt`
4. 先单独测试分割效果
5. 再接回 FoundationPose 和抓取 pipeline

这条路比继续硬调传统深度分割更符合你现在的真实需求。
