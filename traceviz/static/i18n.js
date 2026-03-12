/**
 * TraceViz 轻量级 i18n
 */

const messages = {
  zh: {
    title: "TraceViz - 路径可视化",
    target: "目标: {target} | 共 {count} 跳",
    loadError: "加载失败: {msg}",
    // 图例
    "seg.local": "局域网",
    "seg.backbone": "骨干网",
    "seg.transit": "中转",
    "seg.international": "国际段",
    "seg.target": "目标",
    // 弹窗标签
    "label.host": "主机名:",
    "label.location": "位置:",
    "label.org": "运营商:",
    "label.asn": "ASN:",
    "label.backbone": "骨干网:",
    "label.latency": "延迟:",
    "label.type": "类型:",
    // 特殊标记
    crossOcean: "🌊跨洋",
    crossOceanSidebar: "🌊 可能跨洋",
    skipAnimation: "跳过动画",
  },
  en: {
    title: "TraceViz - Route Visualization",
    target: "Target: {target} | {count} hops",
    loadError: "Load failed: {msg}",
    "seg.local": "LAN",
    "seg.backbone": "Backbone",
    "seg.transit": "Transit",
    "seg.international": "International",
    "seg.target": "Target",
    "label.host": "Hostname:",
    "label.location": "Location:",
    "label.org": "ISP:",
    "label.asn": "ASN:",
    "label.backbone": "Backbone:",
    "label.latency": "Latency:",
    "label.type": "Type:",
    crossOcean: "🌊 Cross-ocean",
    crossOceanSidebar: "🌊 Cross-ocean",
    skipAnimation: "Skip",
  },
};

let currentLang = getLang();

function getLang() {
  const stored = localStorage.getItem("traceviz-lang");
  if (stored && messages[stored]) return stored;
  const nav = navigator.language || navigator.userLanguage || "en";
  return nav.startsWith("zh") ? "zh" : "en";
}

function t(key, params) {
  const text = (messages[currentLang] && messages[currentLang][key]) ||
               (messages.zh && messages.zh[key]) || key;
  if (!params) return text;
  return text.replace(/\{(\w+)\}/g, (_, k) => (params[k] != null ? params[k] : `{${k}}`));
}

function setLang(lang) {
  if (!messages[lang]) return;
  localStorage.setItem("traceviz-lang", lang);
  location.reload();
}

function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  document.title = t("title");
  // 更新语言切换按钮文本
  const btn = document.getElementById("lang-toggle");
  if (btn) btn.textContent = currentLang === "zh" ? "EN" : "中文";
}
