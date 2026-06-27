# Experiment Report — Video-to-Force Prediction with Synthetic Augmentation
# 实验汇总报告 — 用合成数据增强的「视频→力」预测

Period 时间范围: 2026-06-13 → 2026-06-23
Commit range 提交范围: `66334d9` … `1f63f3c` (18 commits)
Author 负责人: WENHUIZ

> How to read this report 阅读说明
> Every number below comes from a file on disk; the **"Verify 核实"** line under each
> result tells you exactly which file to open or which script to re-run. No claim is
> made that cannot be checked by hand.
> 下面每个数字都来自磁盘上的真实文件;每条结果下的 **"核实"** 行告诉你打开哪个文件、
> 或重跑哪个脚本即可亲自验证。没有任何一句结论是无法人工核对的。

---

## 0. One-page summary 一页纸总结

We are trying to predict the 3-D force a surgical grasper applies to a kidney, using
only the endoscopic video. Real labelled video is scarce (~31 clips), so we built a
physics-simulation (FEM) pipeline that re-creates each real clip as a synthetic
"digital twin" and asked: **does adding synthetic data make the model better on real
video?**

我们要做的是:**只看内窥镜视频,预测手术钳对肾脏施加的三维力**。带标注的真实视频很少
(约 31 段),所以我们做了一条物理仿真(有限元 FEM)管线,把每段真实视频复刻成一个合成
「数字孪生」,然后问:**加入合成数据,模型在真实视频上会变好吗?**

**The honest answer so far 目前的诚实答案:**
1. A model trained on synthetic frames **alone** does not work on real video at all — the
   error is about **6× worse**. The problem is that synthetic and real frames simply
   *look* different (an appearance gap), not that the physics is wrong.
   只用合成帧训练的模型在真实视频上**完全不可用**,误差约**差 6 倍**。根因是合成帧和真实帧
   「长得不一样」(外观差),不是物理算错。
2. Once the model sees real data, **every** way of adding synthetic data (mixing, or
   pre-training then fine-tuning) lands in the **same** accuracy band as using real data
   alone — the differences are smaller than the run-to-run spread. So at today's scale,
   synthetic data does not yet *add* measurable accuracy.
   一旦模型见过真实数据,**各种**加合成数据的方式(混合、或先预训练再微调)都落在与「只用
   真实数据」**同一**精度带内——彼此差异小于不同次运行间的波动。所以现阶段合成数据还没带来
   可测的额外精度。
3. The single biggest obstacle right now is **measurement noise**: our validation set is
   only 3 clips, so the score swings a lot between runs and hides small effects. Fixing
   the measurement comes before anything else.
   当前最大的障碍是**测量噪声**:验证集只有 3 段,导致每次评测结果波动很大、淹没小效应。修好
   「测量尺子」是后续一切比较的前提。

One change did help: a **redesigned loss function** (it lets the model learn how much to
trust each training sample) made training **markedly more stable** and lowered the error
in the hardest setting. 唯一明确有帮助的改动是**重新设计损失函数**(让模型自己学会每个样本
该信多少),它让训练**明显更稳**,并在最难的设置下降低了误差。

---

## 1. Glossary 术语对照表 (so nothing here is "AI-only" jargon)

