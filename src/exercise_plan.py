"""每日锻炼计划 · 核心算法验证脚本。

本脚本是《每日锻炼计划功能规划》文档的配套可运行代码，用于校验文档中
出现的所有数值（一周模板、双进阶负荷表、周容量、训练时长、心率区间、ACWR）。

运行::

    python src/exercise_plan.py

依赖: 仅使用标准库。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 肌群 -> 大肌群归并（容量按大肌群统计，避免小肌群划分过细导致误报）
MUSCLE_GROUP: dict[str, str] = {
    "胸": "胸",
    "背": "背",
    "肩": "肩",
    "后肩": "肩",
    "三头": "手臂",
    "二头": "手臂",
    "股四头": "股四头",
    "腘绳": "后链",
    "臀": "后链",
    "后链": "后链",
    "小腿": "小腿",
    "核心": "核心",
}

# 经验水平 -> {大肌群: (每周组数下限, 上限)}
LEVEL_VOLUME_TARGET: dict[str, dict[str, tuple[int, int]]] = {
    "新手": {"胸": (6, 12), "背": (6, 12), "肩": (5, 10), "手臂": (4, 8),
             "股四头": (8, 14), "后链": (6, 10), "小腿": (4, 8), "核心": (4, 8)},
    "中级": {"胸": (10, 16), "背": (10, 16), "肩": (8, 14), "手臂": (6, 12),
             "股四头": (12, 18), "后链": (8, 14), "小腿": (6, 12), "核心": (6, 12)},
    "进阶": {"胸": (14, 22), "背": (14, 22), "肩": (10, 18), "手臂": (8, 14),
             "股四头": (16, 24), "后链": (10, 18), "小腿": (8, 14), "核心": (8, 14)},
}

# 中周期 = 3 周递增 + 1 周减载；块末加片幅度按经验水平区分（双进阶）
LEVEL_BLOCK_INCREMENT: dict[str, float] = {
    "新手": 0.05,      # 新手每个中周期 +5%
    "中级": 0.025,     # 中级每个中周期 +2.5%
    "进阶": 0.0125,    # 进阶每个中周期 +1.25%
}

BLOCK_WEEKS = 4              # 中周期长度（周）
DELOAD_LOAD_FACTOR = 0.70    # 减载周负荷系数
DELOAD_SET_FACTOR = 0.60     # 减载周组数系数
PLATE_STEP = 2.5             # 最小配重片增量（kg）


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Exercise:
    """单个动作。"""

    name: str
    muscle: str          # 主要目标肌群
    sets: int            # 基础组数（常规周）
    reps_low: int        # 次数区间下限（块内第 1 周目标）
    reps_high: int       # 次数区间上限（块内第 3 周目标）
    rest_sec: int        # 组间休息（秒）
    base_load: float     # 基准负荷 kg（自重动作记 0）
    set_sec: int = 45    # 单组净耗时（秒）

    @property
    def reps_label(self) -> str:
        return f"{self.reps_low}-{self.reps_high}"


@dataclass(frozen=True)
class Session:
    """一次训练课。"""

    weekday: int                       # 0=周一 … 6=周日
    name: str
    warmup_min: int
    cooldown_min: int
    exercises: list[Exercise] = field(default_factory=list)

    @property
    def total_sets(self) -> int:
        return sum(e.sets for e in self.exercises)


@dataclass(frozen=True)
class Profile:
    """训练者画像。"""

    age: int
    level: str = "中级"
    days_per_week: int = 4
    session_minutes: int = 70
    equipment: str = "健身房"
    bodyweight_kg: float = 70.0


@dataclass(frozen=True)
class Prescription:
    """某周某动作的处方。"""

    load: float          # 负荷 kg
    reps: int            # 目标次数
    set_factor: float    # 组数系数（减载 0.6，常规 1.0）


# ---------------------------------------------------------------------------
# 默认一周模板：上下肢分化（Upper / Lower x2，4 训练日 + 3 恢复日）
# ---------------------------------------------------------------------------


def default_week() -> list[Session]:
    """返回默认一周模板（周一 / 周二 / 周四 / 周六训练）。"""
    return [
        Session(
            weekday=0, name="上肢推（胸 / 肩 / 三头）", warmup_min=8, cooldown_min=5,
            exercises=[
                Exercise("杠铃卧推", "胸", 4, 6, 8, 150, 60.0),
                Exercise("上斜哑铃卧推", "胸", 4, 8, 10, 120, 22.5),
                Exercise("双杠臂屈伸（负重）", "胸", 3, 8, 10, 90, 10.0),
                Exercise("坐姿哑铃推举", "肩", 3, 8, 10, 120, 17.5),
                Exercise("绳索侧平举", "肩", 3, 12, 15, 60, 7.5),
                Exercise("三头绳索下压", "三头", 3, 10, 12, 60, 25.0),
            ],
        ),
        Session(
            weekday=1, name="下肢 A（股四头主导）", warmup_min=8, cooldown_min=5,
            exercises=[
                Exercise("杠铃深蹲", "股四头", 4, 6, 8, 180, 80.0),
                Exercise("罗马尼亚硬拉", "腘绳", 3, 8, 10, 150, 60.0),
                Exercise("腿举", "股四头", 3, 10, 12, 120, 120.0),
                Exercise("坐姿腿屈伸", "股四头", 3, 12, 15, 60, 45.0),
                Exercise("站姿提踵", "小腿", 4, 12, 15, 60, 40.0),
                Exercise("卷腹", "核心", 3, 12, 15, 60, 0.0),
            ],
        ),
        Session(
            weekday=3, name="上肢拉（背 / 后肩 / 二头）", warmup_min=8, cooldown_min=5,
            exercises=[
                Exercise("引体向上（辅助）", "背", 4, 6, 10, 150, 0.0),
                Exercise("坐姿绳索划船", "背", 4, 8, 10, 120, 55.0),
                Exercise("单臂哑铃划船", "背", 3, 10, 12, 90, 27.5),
                Exercise("绳索面拉", "后肩", 3, 12, 15, 60, 20.0),
                Exercise("哑铃弯举", "二头", 3, 10, 12, 60, 12.5),
                Exercise("悬垂举腿", "核心", 3, 10, 15, 60, 0.0),
            ],
        ),
        Session(
            weekday=5, name="下肢 B（髋主导 / 后链）", warmup_min=8, cooldown_min=5,
            exercises=[
                Exercise("杠铃硬拉", "后链", 4, 5, 6, 180, 100.0),
                Exercise("臀推", "臀", 4, 8, 10, 120, 80.0),
                Exercise("坐姿腿弯举", "腘绳", 3, 10, 12, 60, 40.0),
                Exercise("保加利亚分腿蹲", "股四头", 3, 10, 12, 90, 20.0),
                Exercise("坐姿提踵", "小腿", 3, 12, 15, 60, 40.0),
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# 算法
# ---------------------------------------------------------------------------


def round_to_plate(load: float, step: float = PLATE_STEP) -> float:
    """把负荷取整到最小配重片的整数倍。"""
    return round(round(load / step) * step, 2)


def prescribe(exercise: Exercise, week_index: int, level: str = "中级") -> Prescription:
    """双进阶处方：块内先加次数、块末加配重、第 4 周减载。

    中周期内第 1/2/3 周负荷不变、次数从区间下限递增到上限；
    第 4 周负荷 -30%、组数 -40% 用于减载；进入下一个中周期时基准负荷按经验水平上调。

    Args:
        exercise: 动作定义（含基准负荷与次数区间）。
        week_index: 训练计划中的周序号，0 起。
        level: 经验水平，决定块间负荷递增率。

    Returns:
        ``Prescription(负荷 kg, 目标次数, 组数系数)``。
    """
    block, week_in_block = divmod(week_index, BLOCK_WEEKS)
    block_base = round_to_plate(exercise.base_load * (1 + LEVEL_BLOCK_INCREMENT[level]) ** block)

    if week_in_block == BLOCK_WEEKS - 1:                       # 减载周：降负荷、降组数、保次数
        return Prescription(round_to_plate(block_base * DELOAD_LOAD_FACTOR),
                            exercise.reps_low, DELOAD_SET_FACTOR)

    reps = min(exercise.reps_low + week_in_block, exercise.reps_high)
    return Prescription(block_base, reps, 1.0)


def session_minutes(session: Session) -> int:
    """估算单次训练时长（分钟）= 热身 + Σ组(净耗时 + 组间歇) + 拉伸。"""
    work_sec = sum(e.sets * (e.set_sec + e.rest_sec) for e in session.exercises)
    return round(session.warmup_min + work_sec / 60 + session.cooldown_min)


def weekly_volume(sessions: Iterable[Session], set_factor: float = 1.0) -> dict[str, int]:
    """统计一周各**大肌群**的训练组数。"""
    volume: dict[str, int] = {}
    for s in sessions:
        for e in s.exercises:
            group = MUSCLE_GROUP[e.muscle]
            volume[group] = volume.get(group, 0) + round(e.sets * set_factor)
    return dict(sorted(volume.items(), key=lambda kv: -kv[1]))


def train_rest_split(sessions: list[Session]) -> list[tuple[str, str]]:
    """返回一周七天的（星期, 安排）列表。"""
    names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    by_day = {s.weekday: s.name for s in sessions}
    recovery = {
        2: "恢复：Zone 2 有氧 30 min 或休息",
        4: "恢复：Zone 2 有氧 25 min 或休息",
        6: "主动恢复：快走 30 min + 全身拉伸",
    }
    return [(names[i], f"训练 · {by_day[i]}" if i in by_day else recovery[i]) for i in range(7)]


def hrmax_tanaka(age: int) -> float:
    """Tanaka 公式估算最大心率（比 220-age 更贴合中老年人群）。"""
    return 208 - 0.7 * age


def heart_rate_zones(age: int) -> dict[str, tuple[int, int]]:
    """按最大心率百分比给出训练心率区间（bpm）。"""
    hrmax = hrmax_tanaka(age)
    bands = {
        "Zone 1 恢复": (0.50, 0.60),
        "Zone 2 有氧基础": (0.60, 0.70),
        "Zone 3 节奏": (0.70, 0.80),
        "Zone 4 阈值": (0.80, 0.90),
        "Zone 5 最大摄氧": (0.90, 1.00),
    }
    return {k: (round(hrmax * lo), round(hrmax * hi)) for k, (lo, hi) in bands.items()}


def acwr(acute_load: float, chronic_load: float) -> float:
    """急慢性负荷比 = 最近 7 天负荷 / 最近 28 天平均周负荷。0.8–1.3 为安全区。"""
    if chronic_load <= 0:
        raise ValueError("慢性负荷必须为正数")
    return round(acute_load / chronic_load, 2)


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------


def print_week_template(profile: Profile) -> None:
    """打印一周 7 天安排与训练时长估算。"""
    sessions = default_week()
    print("=" * 76)
    print("【1】默认一周模板（4 训练日 + 3 恢复日）")
    print("=" * 76)
    for day, plan in train_rest_split(sessions):
        print(f"{day}  {plan}")
    print()
    print(f"{'训练日':<28}{'组数':>6}{'时长(估)':>12}")
    for s in sessions:
        flag = "  ⚠ 超时" if session_minutes(s) > profile.session_minutes else ""
        print(f"{s.name:<28}{s.total_sets:>6}{session_minutes(s):>8} min{flag}")
    print()


def print_progression(profile: Profile, weeks: int = 12) -> None:
    """打印 12 周双进阶表（负荷 / 次数 / 组数）。"""
    keys = [e.name for s in default_week() for e in s.exercises][:3]
    print("=" * 76)
    print(f"【2】双进阶负荷表（12 周 = 3 个中周期，经验水平：{profile.level}，负荷单位 kg）")
    print("=" * 76)
    print(f"{'周':<5}{'阶段':<12}{'深蹲':>8}{'卧推':>8}{'硬拉':>8}{'次数目标':>12}{'组数系数':>10}")
    execs = {"深蹲": (80.0, 6, 8), "卧推": (60.0, 6, 8), "硬拉": (100.0, 5, 6)}
    for w in range(weeks):
        week_no = w % BLOCK_WEEKS + 1
        phase = "减载" if week_no == BLOCK_WEEKS else f"递增 W{week_no}"
        loads, reps, factor = [], set(), None
        for base, rl, rh in execs.values():
            ex = Exercise("x", "x", 4, rl, rh, 120, base)
            p = prescribe(ex, w, profile.level)
            loads.append(p.load)
            reps.add(p.reps)
            factor = p.set_factor
        reps_txt = "/".join(str(r) for r in sorted(reps))
        print(f"W{w + 1:<4}{phase:<12}" + "".join(f"{v:>8.1f}" for v in loads)
              + f"{reps_txt:>12}{factor:>10.1f}")
    print()


def print_volume(profile: Profile) -> None:
    """打印周容量与目标区间校验（减载周不参与区间判定）。"""
    sessions = default_week()
    vol = weekly_volume(sessions)
    deload = weekly_volume(sessions, DELOAD_SET_FACTOR)
    target = LEVEL_VOLUME_TARGET[profile.level]
    print("=" * 76)
    print(f"【3】周容量校验（经验水平：{profile.level}，常规周按大肌群判定）")
    print("=" * 76)
    print(f"{'大肌群':<10}{'常规周':>8}{'目标区间':>12}{'减载周':>8}   判定")
    for group, sets in vol.items():
        lo, hi = target[group]
        verdict = "✔ 区间内" if lo <= sets <= hi else ("⚠ 低于下限" if sets < lo else "⚠ 高于上限")
        print(f"{group:<10}{sets:>8}{f'{lo}-{hi}':>12}{deload.get(group, 0):>8}   {verdict}")
    print(f"\n单周总组数：{sum(vol.values())} 组；减载周 {sum(deload.values())} 组"
          f"（{sum(deload.values()) / sum(vol.values()):.0%}，符合 -40% 目标）")
    print()


def print_heart_rate(profile: Profile) -> None:
    """打印心率区间与有氧处方。"""
    print("=" * 76)
    print(f"【4】心率区间（Tanaka 公式，年龄 {profile.age}，HRmax = {hrmax_tanaka(profile.age):.0f} bpm）")
    print("=" * 76)
    for zone, (lo, hi) in heart_rate_zones(profile.age).items():
        print(f"{zone:<16}{lo:>5} –{hi:>5} bpm")
    print("\n有氧处方：Zone 2 累计 150 min/周（WHO 建议），可拆为 5 x 30 min，训练日不叠加")
    print()


def print_acwr() -> None:
    """打印 ACWR 安全区示例。"""
    print("=" * 76)
    print("【5】负荷监控（ACWR，单次课 sRPE = RPE 7 x 70 min = 490，常规周负荷 = 1960）")
    print("=" * 76)
    chronic = 4 * 490
    for label, factor in (("按计划推进", 1.00), ("突然加量 40%", 1.40), ("减载周 -40%", 0.60)):
        ratio = acwr(chronic * factor, chronic)
        verdict = "超载风险 ⚠" if ratio > 1.3 else ("负荷回落（减载期正常）" if ratio < 0.8 else "安全区 ✔")
        print(f"{label:<14}ACWR = {ratio:<6}{verdict}")
    print()


def main() -> None:
    """验证脚本入口。"""
    profile = Profile(age=30, level="中级", days_per_week=4, session_minutes=70)
    print_week_template(profile)
    print_progression(profile)
    print_volume(profile)
    print_heart_rate(profile)
    print_acwr()


if __name__ == "__main__":
    main()
