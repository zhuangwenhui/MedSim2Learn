# 实验配置清单 REHEARSAL-20260810（数据回路试运转，跑前交检）

## 1. 目的与预注册判据

- **目的**：机械验证"Windows 产数据 → 服务器可用"的完整回路（传输→落盘→装配→特征提取），在依赖它做正式实验前发现全部摩擦点。**这不是科学实验：不产生任何 Gap/训练结论**。
- **预注册判据**：
  1. 传输完整性：上传后服务器端逐文件 sha256 与本机**逐一相等**（0 失配）；
  2. 可装配：上传的逐序列 `.pt` 能在服务器端组成 KiDKNet 可读的 data_dir（含 `metadata.yaml` 与 `sequence_index.json`）；
  3. 可提特征：`dknet.data.feature_cache` 在其上跑通，产出 `total_samples=1716, feature_dim=1536` 的缓存；
  4. 全程回执：每步命令与输出留档（本清单末尾附实测回执）。
- **预注册应变**（透明列出，不算偏离）：`build_from_pngs` 产出的逐序列 dataset 若缺 `sequence_index.json`（该文件常规由 assemble 生成），则按 assemble 的 schema 生成最小索引后重试特征提取，并在回执记录生成物内容。

## 2. 数据与落点

| 项 | 值 |
|---|---|
| 载荷 | 试点 seed1 的 `seq01_256/`（约 1.3G：`preprocessed_batch_*.pt` + `metadata.yaml`），含 `appearance_meta.json` 一并上传 |
| 传输通道 | tar 流 → ssh 别名 `H100+RTX6000Adax3` → `docker exec -i 4cc88597ad44 tar -x`（六月 77G 上传同款通道） |
| 服务器落点 | 容器 `/workspace/project/MedSim2Learn/DataFlow/Deform_post/preprocessed/sources/synt/dr-c1-pilot/seq01/`（全新目录，无覆写；该层级此前不存在，本次创建即回路的一部分） |
| 特征输出 | `.../DataFlow/Deform_post/feature_cache/dr_c1_pilot_feat_convnextL/`（全新目录） |

## 3. 命令（逐字）

本机打包上传（Git Bash）：
```
cd /d/MedSim2Learn-Windows-Render-Guards/_c1_scratch/pilot/seed1 && tar -cf - seq01_256 appearance_meta.json | ssh "H100+RTX6000Adax3" "docker exec -i 4cc88597ad44 bash -c 'mkdir -p /workspace/project/MedSim2Learn/DataFlow/Deform_post/preprocessed/sources/synt/dr-c1-pilot/seq01 && tar -xf - -C /workspace/project/MedSim2Learn/DataFlow/Deform_post/preprocessed/sources/synt/dr-c1-pilot/seq01'"
```
两端哈希对账（本机与服务器各算一遍、逐文件比对）：
```
find seq01_256 -type f -exec sha256sum {} \; | sort -k2   （本机）
docker exec ... bash -c "cd .../dr-c1-pilot/seq01 && find seq01_256 -type f -exec sha256sum {} \; | sort -k2"   （服务器）
```
特征提取（容器内，按预注册应变可先补最小索引）：
```
PYTHONPATH=KiDKNet /opt/venv/bin/python -m dknet.data.feature_cache --source DataFlow/Deform_post/preprocessed/sources/synt/dr-c1-pilot/seq01/seq01_256 --out DataFlow/Deform_post/feature_cache/dr_c1_pilot_feat_convnextL --size large --device cuda:0
```

## 4. 环境与成本

传输：校园网 LAN，1.3G 预计数分钟；特征提取：单卡（H100/Ada 任一空闲卡），1716 帧预计 <1 分钟（参照 real 52,522 帧 308s 的实测速率）；服务器磁盘余 1.9T。

## 5. 术语表（术语｜通俗解释｜来路）

| 术语 | 解释 | 来路 |
|---|---|---|
| 回路试运转 | 项目自造词：小载荷走一遍完整数据通道以验证机械可行性 | 本清单 §1；动机见 2026-08-10 会话"不要骗我"裁定 |
| tar 流上传 | 本机打 tar 不落地、经 ssh 管道在容器内解开（本机无 rsync） | 记忆 session-server-deploy-handoff（六月 77G 实践） |
| docker exec | 在宿主机上向容器内执行命令（DataFlow 服务器侧属 root，须经容器写入） | 同上记忆"从本地 session 驱动容器"节 |
| sources/synt/<域> | DataFlow 四层布局中"逐序列序列化产物"层的合成域目录 | 仓库根 CLAUDE.md「DataFlow/Deform_post layout」节 |
| assemble / data_dir | 把逐序列 `.pt` 硬链接装配成 KiDKNet 训练可读目录的步骤/产物 | `Deform_post/dpost/dataset/assemble.py` 模块注释 |
| sequence_index.json | data_dir 内按序列记录样本区间的索引文件，feature_cache 依赖它 | `dknet/data/feature_cache.py` `_discover_batch_files`；assemble.py 写出 |
| feature_cache | 冻结 ConvNeXt-Large 逐帧特征缓存（1536 维），供时序模型与域差距度量复用 | `KiDKNet/dknet/data/feature_cache.py` 模块 docstring |
| ConvNeXt-Large | 本项目固定的图像骨干网络（ImageNet 预训练，特征维 1536） | KiDKNet configs `*convnextL.yaml`；文献=ConvNeXt (Liu et al., CVPR 2022, 台账外通识引用) |
| 逐文件 sha256 对账 | 两端各算哈希、按文件名逐一比对，0 失配才算传输成功 | 判据 §1-1；工具=GNU coreutils sha256sum |

## 6. 实测回执（2026-08-10 协调者填写）

- **判定：四项预注册判据全部通过。**
- 传输：tar 流上传实测 39.9s（约 1.5G 载荷）；落点按计划全新创建。
- 哈希对账：本机与服务器各算 sha256，**1720/1720 文件零失配**（首轮 diff 报"全不同"系 Windows 二进制模式 `hash *path` 与 Linux `hash␣␣path` 的格式差，空白规范化后逐行相等——此格式陷阱记入经验）。
- 预注册应变触发：`build_from_pngs` 产物确实缺 `sequence_index.json`；按 assemble.py L471 schema 生成最小索引（单序列 01，[0,1716)，内容与哈希 6708d969… 已入对账清单）后上传。
- 特征提取：`[done] total_samples=1716, feature_dim=1536, elapsed 12.2s`（cuda:0），输出五件齐全（features/forces/ids/sequence_index/metadata）。
- 结论：Windows→服务器数据回路**机械可行性已实证**；全量批次可沿同一通道执行。本回执不构成任何 Gap/训练主张。