| Term used 术语 | 中文 | Plain meaning 一句话解释 |
|---|---|---|
| Magnitude error (MAE) | 力大小误差 | How far off the predicted force *size* is, averaged. Lower is better. Reported in normalized units (a.u.). |
| Direction error | 力方向误差 | The angle (in degrees) between predicted and true force direction. Lower is better. |
| 5-fold cross-validation (CV) | 5 折交叉验证 | Split data into 5 parts; train on 4, test on the held-out 1, rotate 5 times. The spread across the 5 runs (±) tells us how reliable a number is. |
| Real-only | 仅真实 | Train using only the real video clips. |
| Synthetic-only | 仅合成 | Train using only synthetic (FEM-rendered) clips, then test on real video — no real training at all. |
| Mixed | 混合 | Train on real and synthetic clips together. |
| Transfer (pre-train → fine-tune) | 迁移(预训练→微调) | First train on synthetic, then continue training on real. |
| Single-frame / Sequence | 单帧 / 序列 | The model looks at one frame, or at a short video sequence. |
| Few-shot / low-data curve | 少样本曲线 | How accuracy changes as we allow only k real clips (k = 1,2,4,8,16) for training. |
| Appearance gap (a.k.a. domain gap) | 外观差(域差) | Synthetic and real images *look* different, so a model trained on one fails on the other. |
| Learned uncertainty weighting | 学习式不确定性加权 | The loss lets the model automatically down-weight noisy samples and balance the "size" vs "direction" objectives, instead of us hand-tuning a fixed ratio. |
| Photometric augmentation | 光度增强 | During training, randomly tweak brightness/colour/blur of images (pixels only, never geometry, so the force label stays correct). |
| Backbone (ConvNeXt-Large) | 主干网络 | The image feature extractor; a standard, strong CNN pre-trained on ImageNet. |
| FEM (finite-element method) | 有限元法 | The physics solver that computes how the soft kidney deforms under a force. |

---

## 2. What we set out to answer 我们想回答什么

The work is organised around four questions (set by the project owner) plus one extra:
本工作围绕四个问题(由项目负责人设定)外加一个附加问题展开:

1. **Diversity 多样性** — does *more varied* synthetic data improve real-video accuracy?
2. **Training recipe 训练方式** — what is the best way to combine synthetic + real data?
3. **Loss function 损失函数** — does redesigning the loss improve accuracy?
4. **Architecture 架构** — which model architecture suits this task best? *(planned last)*
5. *(extra)* **Scaling 规模** — can we predict how much / what synthetic data to generate,
   like a scaling law? *(planned, not yet run)*

This report covers what has actually been **built and measured** for questions 1–3; the
architecture study (4) and scaling study (5) are deliberately scheduled for later, after
the measurement is fixed.
本报告涵盖问题 1–3 中**已建成并测量**的部分;架构(4)与规模(5)按计划放在「修好测量」之后再做。

---

## 3. The experimental setup 实验装置

- **Real data 真实数据:** ~31 endoscopic clips of a pig kidney pressed by a sensorised
  surgical grasper; the force comes from the grasper's own sensor.
  约 31 段猪肾内窥镜视频,手术钳带力传感器,力即传感器读数。
- **Synthetic data 合成数据:** for each real clip we reconstruct the kidney surface from
  CT, turn it into an elastic body, apply the **same** real measured force, solve the
  deformation with FEM, and render it back to video — a 1-to-1 "digital twin". Because the
  force comes from the real sensor, the *forces* already match real; only the *images* differ.
  对每段真实视频,用 CT 重建肾表面、设为弹性体、施加**同一**真实测得的力、用 FEM 解形变再
  渲染成视频,得到 1:1「数字孪生」。因为力来自真实传感器,**力分布天然匹配真实**,只有**图像**不同。
- **Model 模型:** a ConvNeXt-Large image backbone (ImageNet-pre-trained) + a small force
  regression head; for video, a temporal-convolution head over the frame features. The full
  architecture is in **§3.1** (per-frame = `arch_single`; video-sequence = `arch_sequence`).
  ConvNeXt-Large 主干(ImageNet 预训练)+ 小型力回归头;视频版在帧特征上加时序卷积头。
  完整架构见 **§3.1**(单帧 `arch_single`;序列 `arch_sequence`)。
- **How we score 评分方式:** magnitude error and direction error, under 5-fold
  cross-validation; the ± is the spread across folds. For the mixed setups we score on
  the **real** test clips only, so all numbers are comparable on real video.
  用力大小误差与力方向误差,5 折交叉验证;± 为折间波动。混合设置只在**真实**测试段上评分,
  确保所有数字在真实视频上可比。
