#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FusionOne AI / FusionOne AI Tools 镜像命名生成与校验。

规范来源：image-release skill（同目录 SKILL.md），2026-09-09 按规范修订版对齐：
- 时间戳统一 14 位（yyyyMMddHHmmss，年月日时分秒）。规范修订版示例已全 14 位；
  custom 旧例 vllm_omni_minimax_h3_a3_20260806.tgz 的 8 位为旧例存量。
- special 模型段 = 开源 tag 原样小写：取社区镜像 tag 的模型标识部分，保留点与
  横线（tgz 阶段横线统一转下划线），不做去横线归并。
  例：quay.io/ascend/vllm-ascend:glm5.2-a3 -> 模型段 glm5.2 + 卡型 a3；
      vllm/vllm-openai:deepseekv4-flash-vision -> deepseekv4-flash-vision
      （tgz: deepseekv4_flash_vision）。
  无社区 tag 的模型按团队惯用标识（参照 glm5.2：名称与版本号间不加横线）。
  旧"去横线归并"口径（deepseekv4flashvision）2026-09-09 作废。
- special 卡型段：NPU 必带。GPU 分两种（2026-09-15 口径）：通用 GPU 镜像
  （不针对特定卡型）不带卡型段——沿用 2026-09-09 口径与规范修订版 GPU 示例
  Wings_vllm_deepseekv4_flash_vision_20260904093929_x86_64.tgz；卡型专用镜像
  （只适用于某一卡型，如含 sm120 补丁仅适用 RTX PRO 5000 的镜像）必带卡型段，
  插在模型段与时间戳之间（wings-vllm:<模型>-<卡型>-<时间戳>）。
  09-02"全平台必带卡型"口径作废，此前 *_h20_* 归档为旧口径存量、不返工。
  generic 维持：NPU 标卡型、GPU 标 cuda 版本（字面量 cu<版本>，如 cu130）。
- custom（非 wings）：<引擎名>_<模型标识>_<卡型>_<时间戳>.tgz，全小写、
  模型标识保留横线（minimax-h3）、卡型段必带、无架构段。
- 卡型段统一用卡名称小写、不带显存大小（2026-09-02 口径）：
  h20 / a3 / a2 / l20 ...；h20-141g、910c-64g 等带显存写法拒绝。

用法：
  python gen_image_name.py special --engine wings-vllm-ascend --model glm5.2 --card a3 --arch aarch64
  python gen_image_name.py special --engine wings-vllm --model deepseekv4-flash-vision --arch x86_64
  python gen_image_name.py generic --engine wings-vllm-ascend --version v0.23.0rc1 --card a3 --arch aarch64
  python gen_image_name.py generic --engine wings-vllm-ascend --version nightly-releases-v0.25.1rc --card a3 --arch aarch64
  python gen_image_name.py generic --engine wings-vllm --version v0.28.0 --cuda cu130 --arch x86_64
  python gen_image_name.py custom  --engine vllm-omni --model minimax-h3 --card a3

