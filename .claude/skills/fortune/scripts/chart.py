#!/usr/bin/env python3
"""八字 + 紫微斗数排盘。算法排盘，不让模型心算。

用法：
  python3 chart.py --date 1990-05-17 --time 09:30 --gender 男 [--lunar [--leap]] [--lng 121.47] [--no-ziwei]

--time 不知道就填 12:00 并加 --no-time（不排时柱、不排紫微）。
--lng 出生地经度，给了就按真太阳时（仅经度修正）校正时辰。
依赖首次运行自动装到 ~/.cache/fortune-skill（pip lunar-python / npm iztro）。
"""
import argparse, datetime as dt, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.expanduser("~/.cache/fortune-skill")
PYLIB, NODEDIR = os.path.join(CACHE, "pylib"), os.path.join(CACHE, "node")


def ensure_deps(need_node):
    if not os.path.isdir(os.path.join(PYLIB, "lunar_python")):
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--target", PYLIB, "lunar-python"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sys.path.insert(0, PYLIB)
    if need_node and not os.path.isdir(os.path.join(NODEDIR, "node_modules", "iztro")):
        os.makedirs(NODEDIR, exist_ok=True)
        subprocess.run(["npm", "i", "--prefix", NODEDIR, "iztro"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", default="12:00")
    ap.add_argument("--gender", required=True, choices=["男", "女"])
    ap.add_argument("--lunar", action="store_true")
    ap.add_argument("--leap", action="store_true")
    ap.add_argument("--lng", type=float)
    ap.add_argument("--no-time", action="store_true")
    ap.add_argument("--no-ziwei", action="store_true")
    a = ap.parse_args()
    use_ziwei = not a.no_ziwei and not a.no_time
    ensure_deps(use_ziwei)
    from lunar_python import Lunar, Solar

    y, m, d = map(int, a.date.split("-"))
    hh, mm = map(int, a.time.split(":"))
    if a.lunar:
        solar = Lunar.fromYmdHms(y, -m if a.leap else m, d, hh, mm, 0).getSolar()
    else:
        solar = Solar.fromYmdHms(y, m, d, hh, mm, 0)
    t = dt.datetime(solar.getYear(), solar.getMonth(), solar.getDay(), solar.getHour(), solar.getMinute())
    note = None
    if a.lng is not None:  # 经度修正：东八区以 120°E 为准，每度 4 分钟
        t = t + dt.timedelta(minutes=(a.lng - 120) * 4)
        note = f"真太阳时(经度修正) {t:%Y-%m-%d %H:%M}"
    solar = Solar.fromYmdHms(t.year, t.month, t.day, t.hour, t.minute, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    ec.setSect(1)  # 23 点后算次日（早子时换日）

    pillars = {}
    for k, n in [("Year", "年柱"), ("Month", "月柱"), ("Day", "日柱"), ("Time", "时柱")]:
        if k == "Time" and a.no_time:
            continue
        g = lambda f: getattr(ec, f"get{k}{f}")()
        pillars[n] = {
            "干支": g(""), "天干十神": "日主" if k == "Day" else g("ShiShenGan"),
            "藏干": g("HideGan"), "地支十神": g("ShiShenZhi"), "纳音": g("NaYin"),
            "五行": g("WuXing"), "十二长生": g("DiShi"), "空亡": g("XunKong"),
        }
    wx = {"金": 0, "木": 0, "水": 0, "火": 0, "土": 0}
    for p in pillars.values():
        for c in p["五行"]:
            wx[c] += 1

    yun = ec.getYun(1 if a.gender == "男" else 0)
    now_year = dt.date.today().year
    dayun = []
    for dy in yun.getDaYun()[1:10]:
        item = {"干支": dy.getGanZhi(), "起止": f"{dy.getStartYear()}-{dy.getEndYear()}",
                "岁": f"{dy.getStartAge()}-{dy.getEndAge()}"}
        if dy.getStartYear() <= now_year <= dy.getEndYear():
            item["当前"] = True
        dayun.append(item)
    liunian = [{"年": ny, "干支": Solar.fromYmd(ny, 6, 1).getLunar().getYearInGanZhiExact()}
               for ny in range(now_year, now_year + 3)]

    out = {
        "输入": {"阳历": solar.toYmdHms(), "农历": lunar.toString(), "性别": a.gender, "备注": note},
        "八字": {
            "四柱": " ".join(p["干支"] for p in pillars.values()),
            "日主": ec.getDayGan() + ec.getDayWuXing()[0],
            "生肖": lunar.getYearShengXiaoExact(), "节气区间": f"{lunar.getPrevJieQi().getName()}后",
            "柱": pillars, "五行个数(干支各计)": wx,
            "胎元": ec.getTaiYuan(), "命宫": ec.getMingGong(), "身宫": ec.getShenGong(),
            "起运": f"出生后{yun.getStartYear()}年{yun.getStartMonth()}个月{yun.getStartDay()}天起运",
            "大运": dayun, "流年": liunian,
        },
    }
    if use_ziwei:
        hour_idx = 0 if t.hour == 0 else (12 if t.hour == 23 else (t.hour + 1) // 2)
        r = subprocess.run(
            ["node", os.path.join(HERE, "ziwei.js"), f"{t.year}-{t.month}-{t.day}", str(hour_idx), a.gender, "solar"],
            capture_output=True, text=True, env={**os.environ, "NODE_PATH": os.path.join(NODEDIR, "node_modules")})
        out["紫微斗数"] = json.loads(r.stdout) if r.returncode == 0 else {"error": r.stderr[-500:]}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