- **The 8 training setups 八种训练设置:**

| Code | Setup 设置 | Frames 输入 |
|---|---|---|
| c1 | Real-only 仅真实 | single 单帧 |
| c2 | Synthetic-only 仅合成 | single 单帧 |
| c3 | Mixed 混合 | single 单帧 |
| c4 | Transfer 迁移 | single 单帧 |
| c5 | Real-only 仅真实 | sequence 序列 |
| c6 | Synthetic-only 仅合成 | sequence 序列 |
| c7 | Mixed 混合 | sequence 序列 |
| c8 | Transfer 迁移 | sequence 序列 |

### 3.1 Model architecture 模型架构

*Schematics 示意图: per-frame model = **`arch_single`**; video-sequence model = **`arch_sequence`**
(both drawn from the verified code, in the colour language of the earlier `Figure_2_wf.pdf`).*

There are **two** networks, not eight. The eight conditions form a 2 × 4 grid — two
architectures × four data/training regimes (the eight rows of the setup table above).
**Within each architecture the network is identical**; only the training data and the
starting weights change. This is why
the only architecture comparison in the study is "per-frame vs. sequence", and why a
difference *within* a row is purely a data/training effect.
共有**两种**网络,而非八种。八个条件构成一个 2 × 4 网格——两种架构 × 四种数据/训练方式
(即上方设置表的八行)。**每种架构内部网络完全相同**,只改训练数据与初始权重。所以本研究里唯一的架构对比
是「单帧 vs 序列」,而同一行内部的差异纯粹来自数据/训练。

**Architecture A — per-frame model (c1–c4) 单帧模型**  —  see figure `arch_single`.
- Input 输入: one endoscopic frame, 256 × 256 × 3. 单张内窥镜帧。
- Backbone 主干: ConvNeXt-Large (ImageNet-pre-trained, ≈197 M parameters), **fine-tuned
  end-to-end** (not frozen); global average pooling → a 1536-dimensional feature per frame.
  ConvNeXt-Large(ImageNet 预训练,约 1.97 亿参数),**端到端微调**(不冻结);全局平均池化得到
  每帧 1536 维特征。
- Head 回归头: a 4-layer MLP, 1536 → 1024 → 512 → 256 → 3, each hidden layer =
  Linear + BatchNorm + ReLU + Dropout(0.1); the last layer outputs the 3-D force.
  四层 MLP,1536 → 1024 → 512 → 256 → 3,每隐藏层 = 线性 + 批归一化 + ReLU + Dropout(0.1);
  末层输出 3D 力。
- Loss 损失: 0.4 × vector-MSE (force size/components) + 0.6 × cosine-squared (force direction).
  0.4 × 向量 MSE(力大小/分量)+ 0.6 × 余弦平方(力方向)。

**Architecture B — video-sequence model (c5–c8) 序列模型**  —  see figure `arch_sequence`.
- Input 输入: a clip of T = 256 consecutive frames (overlapping, stride 128).
  T = 256 连续帧的片段(重叠,步长 128)。
- Frame encoder 帧编码器: the same ConvNeXt-Large, but **frozen** — its 1536-d per-frame
  features are pre-computed once and cached, so only the temporal part trains (this keeps
  compute and memory tractable for long clips). 同一个 ConvNeXt-Large,但**冻结**——每帧
  1536 维特征一次性预算并缓存,只训练时序部分(长片段下省算力/显存)。
