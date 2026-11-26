// 紫微斗数排盘（iztro）。用法：node ziwei.js <YYYY-M-D> <时辰序号0-12> <男|女> <solar|lunar> [leap]
const { astro } = require('iztro');
const [date, hourIdx, gender, kind, leap] = process.argv.slice(2);
const idx = parseInt(hourIdx, 10);
const a = kind === 'lunar'
  ? astro.byLunar(date, idx, gender, leap === 'leap', true, 'zh-CN')
  : astro.bySolar(date, idx, gender, true, 'zh-CN');
const now = new Date();
const h = a.horoscope(`${now.getFullYear()}-${now.getMonth() + 1}-${now.getDate()}`);
const star = (s) => s.name + (s.brightness ? `(${s.brightness})` : '') + (s.mutagen ? `化${s.mutagen}` : '');
console.log(JSON.stringify({
  阳历: a.solarDate, 农历: a.lunarDate, 时辰: a.time, 生肖: a.zodiac, 星座: a.sign,
  五行局: a.fiveElementsClass, 命主: a.soul, 身主: a.body,
  命宫地支: a.earthlyBranchOfSoulPalace, 身宫地支: a.earthlyBranchOfBodyPalace,
  十二宫: a.palaces.map((p) => ({
    宫: p.name + (p.isBodyPalace ? '(身宫)' : ''), 干支: p.heavenlyStem + p.earthlyBranch,
    主星: p.majorStars.map(star), 辅星: p.minorStars.map(star),
    杂曜: p.adjectiveStars.map((s) => s.name),
    大限: `${p.decadal.range[0]}-${p.decadal.range[1]}岁`,
  })),
  今年运限: {
    大限: { 落本命宫: a.palaces[h.decadal.index].name, 干支: h.decadal.heavenlyStem + h.decadal.earthlyBranch, 四化禄权科忌: h.decadal.mutagen },
    流年: { 落本命宫: a.palaces[h.yearly.index].name, 干支: h.yearly.heavenlyStem + h.yearly.earthlyBranch, 四化禄权科忌: h.yearly.mutagen },
  },
}, null, 1));
