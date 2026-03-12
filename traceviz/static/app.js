/**
 * TraceViz 前端 - Leaflet 地图可视化 + 路径回放动画
 */

function escapeHtml(str) {
  if (!str) return str;
  return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;");
}

function getSegmentLabel(key) {
  return t("seg." + key) || key;
}

let map;
let markers = [];
let layers = [];
let animationController = null;

/** 计算从点A到点B的方位角（度，正北为0，顺时针） */
function getBearing(lat1, lon1, lat2, lon2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const toDeg = (r) => (r * 180) / Math.PI;
  const dLon = toRad(lon2 - lon1);
  const y = Math.sin(dLon) * Math.cos(toRad(lat2));
  const x =
    Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) -
    Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(dLon);
  return (toDeg(Math.atan2(y, x)) + 360) % 360;
}

function initMap() {
  map = L.map("map", { markerZoomAnimation: false }).setView([30, 110], 4);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);
}

function buildPopup(hop) {
  let html = '<div class="popup-content">';
  html += `<strong>#${hop.hop_number}</strong>`;
  if (hop.ip) html += ` <code>${escapeHtml(hop.ip)}</code>`;
  html += "<br>";

  if (hop.hostname) {
    html += `<span class="label">${t('label.host')}</span> <code class="hostname">${escapeHtml(hop.hostname)}</code><br>`;
  }
  if (hop.city || hop.country) {
    html += `<span class="label">${t('label.location')}</span> ${[hop.city, hop.region, hop.country].filter(Boolean).map(escapeHtml).join(", ")}<br>`;
  }
  if (hop.asn || hop.org) {
    const orgDisplay = [hop.asn, hop.org].filter(Boolean).map(escapeHtml).join(" ");
    html += `<span class="label">${t('label.org')}</span> ${orgDisplay}<br>`;
  }
  if (hop.backbone) {
    html += `<span class="label">${t('label.backbone')}</span> <strong style="color:#ff9800">${escapeHtml(hop.backbone)}</strong><br>`;
  }
  if (hop.is_anycast) {
    html += `<span class="anycast-tag">Anycast</span><br>`;
  }
  if (hop.avg_rtt != null) {
    html += `<span class="label">${t('label.latency')}</span> ${hop.avg_rtt.toFixed(1)} ms`;
    if (hop.latency_jump != null && hop.latency_jump > 0) {
      const style = hop.is_cross_ocean ? 'color:#f44336;font-weight:600' : '';
      html += ` <span style="${style}">(+${hop.latency_jump} ms${hop.is_cross_ocean ? " " + t('crossOcean') : ""})</span>`;
    }
    html += "<br>";
  }
  html += `<span class="label">${t('label.type')}</span> ${getSegmentLabel(escapeHtml(hop.segment))}`;
  html += "</div>";
  return html;
}

// === 数据准备函数 ===

function computeAdjLons(geoHops) {
  const adjLons = [];
  if (geoHops.length > 0) {
    adjLons.push(geoHops[0].lon);
    for (let i = 1; i < geoHops.length; i++) {
      let lon = geoHops[i].lon;
      const prev = adjLons[i - 1];
      while (lon - prev > 180) lon -= 360;
      while (lon - prev < -180) lon += 360;
      adjLons.push(lon);
    }
  }
  return adjLons;
}

function createMarker(hop, adjLon, options = {}) {
  const radius = hop.segment === "target" ? 8 : 6;
  const marker = L.circleMarker([hop.lat, adjLon], {
    radius: options.initialRadius != null ? options.initialRadius : radius,
    fillColor: hop.color,
    color: "#fff",
    weight: 1.5,
    fillOpacity: options.initialOpacity != null ? options.initialOpacity : 0.9,
  })
    .addTo(map)
    .bindPopup(buildPopup(hop));
  layers.push(marker);
  return { marker, hop, adjLon, targetRadius: radius };
}