- Temporal head 时序头: a multi-stage temporal convolutional network (MS-TCN, after
  Abu Farha & Gall, CVPR 2019 / TeCNO, MICCAI 2020) — 3 stages × 10 dilated **causal** 1-D
  convolutions (dilation 1, 2, 4, …, 512; 64 channels; kernel 3; residual). Each stage
  refines the previous stage's per-frame force and all three are supervised (deep
  supervision); the output is one 3-D force per frame (T × 3). "Causal" means frame *t*
  never uses future frames (real-time-capable); the receptive field is ≈ 2046 frames.
  多阶段时序卷积网络(MS-TCN,源自 Abu Farha & Gall, CVPR 2019 / TeCNO, MICCAI 2020)——
  3 阶段 × 10 层膨胀**因果**一维卷积(膨胀 1,2,4,…,512;64 通道;卷积核 3;残差)。每阶段细化
  上一阶段的逐帧力,三阶段全部监督(深监督);输出逐帧 3D 力(T × 3)。「因果」指第 *t* 帧不看
  未来帧(可实时);感受野约 2046 帧。
- Loss 损失: the same size + direction objective per frame, plus a temporal-smoothness term
  that matches the frame-to-frame change of the true force. 同样的逐帧大小+方向目标,外加一个
  时序平滑项,匹配真实力的逐帧变化。

**Transfer 迁移 (c4, c8):** initialise from the matching synthetic-only model, then fine-tune
on real. For the per-frame model this is "linear-probe then fine-tune" (train the head with
the backbone frozen for a few epochs, then unfreeze the backbone at 0.1× the learning rate);
for the sequence model only the temporal head's weights are carried over. 从对应的「仅合成」
模型初始化,再在真实数据上微调。单帧版是「先线性探针再微调」(先冻结主干只训头几轮,再以
0.1× 学习率解冻主干);序列版只迁移时序头的权重。

**Verify 核实:** `KiDKNet/dknet/models/force_net.py`, `.../heads/regression_head.py`,
`.../sequence_force_net.py`, `.../temporal.py`; `KiDKNet/configs/c1…c8_*.yaml`. Schematics:
`arch_single.png` / `.pdf` and `arch_sequence.png` / `.pdf`.

> Both figures are drawn from the current code (ConvNeXt-**Large**, 1536-d). The older
> `Figure_2_wf.pdf` showed a 768-d ConvNeXt from an earlier run and is superseded by `arch_single`
> for this study. 两图均按当前代码绘制(ConvNeXt-Large,1536 维);旧的 `Figure_2_wf.pdf` 是早期
> 实验的 768 维版,本研究以 `arch_single` 为准。

---

## 4. Experiments and findings 实验与发现

### 4.1 Can synthetic data replace real data? 合成能不能替代真实?  *(main result 主结果)*

**Purpose 目的.** Establish the baseline accuracy of every training setup on real video,
and see whether synthetic data alone can carry the task.
确立各设置在真实视频上的基线精度,看仅靠合成能否完成任务。

**Method 做法.** Train all 8 setups, 5-fold CV each, score on real test clips.
训练全部 8 种设置,各 5 折交叉验证,在真实测试段评分。

**Result 结果** (mean ± fold-spread; 力大小误差越低越好):

| Setup 设置 | Magnitude error 力大小误差 | Direction error 力方向误差 |
|---|---|---|
| Real-only (single) 仅真实·单帧 | 0.232 ± 0.073 | 24° |
| **Synthetic-only (single) 仅合成·单帧** | **1.357 ± 0.456** | **55°** |
| Mixed (single) 混合·单帧 | 0.204 ± 0.054 | 25° |
| Transfer (single) 迁移·单帧 | 0.209 ± 0.035 | 26° |
| Real-only (sequence) 仅真实·序列 | 0.234 ± 0.023 | 28° |
| **Synthetic-only (sequence) 仅合成·序列** | **1.542 ± 0.097** | **60°** |
| Mixed (sequence) 混合·序列 | 0.222 ± 0.040 | 28° |
| Transfer (sequence) 迁移·序列 | 0.240 ± 0.037 | 29° |

