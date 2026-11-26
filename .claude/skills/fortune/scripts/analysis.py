"""八字确定性分析：旺衰打分、喜用神、穷通宝典调候、刑冲合害、神煞。
全部查表/计算，解读时以此为准，不让模型凭感觉判断。"""

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"
GAN_WX = dict(zip(GAN, "木木火火土土金金水水"))
ZHI_WX = dict(zip(ZHI, "水土木木土火火土金金土水"))
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}  # 我生
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}  # 我克
HIDE_W = [0.6, 0.3, 0.1]  # 本气/中气/余气

# 穷通宝典 调候用神（通行摘要，按日干 × 月支，寅月起）
TIAOHOU = {
    "甲": ["丙癸", "庚丙丁戊己", "庚丁壬", "癸丁庚", "癸丁庚", "癸丁庚", "庚丁壬", "庚丁丙", "庚甲丁壬癸", "庚丁丙戊", "丁庚丙", "丁庚丙"],
    "乙": ["丙癸", "丙癸", "癸丙戊", "癸", "癸丙", "癸丙", "丙癸己", "癸丙丁", "癸辛", "丙戊", "丙", "丙"],
    "丙": ["壬庚", "壬己", "壬甲", "壬癸庚", "壬庚", "壬庚", "壬戊", "壬癸", "甲壬", "甲戊庚壬", "壬戊己", "壬甲"],
    "丁": ["甲庚", "庚甲", "甲庚", "甲庚", "壬庚癸", "甲壬庚", "甲庚丙戊", "甲庚丙戊", "甲庚戊", "甲庚", "甲庚", "甲庚"],
    "戊": ["丙甲癸", "丙甲癸", "甲丙癸", "甲丙癸", "壬甲丙", "癸丙甲", "丙癸甲", "丙癸", "甲丙癸", "甲丙", "丙甲", "丙甲"],
    "己": ["丙庚甲", "甲癸丙", "丙癸甲", "癸丙", "癸丙", "癸丙", "丙癸", "丙癸", "甲丙癸", "丙甲戊", "丙甲戊", "丙甲戊"],
    "庚": ["戊甲壬丙丁", "丁甲庚丙", "甲丁壬癸", "壬戊丙丁", "壬癸", "丁甲", "丁甲", "丁甲丙", "甲壬", "丁丙", "丁甲丙", "丙丁甲"],
    "辛": ["己壬庚", "壬甲", "壬甲", "壬甲癸", "壬己癸", "壬庚甲", "壬甲戊", "壬甲", "壬甲", "壬丙", "丙戊壬甲", "丙壬戊己"],
    "壬": ["庚丙戊", "戊辛庚", "甲庚", "壬辛庚癸", "癸庚辛", "辛甲", "戊丁", "甲庚", "甲丙", "戊丙庚", "戊丙", "丙丁甲"],
    "癸": ["辛丙", "庚辛", "丙辛甲", "辛", "庚辛壬癸", "庚辛壬癸", "丁", "辛丙", "辛甲壬癸", "庚辛戊丁", "丙辛", "丙丁"],
}
MONTH_ORDER = "寅卯辰巳午未申酉戌亥子丑"

GAN_HE = {frozenset("甲己"): "土", frozenset("乙庚"): "金", frozenset("丙辛"): "水", frozenset("丁壬"): "木", frozenset("戊癸"): "火"}
GAN_CHONG = [set("甲庚"), set("乙辛"), set("丙壬"), set("丁癸")]
LIU_HE = {frozenset("子丑"): "土", frozenset("寅亥"): "木", frozenset("卯戌"): "火", frozenset("辰酉"): "金", frozenset("巳申"): "水", frozenset("午未"): "火土"}
LIU_CHONG = [set(x) for x in ["子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥"]]
LIU_HAI = [set(x) for x in ["子未", "丑午", "寅巳", "卯辰", "申亥", "酉戌"]]
SAN_HE = {"申子辰": "水", "亥卯未": "木", "寅午戌": "火", "巳酉丑": "金"}
SAN_HUI = {"寅卯辰": "木", "巳午未": "火", "申酉戌": "金", "亥子丑": "水"}
XING = [("寅巳申", "无恩之刑"), ("丑戌未", "恃势之刑"), ("子卯", "无礼之刑")]
ZI_XING = "辰午酉亥"

TIANYI = {"甲": "丑未", "戊": "丑未", "庚": "丑未", "乙": "子申", "己": "子申", "丙": "亥酉", "丁": "亥酉", "辛": "寅午", "壬": "卯巳", "癸": "卯巳"}
WENCHANG = dict(zip(GAN, "巳午申酉申酉亥子寅卯"))
LU = dict(zip(GAN, "寅卯巳午巳午申酉亥子"))
YANGREN = {"甲": "卯", "丙": "午", "戊": "午", "庚": "酉", "壬": "子"}
GROUP = {"申子辰": ("酉", "寅", "辰"), "寅午戌": ("卯", "申", "戌"), "巳酉丑": ("午", "亥", "丑"), "亥卯未": ("子", "巳", "未")}