function placeArrow(from, to, fromLon, toLon, hop) {
  const midLat = (from.lat + to.lat) / 2;
  const midLon = (fromLon + toLon) / 2;
  const angle = getBearing(from.lat, fromLon, to.lat, toLon);
  const isCrossOcean = hop.is_cross_ocean;
  const color = isCrossOcean ? "#f44336" : "#4fc3f7";

  const arrow = L.marker([midLat, midLon], {
    icon: L.divIcon({
      className: "route-arrow",
      html: `<svg width="14" height="14" viewBox="0 0 14 14" style="transform:rotate(${angle}deg);transform-origin:center center">
        <path d="M7 1 L12 11 L7 8 L2 11 Z" fill="${color}" opacity="0.85"/>
      </svg>`,
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    }),
    interactive: false,
  }).addTo(map);
  layers.push(arrow);
  return arrow;
}

// === 动画工具函数 ===

function delay(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal && signal.aborted) { reject(new DOMException("Aborted", "AbortError")); return; }
    const timer = setTimeout(resolve, ms);
    if (signal) {
      signal.addEventListener("abort", () => { clearTimeout(timer); reject(new DOMException("Aborted", "AbortError")); }, { once: true });
    }
  });
}

function flyToAsync(latlng, zoom, duration, signal) {
  return new Promise((resolve, reject) => {
    if (signal && signal.aborted) { reject(new DOMException("Aborted", "AbortError")); return; }
    const onAbort = () => { map.stop(); reject(new DOMException("Aborted", "AbortError")); };
    if (signal) signal.addEventListener("abort", onAbort, { once: true });
    map.once("moveend", () => {
      if (signal) signal.removeEventListener("abort", onAbort);
      if (signal && signal.aborted) return;
      resolve();
    });
    map.flyTo(latlng, zoom, { duration, easeLinearity: 0.25 });
  });
}

function flyToBoundsAsync(bounds, options, signal) {
  return new Promise((resolve, reject) => {
    if (signal && signal.aborted) { reject(new DOMException("Aborted", "AbortError")); return; }
    const onAbort = () => { map.stop(); reject(new DOMException("Aborted", "AbortError")); };
    if (signal) signal.addEventListener("abort", onAbort, { once: true });
    map.once("moveend", () => {
      if (signal) signal.removeEventListener("abort", onAbort);
      if (signal && signal.aborted) return;
      resolve();
    });
    map.flyToBounds(bounds, options);
  });
}

function computeAdaptiveZoom(pointA, pointB) {
  const bounds = L.latLngBounds([pointA, pointB]).pad(0.5);
  const zoom = map.getBoundsZoom(bounds);
  return Math.max(3, Math.min(10, zoom));
}

function computeFlyDuration(targetCenter) {
  const currentCenter = map.getCenter();
  const dist = currentCenter.distanceTo(L.latLng(targetCenter)) / 1000; // km
  if (dist < 100) return 0.5;
  if (dist < 1000) return 0.8;
  if (dist < 5000) return 1.2;
  return 1.5;
}

function easeOutCubic(x) {
  return 1 - Math.pow(1 - x, 3);
}

function animateLine(from, to, hop, signal, lineIndex) {
  return new Promise((resolve, reject) => {
    if (signal && signal.aborted) { reject(new DOMException("Aborted", "AbortError")); return; }

    const isCrossOcean = hop.is_cross_ocean;
    const color = isCrossOcean ? "#f44336" : "#4fc3f7";
    const duration = 400;
    const startTime = performance.now();

    const line = L.polyline([from, from], {
      color,
      weight: isCrossOcean ? 3 : 2,
      opacity: 0.7,
      dashArray: isCrossOcean ? "8, 6" : null,
    }).addTo(map);
    if (lineIndex != null) line._animTag = `line-${lineIndex}`;
    layers.push(line);

    let aborted = false;
    const onAbort = () => { aborted = true; };
    if (signal) signal.addEventListener("abort", onAbort, { once: true });

    function step(now) {
      if (aborted) {
        line.setLatLngs([from, to]);
        if (signal) signal.removeEventListener("abort", onAbort);
        reject(new DOMException("Aborted", "AbortError"));
        return;
      }
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = easeOutCubic(progress);
      const currentLat = from[0] + (to[0] - from[0]) * eased;
      const currentLng = from[1] + (to[1] - from[1]) * eased;
      line.setLatLngs([from, [currentLat, currentLng]]);

      if (progress < 1) {
        requestAnimationFrame(step);
      } else {
        if (signal) signal.removeEventListener("abort", onAbort);
        resolve(line);
      }
    }
    requestAnimationFrame(step);
  });
}