输出：镜像 tag / tgz 文件名 / 示例归档绝对路径 / 导出命令，供直接复制。
命名违规时以退出码 2 拒绝输出——宁可报错，不出错名。
"""
import argparse
import re
import sys
from datetime import datetime

ARCHES = ("aarch64", "x86_64")

# 卡型段 = 卡名称小写、不带显存（2026-09-02 口径），以本表为准。
# 启用新卡型：先加本表，再按字典义务回写 kb/dict/cards.yaml。
CARDS = ("a3", "a5", "a2", "h20", "l20", "rtxpro5000", "nrp0500")


def fail(msg):
    print(f"[命名违规] {msg}", file=sys.stderr)
    sys.exit(2)


def check(cond, msg):
    if not cond:
        fail(msg)


def norm_engine_tgz(engine, wings):
    # tgz 引擎段：中划线转下划线；wings 系列首字母大写其余小写，自定义全小写
    seg = engine.lower().replace("-", "_")
    return seg[0].upper() + seg[1:] if wings else seg


def main():
    p = argparse.ArgumentParser(description="FusionOne AI 镜像命名生成与校验")
    p.add_argument("category", choices=["special", "generic", "custom"],
                   help="special=特殊镜像(带开源tag) generic=通用/收编镜像(带引擎版本) custom=自定义引擎(非wings)")
    p.add_argument("--engine", required=True,
                   help="引擎段，如 wings-vllm-ascend / wings-vllm / vllm-omni")
    p.add_argument("--model", help="开源 tag / 模型标识（special/custom 必填）：取社区镜像 tag 的模型标识"
                                   "部分原样传入（自动小写化，保留点与横线）；无社区 tag 时按团队惯用标识")
    p.add_argument("--version", help="引擎版本（generic 必填），如 v0.23.0rc1 / nightly-releases-v0.25.1rc")
    p.add_argument("--cuda", help="CUDA 版本段（generic 且 GPU 时必填），字面量 cu<版本> 如 cu130")
    p.add_argument("--card", help="卡型段：卡名称小写不带显存（h20/a3/a2/l20/rtxpro5000...）。"
                                  "special NPU 必填；special GPU 通用镜像禁填、卡型专用镜像必填；"
                                  "generic NPU 必填；custom 必填")
    p.add_argument("--arch", choices=ARCHES,
                   help="uname -m 实测值（wings 镜像 tgz 带架构段，必填；custom 无架构段）")
    p.add_argument("--timestamp", help="覆盖时间戳（默认当前时刻，14 位 yyyyMMddHHmmss）")
    args = p.parse_args()

    ts = args.timestamp or datetime.now().strftime("%Y%m%d%H%M%S")
    check(re.fullmatch(r"\d{14}", ts), f"时间戳须 14 位（年月日时分秒），得到: {ts}")

    engine = args.engine.lower()
    wings = engine.startswith("wings-")
    if args.category in ("special", "generic"):
        check(wings, f"{args.category} 引擎段须 wings- 开头，得到: {engine}（非 wings 用 custom）")
    else:
        check(not wings, f"wings 开头请用 special/generic，得到: {engine}")
        check(not args.arch, "custom 镜像无架构段，去掉 --arch")

    card = args.card.lower() if args.card else None
    if card:
        check(not re.search(r"-\d+g$", card),
              f"卡型段不带显存大小，直接用卡名称: {card} -> {re.sub(r'-\d+g$', '', card)}")
        check(card in CARDS,
              f"卡型段不在内置卡型表: {card}（表: {'/'.join(CARDS)}；新卡型先加 gen_image_name.py 内置表，"
              f"再回写 kb/dict/cards.yaml）")

    # wings 引擎段判定 NPU/GPU：含 ascend 为 NPU。special：NPU 必带卡型；
    # GPU 通用镜像不带卡型（2026-09-09 口径沿用）、卡型专用镜像必带卡型
    # （2026-09-15 口径，插在模型段与时间戳之间）。generic：NPU 标卡型、GPU 标 cuda。
    if wings:
        is_npu = "ascend" in engine
        if args.category == "special":
            if is_npu:
                check(card, "special NPU 必须 --card（卡名称不带显存，如 a3/a2）")
            # special GPU：--card 可选——通用镜像不带、卡型专用镜像必带（调用方按镜像适用性判断）
            check(not args.cuda, "special 镜像无 cuda 段")
        elif is_npu:
            check(card, f"NPU 引擎 {engine} 必须 --card（如 a3/a2）")
            check(not args.cuda, "NPU 镜像无 cuda 段")
        else:
            check(not card, f"GPU 引擎 {engine} 的 generic 镜像标 cuda 不标卡型，去掉 --card")
            check(args.cuda, f"GPU 引擎 {engine} 的 generic 镜像必须 --cuda（如 cu130）")

    if args.cuda:
        cuda = args.cuda.lower()
        check(re.fullmatch(r"cu\d+", cuda),
              f"cuda 段字面量为 cu<版本>（如 cu130），得到: {args.cuda}")

    if args.category == "special":
        check(args.model, "special 必须 --model（开源 tag 的模型标识部分，如 glm5.2 / deepseekv4-flash-vision）")
        check(args.arch, "special 必须 --arch（tgz 带架构段）")
        model = args.model.lower()
        check(re.fullmatch(r"[a-z0-9._-]+", model), f"模型段含非法字符: {model}")
        segs = [model] + ([card] if card else []) + [ts]
        tag_tail = "-".join(segs)
        tgz_mid = "_".join(segs + [args.arch])
    elif args.category == "generic":
        check(args.version, "generic 必须 --version")
        check(args.arch, "generic 必须 --arch（tgz 带架构段）")
        version = args.version.lower()
        check(re.fullmatch(r"[a-z0-9._-]+", version), f"版本段含非法字符: {version}")
        segs = [version]
        if card:
            segs.append(card)                 # NPU: 版本-卡型-时间戳
        elif args.cuda:
            segs.append(args.cuda.lower())    # GPU: 版本-cuda版本-时间戳
        else:
            fail("generic 须给 --card（NPU）或 --cuda（GPU）")
        segs.append(ts)
        tag_tail = "-".join(segs)
        tgz_mid = "_".join(segs + [args.arch])
    else:  # custom：<引擎名>_<模型标识>_<卡型>_<时间戳>.tgz，全小写、无架构段
        check(args.model, "custom 必须 --model")
        check(card, "custom 必须 --card（规范格式 <引擎名>_<模型标识>_<卡型>_<时间戳>.tgz）")
        model = args.model.lower()
        check(re.fullmatch(r"[a-z0-9._-]+", model), f"模型标识含非法字符: {model}")
        segs = [model, card, ts]
        tag_tail = "-".join(segs)
        tgz_mid = "_".join(segs)

    tag = f"{engine}:{tag_tail}"
    # tgz 段内横线一律转下划线（分隔符只保留下划线；tag 保留横线）
    tgz = f"{norm_engine_tgz(engine, wings)}_{tgz_mid.replace('-', '_')}.tgz"

    check(re.fullmatch(r"[a-z0-9./:_\-]+", tag), f"tag 含非法字符: {tag}")
    check(re.fullmatch(r"[A-Za-z0-9._\-]+\.tgz", tgz), f"tgz 文件名含非法字符: {tgz}")

    print(f"镜像 tag   : {tag}")
    print(f"tgz 文件名 : {tgz}")
    print(f"示例归档路径: 192.0.2.75:/data/personal/0day/image/{engine}-{tag_tail}/{tgz}")
    print(f"导出命令   : docker save {tag} | pigz > {tgz}")


if __name__ == "__main__":
    main()
