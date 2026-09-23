"""Optional end-to-end material -- never committed (see ``.gitignore``).

真实素材（PE 规格 / 测试程序 / datalog）含料号与实测值，**不入库**。
本地想跑真实数据端到端用例时，把素材目录指进来：

    set LIMIT_COMPARE_MATERIAL_DIR=D:\\material      # Windows
    export LIMIT_COMPARE_MATERIAL_DIR=/data/material  # Linux / macOS
    set LIMIT_COMPARE_PE_DIR=D:\\material\\<PE 规格目录>   # 可选，精确指定
    python -m pytest -q

未设置该变量时，所有 ``real_*`` 用例自动 skip，仓库开箱即可通过全量测试。
素材按扩展名定位，因此这里不出现任何料号。
"""

import glob
import os

_REPO_MATERIAL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Material"
)

# 优先级：环境变量 > 仓库内 Material/（本身已被 .gitignore 排除）> 无素材
MATERIAL_DIR = (
    os.environ.get("LIMIT_COMPARE_MATERIAL_DIR")
    or (_REPO_MATERIAL if os.path.isdir(_REPO_MATERIAL) else "")
)


def _first(pattern):
    """素材目录下第一个匹配 *pattern* 的文件；无素材或未命中则 None。"""
    if not MATERIAL_DIR:
        return None
    hits = sorted(glob.glob(os.path.join(MATERIAL_DIR, "**", pattern), recursive=True))
    return hits[0] if hits else None


def real_pds():
    """ETS88 程序 ``*.pds``。"""
    return _first("*.pds")


def real_cpts():
    """CTA8290 程序 ``*_FT_*.cpts``。"""
    return _first("*_FT_*.cpts")


def real_pe_dir():
    """PE 规格目录：取含 ``*.xlsx`` 最多的目录（跳过 Excel ``~$`` 锁文件）。

    素材目录通常是 PE 十份 Excel + Datalog 混放，根目录可能只有一两张
    汇总表，所以按「xlsx 最多的那一层」判定。想精确指定时用
    ``LIMIT_COMPARE_PE_DIR`` 覆盖。
    """
    override = os.environ.get("LIMIT_COMPARE_PE_DIR", "")
    if override and os.path.isdir(override):
        return override
    if not MATERIAL_DIR:
        return None
    best, best_n = None, 0
    for root, _dirs, files in os.walk(MATERIAL_DIR):
        n = sum(
            1
            for f in files
            if not f.startswith("~$") and f.lower().endswith((".xlsx", ".xlsm"))
        )
        if n > best_n:
            best, best_n = root, n
    return best


def has(*paths):
    """全部路径非空且存在时为 True。"""
    return all(p and os.path.exists(p) for p in paths)