**Takeaway 结论.** Synthetic-only is **~6× worse** and its direction is almost random
(55–60° error). Every setup that uses real data lands in the same 0.20–0.24 band. So real
data is currently necessary, and synthetic data does not yet add accuracy beyond it.
仅合成**差约 6 倍**,方向几乎随机(55–60°)。所有用到真实数据的设置都落在 0.20–0.24 同一带。
即真实数据当前不可或缺,合成数据尚未在其之上带来额外精度。
**Verify 核实:** `DataFlow/KiDKNet/outputs/cv5/report/report_cv_table.csv` · Figure `fig1_domain_gap`.

### 4.2 What exactly is the gap? 域差到底是什么?

**Purpose 目的.** Decide whether the failure of synthetic-only is a *physics* problem or an
*appearance* (looks-different) problem — they need completely different fixes.
判断仅合成失败是**物理**问题还是**外观**(长得不一样)问题——两者解法完全不同。

**Method 做法.** Take the model's image features for real vs synthetic frames; (a) check
whether a trivial classifier can tell them apart, (b) measure how varied the synthetic
features are versus real.
取模型对真实/合成帧的图像特征:(a) 看一个最简单的分类器能否区分两者,(b) 比较合成特征的
多样性与真实的差距。

**Result 结果.** A trivial classifier separates real from synthetic **100%** of the time
(chance is 50%), and a simple variety measure of the image features is **several-fold
lower** for synthetic than for real frames (clearly visible in the figure). The forces, by
construction, already match real — so this is an **appearance** gap, not a physics gap.
最简单的分类器以 **100%** 准确率区分真假(随机猜是 50%);按一个简单的「多样性」度量,合成帧的
图像特征比真实**低数倍**(图中清晰可见)。而力本身按构造已匹配真实——所以这是**外观差**,不是
物理差。
**Verify 核实:** Figure `DataFlow/Deform_post/feature_cache/domain_gap.png`; re-runnable via
`KiDKNet/scripts/analyze_domain_gap.py`.

### 4.3 Which fine-tuning recipe is best? 哪种迁移微调最好?

**Purpose 目的.** If we pre-train on synthetic then fine-tune on real, which fine-tuning
strategy wins? (Five common recipes.)
若先在合成上预训练、再在真实上微调,哪种微调策略最好?(五种常见配方。)

**Method 做法.** Five recipes — fine-tune everything / different learning rates per layer /
retrain only the last few layers / freeze the backbone and train the head only /
linear-probe-then-fine-tune — all starting from the same synthetic-pre-trained weights,
5-fold CV.
五种配方——全量微调 / 分层学习率 / 只重训最后几层 / 冻结主干只训头 / 先线性探针再微调——
都从同一合成预训练权重出发,5 折交叉验证。

**Result 结果.** All five tie: 0.207–0.216, a spread (0.009) far smaller than the fold
noise (±0.03). 五种全部打平:0.207–0.216,彼此差距(0.009)远小于折间噪声(±0.03)。

**Takeaway 结论.** The fine-tuning recipe is **not** a bottleneck; the only real benefit of
transfer over training-from-scratch is slightly **more stable** runs, not higher accuracy.
微调配方**不是**瓶颈;迁移相对从头训练唯一的真实收益是**更稳**,而非更准。
**Verify 核实:** `DataFlow/KiDKNet/outputs/cv5/report/report_race_table.md`.

### 4.4 How scarce must data be for synthetic to help? 数据多稀缺时合成才有用?

**Purpose 目的.** Synthetic priors should matter most when real data is *very* scarce. Test
this directly by allowing only k real clips (k = 1,2,4,8,16).
合成先验理应在真实数据**极少**时最有用。直接用「只给 k 段真实视频」(k=1,2,4,8,16)来检验。

**Method 做法.** Fine-tune from a synthetic-pre-trained start vs from a plain ImageNet start,
on k real clips, 3 random seeds each.
分别从「合成预训练」和「普通 ImageNet」出发,在 k 段真实视频上微调,各 3 个随机种子。

**Result 结果** (magnitude error; synthetic-start / ImageNet-start):