function animateMarkerIn(markerObj, duration, signal) {
  return new Promise((resolve, reject) => {
    if (signal && signal.aborted) { reject(new DOMException("Aborted", "AbortError")); return; }

    const { marker, targetRadius } = markerObj;
    const startTime = performance.now();

    let aborted = false;
    const onAbort = () => { aborted = true; };
    if (signal) signal.addEventListener("abort", onAbort, { once: true });

    function step(now) {
      if (aborted) {
        marker.setRadius(targetRadius);
        marker.setStyle({ fillOpacity: 0.9 });
        if (signal) signal.removeEventListener("abort", onAbort);
        reject(new DOMException("Aborted", "AbortError"));
        return;
      }
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = easeOutCubic(progress);
      marker.setRadius(targetRadius * eased);
      marker.setStyle({ fillOpacity: 0.9 * eased });

      if (progress < 1) {
        requestAnimationFrame(step);
      } else {
        if (signal) signal.removeEventListener("abort", onAbort);
        resolve();
      }
    }
    requestAnimationFrame(step);
  });
}

function highlightHopCard(hopNumber) {
  document.querySelectorAll(".hop-card.active").forEach((el) => el.classList.remove("active"));
  const card = document.getElementById(`hop-card-${hopNumber}`);
  if (card) {
    card.classList.add("active");
    card.style.opacity = "1";
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

function finishAnimation(geoHops, adjLons, allHops) {
  // 确保所有 marker 存在并可见
  const existingHopNums = new Set(markers.map((m) => m.hop.hop_number));
  geoHops.forEach((hop, i) => {
    if (!existingHopNums.has(hop.hop_number)) {
      const m = createMarker(hop, adjLons[i]);
      markers.push(m);
    } else {
      const m = markers.find((x) => x.hop.hop_number === hop.hop_number);
      if (m) {
        m.marker.setRadius(m.targetRadius);
        m.marker.setStyle({ fillOpacity: 0.9 });
      }
    }
  });

  // 恢复所有卡片不透明度
  document.querySelectorAll(".hop-card").forEach((card) => {
    card.style.opacity = "";
  });
  document.querySelectorAll(".hop-card.active").forEach((el) => el.classList.remove("active"));

  // flyToBounds
  if (geoHops.length > 0) {
    const adjLatlngs = geoHops.map((h, i) => [h.lat, adjLons[i]]);
    map.flyToBounds(L.latLngBounds(adjLatlngs).pad(0.15), { duration: 0.8, maxZoom: 12 });
  }

  // 隐藏跳过按钮
  const skipBtn = document.getElementById("skip-animation");
  if (skipBtn) skipBtn.style.display = "none";
}

// === 动画主控 ===

async function animateRoute(geoHops, adjLons, allHops) {
  if (geoHops.length === 0) return;

  const controller = new AbortController();
  const signal = controller.signal;
  animationController = controller;

  // 显示跳过按钮
  const skipBtn = document.getElementById("skip-animation");
  if (skipBtn) {
    skipBtn.textContent = t("skipAnimation");
    skipBtn.style.display = "block";
    skipBtn.onclick = () => controller.abort();
  }

  try {
    // 阶段0：flyTo 第一个节点
    const firstLatLng = [geoHops[0].lat, adjLons[0]];
    const firstZoom = Math.min(10, map.getZoom() + 2);
    await flyToAsync(firstLatLng, firstZoom, 1.0, signal);

    // 淡入第一个 marker
    const firstMarker = createMarker(geoHops[0], adjLons[0], { initialRadius: 0, initialOpacity: 0 });
    markers.push(firstMarker);
    await animateMarkerIn(firstMarker, 250, signal);
    highlightHopCard(geoHops[0].hop_number);
    await delay(200, signal);

    // 逐跳动画
    for (let i = 1; i < geoHops.length; i++) {
      const prev = geoHops[i - 1];
      const curr = geoHops[i];
      const fromLatLng = [prev.lat, adjLons[i - 1]];
      const toLatLng = [curr.lat, adjLons[i]];

      // 计算自适应缩放
      const midLat = (prev.lat + curr.lat) / 2;
      const midLon = (adjLons[i - 1] + adjLons[i]) / 2;
      const midPoint = [midLat, midLon];
      const zoom = computeAdaptiveZoom(fromLatLng, toLatLng);
      const duration = computeFlyDuration(midPoint);

      // flyTo 两点中心
      await flyToAsync(midPoint, zoom, duration, signal);

      // 画线动画
      await animateLine(fromLatLng, toLatLng, curr, signal, i - 1);

      // 放置箭头
      placeArrow(prev, curr, adjLons[i - 1], adjLons[i], curr);

      // 终点节点淡入
      const markerObj = createMarker(curr, adjLons[i], { initialRadius: 0, initialOpacity: 0 });
      markers.push(markerObj);
      await animateMarkerIn(markerObj, 250, signal);

      // 高亮侧边栏
      highlightHopCard(curr.hop_number);

      // 间隔
      await delay(200, signal);
    }

    // 动画完成：flyToBounds
    if (geoHops.length > 0) {
      const adjLatlngs = geoHops.map((h, i) => [h.lat, adjLons[i]]);
      await flyToBoundsAsync(L.latLngBounds(adjLatlngs).pad(0.15), { duration: 0.8, maxZoom: 12 }, signal);
    }

    // 移除所有卡片高亮，恢复不透明度
    document.querySelectorAll(".hop-card.active").forEach((el) => el.classList.remove("active"));
    document.querySelectorAll(".hop-card").forEach((card) => { card.style.opacity = ""; });

    // 隐藏跳过按钮
    if (skipBtn) skipBtn.style.display = "none";

  } catch (err) {
    if (err.name === "AbortError") {
      // 仅当此 controller 仍是当前活跃的才执行清理（防止旧动画污染新动画）
      if (animationController === controller || animationController === null) {
        finishAllElements(geoHops, adjLons);
        finishAnimation(geoHops, adjLons, allHops);
      }
    } else {
      throw err;
    }
  }

  if (animationController === controller) animationController = null;
}

/** 跳过时补全所有缺失的线和箭头和节点 */
function finishAllElements(geoHops, adjLons) {
  const existingHopNums = new Set(markers.map((m) => m.hop.hop_number));

  for (let i = 0; i < geoHops.length; i++) {
    if (!existingHopNums.has(geoHops[i].hop_number)) {
      const m = createMarker(geoHops[i], adjLons[i]);
      markers.push(m);
    }
  }

  // 补全线和箭头 — 逐段检查
  // 由于动画中断时部分线段已完成，我们需要知道已完成到哪一段
  // 简化处理：遍历所有段，检查是否有对应的 polyline
  // 实际上 layers 中已有的线条不容易精确匹配，直接补全不会有视觉问题
  for (let i = 0; i < geoHops.length - 1; i++) {
    const a = geoHops[i];
    const b = geoHops[i + 1];
    const fromLatLng = [a.lat, adjLons[i]];
    const toLatLng = [b.lat, adjLons[i + 1]];
    const isCrossOcean = b.is_cross_ocean;
    const color = isCrossOcean ? "#f44336" : "#4fc3f7";

    // 检查是否已有这段线 — 通过标记
    const lineTag = `line-${i}`;
    const existing = layers.find((l) => l._animTag === lineTag);
    if (!existing) {
      const line = L.polyline([fromLatLng, toLatLng], {
        color,
        weight: isCrossOcean ? 3 : 2,
        opacity: 0.7,
        dashArray: isCrossOcean ? "8, 6" : null,
      }).addTo(map);
      line._animTag = lineTag;
      layers.push(line);

      placeArrow(a, b, adjLons[i], adjLons[i + 1], b);
    }
  }
}

// === 渲染函数 ===

async function renderMap(data) {
  // 清理旧状态
  layers.forEach((l) => map.removeLayer(l));
  layers = [];
  markers = [];
  const skipBtn = document.getElementById("skip-animation");
  if (skipBtn) skipBtn.style.display = "none";
  if (animationController) {
    animationController.abort();
    animationController = null;
  }
  document.getElementById("hop-list").innerHTML = "";

  const { target, hops } = data;

  // 目标信息
  document.getElementById("target-info").textContent = t('target', { target, count: hops.length });

  // 有坐标的跳
  const geoHops = hops.filter((h) => h.lat != null && h.lon != null);

  // 计算调整后的经度
  const adjLons = computeAdjLons(geoHops);

  // 仅在存在地理坐标时启用动画态。
  const shouldAnimate = geoHops.length > 0;
  renderHopList(hops, shouldAnimate);

  if (shouldAnimate) {
    await animateRoute(geoHops, adjLons, hops);
  }
}

function renderHopList(hops, animated = false) {
  const container = document.getElementById("hop-list");

  hops.forEach((hop) => {
    const card = document.createElement("div");
    card.className = "hop-card" + (hop.is_timeout ? " timeout" : "");
    card.id = `hop-card-${hop.hop_number}`;
    card.style.borderLeftColor = hop.color;
    if (animated) card.style.opacity = "0.3";

    let headerHtml = `<span class="hop-num">#${hop.hop_number}</span>`;
    if (hop.ip) {
      headerHtml += `<span class="hop-ip">${escapeHtml(hop.ip)}</span>`;
    } else {
      headerHtml += `<span class="hop-ip">* * *</span>`;
    }
    if (hop.avg_rtt != null) {
      headerHtml += `<span class="hop-rtt">${hop.avg_rtt.toFixed(1)} ms</span>`;
    }

    let detailHtml = "";
    if (hop.hostname) {
      detailHtml += `<span class="hostname">${escapeHtml(hop.hostname)}</span>`;
    }
    if (hop.city || hop.country) {
      detailHtml += (detailHtml ? " | " : "") + [hop.city, hop.region, hop.country].filter(Boolean).map(escapeHtml).join(", ");
    }
    if (hop.asn || hop.org) {
      const orgDisplay = [hop.asn, hop.org].filter(Boolean).map(escapeHtml).join(" ");
      detailHtml += (detailHtml ? " | " : "") + orgDisplay;
    }
    if (hop.backbone) {
      detailHtml += ` <span class="backbone-tag">[${escapeHtml(hop.backbone)}]</span>`;
    }
    if (hop.is_anycast) {
      detailHtml += ` <span class="anycast-tag">Anycast</span>`;
    }
    if (hop.is_cross_ocean && hop.latency_jump != null) {
      detailHtml += ` <span class="cross-ocean">${t('crossOceanSidebar')} (+${hop.latency_jump.toFixed(1)}ms)</span>`;
    }

    card.innerHTML = `
      <div class="hop-header">${headerHtml}</div>
      ${detailHtml ? `<div class="hop-detail">${detailHtml}</div>` : ""}
    `;

    // 点击定位到地图
    if (hop.lat != null && hop.lon != null) {
      card.style.cursor = "pointer";
      card.addEventListener("click", () => {
        const m = markers.find((x) => x.hop.hop_number === hop.hop_number);
        if (m) {
          map.setView([hop.lat, m.adjLon], 8);
          m.marker.openPopup();
        }
      });
    }

    container.appendChild(card);
  });
}

// 启动
applyI18n();
initMap();
fetch("/api/trace")
  .then((r) => r.json())
  .then(renderMap)
  .catch((err) => {
    console.error("Failed to load trace data:", err);
    document.getElementById("target-info").textContent = t('loadError', { msg: err.message });
  });