def _group(z):
    return next(v for k, v in GROUP.items() if z in k)


def strength(gans, zhis, hides, day_gan, month_idx):
    """日主旺衰：同党(比劫+印) vs 异党。月令权重 ×3。"""
    me = GAN_WX[day_gan]
    yin = next(k for k, v in SHENG.items() if v == me)
    score = {w: 0.0 for w in "木火土金水"}
    for i, g in enumerate(gans):
        if i != 2:
            score[GAN_WX[g]] += 1
    for i, hs in enumerate(hides):
        w = 3 if i == month_idx else 1
        for j, h in enumerate(hs):
            score[GAN_WX[h]] += w * HIDE_W[j]
    total = sum(score.values())
    same = score[me] + score[yin]
    pct = round(same / total * 100)
    month_wx = ZHI_WX[zhis[month_idx]]
    de_ling = month_wx in (me, yin)
    if pct >= 80:
        level = "极强（可能从强/专旺格，需人工复核）"
    elif pct >= 55:
        level = "身强"
    elif pct >= 45:
        level = "中和"
    elif pct >= 20:
        level = "身弱"
    else:
        level = "极弱（可能从弱格，需人工复核）"
    shi = SHENG[me]
    cai = KE[me]
    guan = next(k for k, v in KE.items() if v == me)
    if pct >= 80:
        xi, ji = [me, yin], [guan, cai]
    elif pct < 20:
        strongest = max((w for w in score if w not in (me, yin)), key=lambda w: score[w])
        xi, ji = [strongest], [me, yin]
    elif pct >= 50:
        xi, ji = [shi, cai, guan], [me, yin]
    else:
        xi, ji = [yin, me], [guan, cai, shi]
    return {
        "五行力量": {k: round(v, 1) for k, v in score.items()},
        "同党占比": f"{pct}%", "月令": f"{zhis[month_idx]}({month_wx}){'得令' if de_ling else '失令'}",
        "判断": level, "扶抑喜用": xi, "扶抑忌神": ji,
    }


def tiaohou(day_gan, month_zhi):
    return {"调候用神(穷通宝典)": list(TIAOHOU[day_gan][MONTH_ORDER.index(month_zhi)])}


def relations(labels, gans, zhis):
    """labels 与 gans/zhis 一一对应，如 ['年','月','日','时','大运','流年']。"""
    out = []
    n = len(gans)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = gans[i], gans[j]
            p = f"{labels[i]}{labels[j]}"
            if frozenset(a + b) in GAN_HE:
                out.append(f"{p} {a}{b}合(化{GAN_HE[frozenset(a + b)]})")
            if {a, b} in GAN_CHONG:
                out.append(f"{p} {a}{b}冲")
            x, y = zhis[i], zhis[j]
            if frozenset(x + y) in LIU_HE:
                out.append(f"{p} {x}{y}六合")
            if {x, y} in LIU_CHONG:
                out.append(f"{p} {x}{y}相冲")
            if {x, y} in LIU_HAI:
                out.append(f"{p} {x}{y}相害")
            if x == y and x in ZI_XING:
                out.append(f"{p} {x}{x}自刑")
            for k, name in XING:
                if x != y and x in k and y in k:
                    out.append(f"{p} {x}{y}相刑({name})")
    zs = set(zhis)
    for k, wx in SAN_HE.items():
        hit = [c for c in k if c in zs]
        if len(hit) == 3:
            out.append(f"{k}三合{wx}局")
        elif len(hit) == 2 and k[1] in hit:
            out.append(f"{''.join(hit)}半合{wx}局")
    for k, wx in SAN_HUI.items():
        if all(c in zs for c in k):
            out.append(f"{k}三会{wx}方")
    return out


def shensha(gans, zhis):
    day_gan, year_zhi, day_zhi = gans[2], zhis[0], zhis[2]
    names = ["年", "月", "日", "时"][: len(zhis)]
    res = {}

    def mark(name, targets):
        hit = [f"{names[i]}支{z}" for i, z in enumerate(zhis) if z in targets]
        if hit:
            res[name] = hit

    mark("天乙贵人", TIANYI[day_gan] + TIANYI[gans[0]])
    mark("文昌", WENCHANG[day_gan])
    mark("禄神", LU[day_gan])
    if day_gan in YANGREN:
        mark("羊刃", YANGREN[day_gan])
    for base, tag in [(year_zhi, "年"), (day_zhi, "日")]:
        th, ym, hg = _group(base)
        mark(f"桃花(以{tag}支)", th)
        mark(f"驿马(以{tag}支)", ym)
        mark(f"华盖(以{tag}支)", hg)
    return res