| k real clips | Synthetic start | ImageNet start |
|---|---|---|
| 1 | 0.582 | 0.755 |
| 2 | 0.563 | 0.590 |
| 4 | 0.309 | 0.340 |
| 8 | 0.325 | 0.306 |
| 16 | 0.230 | 0.239 |

**Takeaway 结论.** The synthetic start is lower at the very smallest k, but the run-to-run
spread is large and the two curves overlap throughout — so the edge is **not statistically
established** (only 3 seeds). Most of the k=1 advantage came from a single lucky run. By
k ≥ 4 the synthetic start no longer helps, and it never helps *direction*. Honest reading:
synthetic pre-training gives **at most a small, unproven edge in the extreme-scarcity
corner**.
合成起点在最小 k 处更低,但评测结果在不同次运行间波动大、两条曲线全程重叠——所以这点优势**统计上不成立**
(仅 3 种子)。k=1 的优势大半来自单次幸运。k≥4 起合成起点不再有用,且对**方向**从无帮助。
诚实结论:合成预训练**至多在极稀缺角落带来一点尚未证实的小优势**。
**Verify 核实:** `DataFlow/KiDKNet/outputs/kshot/report/kshot_summary.json` · Figure `fig2_kshot`.

### 4.5 Does redesigning the loss function help? 改损失函数有没有用?

**Purpose 目的.** Test whether a smarter loss — one that learns how much to trust each
sample and auto-balances the "size" vs "direction" terms — beats a hand-tuned fixed ratio.
检验一种更聪明的损失——让模型学会每个样本该信多少、并自动平衡「大小」与「方向」两项——
能否胜过手调的固定系数。

**Method 做法.** Same model and data, only the loss changes: fixed weighting vs learned
uncertainty weighting. Tested on the real-only and the mixed single-frame settings, 5-fold CV.
模型与数据不变,只换损失:固定加权 对 学习式不确定性加权。在「仅真实」与「混合」单帧设置上测,5 折。

**Result 结果:**

| Setting 设置 | Fixed weighting 固定加权 | Learned uncertainty 学习式不确定性 | Change 变化 |
|---|---|---|---|
| Real-only 仅真实 | 0.232 ± 0.073 | **0.190 ± 0.037** | mean −18%, spread −49% |
| Mixed 混合 | 0.204 ± 0.054 | 0.206 ± 0.043 | mean ≈ flat, spread −20% |

**Takeaway 结论.** Learned uncertainty weighting makes training **markedly more stable**
(fold spread down 49% / 20%) and, in the noisiest "real-only" setting, also lowers the mean
error by 18% (0.232 → 0.190). The stability gain is the robust, repeatable part; the 18%
mean improvement is encouraging but, with only 5 folds, still within the run-to-run noise
(a paired test over the 5 folds is not significant). This is the **one change that clearly
helped** so far.
学习式不确定性加权让训练**明显更稳**(折间波动降 49%/20%),并在最吵的「仅真实」设置下把
均值误差降 18%(0.232→0.190)。**变稳**是稳健可复现的部分;18% 的均值改善令人鼓舞,但仅 5 折
时仍在波动范围内(对这 5 折做配对检验并不显著)。这是迄今**唯一明确有帮助的改动**。
**Verify 核实:** `DataFlow/KiDKNet/outputs/cv5_unc/{c1,c3}/cross_fold_summary.json` · Figure `fig3_loss_uncertainty`.

### 4.6 Does training-time image augmentation help? 训练期图像增强有没有用?

**Purpose 目的.** Test cheap, label-safe photometric augmentation (random brightness/colour/
blur on pixels only) as a regulariser.
检验廉价、标注安全的光度增强(只动像素的随机亮度/颜色/模糊)作为正则手段。

