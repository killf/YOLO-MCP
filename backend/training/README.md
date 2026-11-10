# YOLO MCP 本地训练

入口为 `yolo-mcp-train` 或 `python -m backend.training.train`。页面训练从数据库标注生成本次数据集；离线命令读取已准备好的 YOLO 数据目录。模型、指标与日志都保存在本地。

## 模型与 GPU 环境

人工标注使用基础安装即可。YOLO26 训练和标注需额外安装训练依赖：

```bash
python -m pip install "yolo-mcp[training]"
```

已有 CUDA 或 AMD ROCm 环境时，先确认其中的 PyTorch 与硬件兼容，再在同一环境安装和运行 YOLO MCP。当前要求 PyTorch `>=2.9,<3`；安装前检查依赖解析结果，保留已准备好的 GPU 运行时。

开放词汇标注另需安装通用推理依赖：

```bash
python -m pip install "yolo-mcp[annotation]"
```

| 标注算法 | 权重或模型 ID | 准备方式 |
| --- | --- | --- |
| YOLO26 | 项目 `models/` 中的 `.pt` | 使用本项目训练产物或预先放入的权重 |
| Florence-2 | `microsoft/Florence-2-base`、`microsoft/Florence-2-large` | 首次使用自动下载，后续复用公共缓存 |
| GroundingDINO + SAM ViT-B | `IDEA-Research/grounding-dino-tiny` | 首次使用自动下载；当前矩形标注只使用 GroundingDINO 检测分支 |
| SAM 3 | `facebook/sam3` | 安装[官方 sam3 包](https://github.com/facebookresearch/sam3)，取得模型访问权限并完成 Hugging Face 登录后自动下载 |

模型在后端进程按需加载，不自动安装依赖。公共权重统一保存在 `YOLO_MCP_DATA_DIR/models/`：YOLO26 官方初始权重位于 `ultralytics/`，开放词汇模型使用 `huggingface/` 缓存；不同项目和每次训练共用，删除项目或训练记录不清理公共缓存。首次使用会下载，后续复用已下载文件；下载失败或访问受限会在页面显示具体原因。首次下载耗时较长时，建议使用 AI 批量标注查看最终状态。模型代码和权重遵循各自许可。

训练使用的字体与 Ultralytics 配置统一缓存到数据根目录下的 `.ultralytics/`，不同项目和每次训练共用，首次缺少字体时下载。数据根目录通过 `YOLO_MCP_DATA_DIR` 设置；离线命令显式设置第三方变量 `YOLO_CONFIG_DIR` 时使用指定目录。

源码开发时，可从仓库根目录执行 `python -m pip install -e "./backend[training]"` 或 `python -m pip install -e "./backend[annotation]"`。页面训练复用启动后端的 Python 环境。

## 页面训练参数

在项目“模型设置”中保存训练默认值；开始训练时可为本次运行修改。算法当前为 YOLO26 目标检测，可选官方初始权重或本项目模型。

“图像增强”开关控制训练输入增强：开启时沿用框架增强，可用 JSON 调整强度；关闭时只保留尺寸适配等必要预处理。“训练范围”支持全部参数、仅 Detect 检测头、先检测头后全部。检测头模式冻结 backbone、neck 和对应的 BN 统计；分阶段模式完成指定 step 后解冻全部可训练参数，保留优化器动量。step 按优化器实际更新次数累计，包含梯度累积，不计 AMP 跳过的更新；暂停后继续累计。

自定义参数使用 JSON 对象，例如：

```json
{
  "optimizer": "AdamW",
  "amp": false
}
```

点击参数标题后的“？”查看可用参数、默认值和说明。基础表单、模型、设备与路径由系统管理，不能在 JSON 中重复覆盖。学习率对应 `lr0`；`optimizer=auto` 时由框架决定实际学习率。

在训练弹窗标题旁的历史图标中查看记录。点击参数摘要查看详情，点击权重名称下载模型。

运行中的记录可“暂停训练”：当前 epoch 验证和检查点保存完成后，训练进程退出并释放 GPU。状态依次为“训练中 → 等待暂停 → 已暂停”；最后一轮或提前停止时正常完成。“继续训练”沿用同一条记录、原数据快照、优化器与精度缩放状态；暂停中的记录跨服务重启仍可继续。当前训练控制支持单设备；原有多设备全量训练仍可用，不提供暂停或新训练策略。

暂停期间禁止清理日志，因为运行目录同时保存恢复检查点；删除记录会放弃该次训练并删除检查点。服务意外中断的运行仍标为“已中断”，不会自动重跑。

## 项目目录

```text
projects/1/
├── images/                     # 上传原图
├── thumbnails/images/          # 缩略图；旧 uploads 原图对应 thumbnails/uploads/
├── models/<日期-编号>.pt
└── runs/<记录 ID>/
    ├── dataset/
    │   ├── images/             # 本次训练使用的独立图片副本
    │   ├── labels/             # 按本次类别顺序生成的 YOLO 标签
    │   ├── train.txt
    │   ├── test.txt
    │   └── data.yaml
    ├── console.log
    ├── train.log
    ├── resume.pt               # 暂停检查点（包含优化器状态和累计 step）
    └── training/               # 指标、图表和中间权重
```

项目只保存原始图片和数据库标注，不在标注保存时写训练副本。提交训练请求时才按当前已完成样本、数据划分和类别顺序生成快照；快照准备失败会回滚记录并清理本次目录。后台进程直接使用该快照，不重新读取项目标注。

原图不会被旋转或覆盖，旋转只作用于 run 内的图片副本。后续编辑、改类别、重新划分或删除原始样本，都不会改变已经生成的快照。新项目不创建 `uploads/`，旧原图按数据库中的路径继续读取，不自动搬迁。访问旧缩略图时，将其移入 `thumbnails/`，原图与附件记录不变。

## 数据格式

训练和测试清单必须非空，每行使用相对于清单的路径，例如 `./images/1.png`。标签位于对应的 `labels/`，每行格式为 `class_id x_center y_center width height`，坐标归一化到 `[0, 1]`。背景样本使用空标签文件。

```yaml
path: /absolute/path/to/run/dataset
train: train.txt
val: test.txt
test: test.txt
names:
  - person
```

测试集同时用于每轮验证和选取 `best.pt`，指标不是独立测试成绩。输入路径拒绝越界和符号链接逃逸，数据配置中的下载脚本不执行。

## 离线运行

页面训练复用后端的 Python 环境。当前使用 Ultralytics 8.4.203 和 PyTorch `>=2.9,<3`；已有 CUDA/AMD ROCm 环境应保留其 GPU 运行时。

从仓库根目录运行，下面的示例读取一个已有快照，在新的运行目录中训练：

```bash
python -m backend.training.train \
  --data "$HOME/.yolo-mcp/projects/1/runs/1/dataset" \
  --work-dir "$HOME/.yolo-mcp/projects/1/runs/manual-1" \
  --models-dir "$HOME/.yolo-mcp/projects/1/models" \
  --model yolo26n.pt --epochs 100 --imgsz 1024 --batch 2 --workers 0 --device 0
```

- `--data`：必填，包含图片、标签及三个配置文件的 YOLO 数据目录。
- `--work-dir`：训练运行目录，默认在 `--data` 下的 `runs/` 中创建独立目录。
- `--models-dir`：产出模型目录，默认是 `--data` 下的 `models/`；页面训练使用项目 `models/`。
- `--result-file`：将训练编号、模型路径和指标写入 JSON，供训练记录读取。
- `--augmentation` / `--no-augmentation`：开启或关闭训练图像增强，默认开启。
- `--training-scope full|head|head_then_full`：训练范围；`--unfreeze-steps` 设置解冻前的优化器更新次数。
- `--resume-checkpoint`：使用原运行目录的 `resume.pt` 继续训练，同时指定原 `--work-dir` 和该目录下的 `dataset/`。

读取外部数据时，离线命令会复制数据到本次 `dataset/`，并在 `input/` 保留输入配置；如果输入已经是本次运行的 `dataset/`，则原地校验，不重复复制或创建 `input/`。

默认模型是 `yolo26s.pt`，官方权重首次使用时可能下载；也可提供本地权重路径。未指定设备时优先使用 CUDA/ROCm，再选择 MPS，最后选择 CPU。完整参数说明使用 `--help` 查看。

页面 JSON 参数通过 `--extra-params '{"lr0": 0.001, "amp": false}'` 传入。只接受 JSON 对象，参数由当前 Ultralytics 校验；基础表单、模型、设备及路径不能重复覆盖。训练失败返回非零码并保留日志。

## 训练记录

记录保存参数、状态、指标、产出模型与执行时间。最优权重发布到项目 `models/`，输入和中间权重保留在本次运行目录。

“清理日志”删除整个运行目录，包括该次数据快照、日志和中间文件，保留记录与产出模型。“删除”同时移除记录、产出模型和运行目录；运行中或仍在使用的模型不能删除。

## 共用服务镜像

```bash
docker build -t yolo-mcp:local .

docker run --rm --gpus all --shm-size=8g --entrypoint yolo-mcp-train \
  -v /your/local/project:/workspace/project \
  yolo-mcp:local --data /workspace/project/runs/1/dataset \
  --work-dir /workspace/project/runs/manual-1 --models-dir /workspace/project/models \
  --epochs 100 --batch 2
```

挂载完整项目目录以保留图片、模型和日志。镜像使用 `ultralytics/ultralytics` 基础环境，不在运行时安装依赖。