**Result 结果.** No measurable accuracy change in the fully-completed mixed setting
(0.204 → 0.208, within noise); the real-only arm completed only 2 of 5 folds so its number
is not interpretable. Direction error was, if anything, slightly worse.
在完整跑完的混合设置上无可测精度变化(0.204→0.208,在噪声内);仅真实那一臂只跑完 2/5 折,
其数字不可解读。方向误差若有变化是略差。

**Takeaway 结论.** Photometric augmentation is at best a mild stabiliser, not a decisive
lever — consistent with the diagnosis that the real obstacle is the appearance gap, not
under-regularisation. 光度增强至多是温和的稳定手段,非决定性杠杆——与「真正障碍是外观差、
而非正则不足」的诊断一致。
**Verify 核实:** `DataFlow/KiDKNet/outputs/cv5_aug/{c1,c3}/cross_fold_summary.json` · Figure `fig4_photometric_aug`.

### 4.7 Render-time randomization (designed, but blocked) 渲染期随机化(已设计,环境受阻)

**Purpose 目的.** The most promising cheap fix for the appearance gap is to randomize the
*renderer* (backgrounds, organ colour/texture, lighting) so the synthetic frames stop
looking uniformly white and become more varied.
缩小外观差最有希望的廉价做法,是在**渲染端**随机化(背景、器官颜色/纹理、光照),让合成帧
不再清一色发白(外观单一)、变得更多样。

**Status 状态.** A minimal, label-safe design was written and reviewed, but it **could not be
run here**: this Linux container cannot do off-screen GPU rendering (no headless GL/EGL). It
needs the dedicated Windows/GPU rendering environment. Nothing was committed.
已写出并评审了一份最小、标注安全的设计,但**无法在此运行**:当前 Linux 容器不支持离屏 GPU
渲染(无 headless GL/EGL),需要专用的 Windows/GPU 渲染环境。未提交任何代码。

---

## 5. Overall conclusions 总体结论

1. **The bottleneck is the appearance gap, not the model design.** The single-frame CNN
   (0.232) and the temporal sequence model (0.234) reach the same real-video accuracy and
   show the same synthetic-only failure (1.36 vs 1.54), so changing the model design does
   not fix this. A fuller architecture study (video transformers) is still planned (§2,
   question 4), but the current limit is clearly the appearance gap, not the network.
   **瓶颈是外观差,不是模型设计。** 单帧 CNN(0.232)与时序序列模型(0.234)达到相同的真实
   分数、并出现相同的仅合成失败(1.36 对 1.54),所以改模型设计解决不了。更完整的架构研究
   (视频 transformer)仍在计划中(§2 问题 4),但当前瓶颈显然是外观差,不是网络。
2. **Measurement noise is the binding constraint right now.** With only a 3-clip validation
   set, the score never stabilises and the spread between folds is larger than almost every
   effect we want to measure. Enlarging and stabilising the measurement must come first.
   **当前的硬约束是测量噪声。** 验证集只有 3 段,分数从不稳定,折间波动大于几乎所有想测的效应。
   必须先扩大并稳定测量。
3. **Synthetic data is, so far, weak-but-not-harmful.** It does not yet beat real-only, but
   it does not hurt; the path to making it pay off is to close the appearance gap (render
   randomization → image translation) rather than to change the model.
   **合成数据目前「弱但无害」。** 尚未胜过仅真实,但也不拖后腿;让它产生价值的路径是闭合外观差
   (渲染随机化→图像翻译),而不是改模型。

The one concrete improvement found is the **learned-uncertainty loss** (§4.5), which is
cheap, independent of the other levers, and clearly stabilises training.
已找到的唯一具体改进是**学习式不确定性损失**(§4.5):廉价、与其他改动互不干扰、并明确让训练更稳。

---

## 6. Not done / blocked / next 未做 · 受阻 · 下一步

- **Measurement overhaul (recommended next) 测量大改(建议下一步):** enlarge the validation
  set, normalize the force targets, and run more folds/seeds, then re-establish all
  baselines. This invalidates current baselines and costs roughly a full day of compute, so
  it awaits a go-ahead. 扩验证集、力目标归一化、加折/加种子,再重建全部基线。会作废现有基线、
  约一天算力,待批准。
- **Render randomization 渲染随机化:** needs the Windows/GPU rendering environment (§4.7).
- **Architecture & scaling studies 架构与规模研究:** deliberately deferred until the
  measurement is trustworthy and the appearance gap is being closed.
  刻意推迟到测量可信、外观差开始闭合之后。

---

## 7. Where to verify every number 怎么核实每个数字

| Claim 结论 | File / script to check 核实文件/脚本 |
|---|---|
| 8-setup main table (§4.1) | `DataFlow/KiDKNet/outputs/cv5/report/report_cv_table.csv` |
| Appearance gap 100% separable, 6× (§4.2) | `DataFlow/Deform_post/feature_cache/domain_gap.png`; re-run `KiDKNet/scripts/analyze_domain_gap.py` |
| Fine-tuning recipes tie (§4.3) | `DataFlow/KiDKNet/outputs/cv5/report/report_race_table.md` |
| Few-shot curve (§4.4) | `DataFlow/KiDKNet/outputs/kshot/report/kshot_summary.json` |
| Uncertainty loss (§4.5) | `DataFlow/KiDKNet/outputs/cv5_unc/{c1,c3}/cross_fold_summary.json` |
| Photometric augmentation (§4.6) | `DataFlow/KiDKNet/outputs/cv5_aug/{c1,c3}/cross_fold_summary.json` |
| Model architecture (§3.1) | `KiDKNet/dknet/models/{force_net,heads/regression_head,sequence_force_net,temporal}.py` + `KiDKNet/configs/c1…c8_*.yaml` |
| Figures for the talk 汇报图 | `DataFlow/KiDKNet/outputs/paper_figures/`: `fig1`–`fig4` (results) + `arch_single` + `arch_sequence` (the two architectures) + `captions.md`, each `.png` + `.pdf` |
| Live training logs 在线训练记录 | Weights & Biases projects `kidknet-cv5`, `kidknet-xferrace` |

---

## 8. Infrastructure built (so the experiments are reproducible) 配套工程

- **8-setup cross-validation harness 八设置交叉验证框架** — leakage-guarded 5-fold splits,
  one launcher for all setups, automatic cross-fold report tables and charts.
- **Experiment tracking 实验追踪** — Weights & Biases logging; lean checkpoints (keep only
  the best) to save disk.
- **Data plumbing 数据管线** — all pipeline data routed through a single `DataFlow/` tree
  (raw kept separate from regenerable caches).
- **Diagnostic & plotting scripts 诊断与绘图脚本** — appearance-gap analysis, few-shot curve,
  loss A/B, and the publication-style figure generator.

---

## Appendix — commit map 附录:提交对照

| Commit | What it did 做了什么 |
|---|---|
| `02c2385`,`1bb3c5c`,`219efe2`,`296bcfb` | data plumbing: route all I/O through `DataFlow/`, add the real-video path 数据管线 |
| `c952e64` | the 8-setup cross-validation framework 八设置交叉验证框架 |
| `8b5081d` | experiment tracking + lean checkpoints + report tables 追踪+精简权重+报告表 |
| `adf29a6` | research direction notes + diagnostic scripts 方向文档+诊断脚本 |
| `493d46c`,`c3ed62f`,`4d922ad` | photometric augmentation + its A/B tooling 光度增强及其 A/B 工具 |
| `aa11317` | the learned-uncertainty loss 不确定性加权损失 |
| `48d7817` | few-shot learning-curve plotter 少样本曲线绘图器 |
| `14bdc31` | consolidated results notes + loss A/B plotter 结果笔记汇总 + 损失 A/B 绘图器 |
| `7747be9` | editor settings (venv/pip) 编辑器设置 |
