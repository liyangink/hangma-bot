"use strict";

const sourceSelect = document.querySelector("#source-select");
const gameList = document.querySelector("#game-list");
const gameCount = document.querySelector("#game-count");
const refreshButton = document.querySelector("#refresh-button");
const lastRefresh = document.querySelector("#last-refresh");
const connection = document.querySelector("#connection");
const emptyState = document.querySelector("#empty-state");
const gameView = document.querySelector("#game-view");
const issues = document.querySelector("#issues");

const boardFit = document.querySelector("#board-fit");
const boardFrame = document.querySelector("#board-frame");
const boardSurface = document.querySelector(".mahjong-board");
const nextFrame = typeof window.requestAnimationFrame === "function"
  ? window.requestAnimationFrame.bind(window)
  : callback => {
      if (typeof window.setTimeout === "function") window.setTimeout(callback, 16);
      else callback();
    };
let fitScheduled = false;

let current = null;
let selectedSourceId = null;
let selectedGameId = null;
let refreshTimer = null;
// 已渲染牌桌的快照签名：内容未变时跳过重绘，避免 750 毫秒轮询反复重建 DOM。
let renderedSignature = null;
// 侧栏条目按 game_id 复用，只就地更新文字，不整表重建。
const sidebarItems = new Map();

function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function text(node, value) { node.textContent = value === null || value === undefined || value === "" ? "—" : String(value); }
function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined) text(node, value);
  return node;
}
// 牌面素材：公有领域矢量牌（见 assets/README.md），牌码到素材名的映射。
const TILE_ASSET_ROOT = "/assets/tiles/";
const TILE_ASSET_BACK = TILE_ASSET_ROOT + "Back.svg";
const TILE_ASSET_SUITS = { w: "Man", b: "Pin", t: "Sou" };
const TILE_ASSET_HONORS = {
  "东": "Ton", "南": "Nan", "西": "Shaa", "北": "Pei",
  "中": "Chun", "发": "Hatsu", "白": "Haku",
};
// 展示排序：万 → 筒 → 条 → 字，字按东南西北中发白。官方返回顺序只用于决策，
// 观战展示统一按此顺序排列，避免手牌看起来杂乱。
const SUIT_ORDER = { w: 0, b: 1, t: 2 };
// 门风顺序：以庄家为东，按出牌方向依次南、西、北。
const SEAT_WINDS = ["東", "南", "西", "北"];
const HONOR_ORDER = { "东": 0, "南": 1, "西": 2, "北": 3, "中": 4, "发": 5, "白": 6 };

function tileAssetName(tile) {
  const matched = /^([1-9])([wbt])$/.exec(tile || "");
  if (matched) return TILE_ASSET_SUITS[matched[2]] + matched[1] + ".svg";
  return TILE_ASSET_HONORS[tile] ? TILE_ASSET_HONORS[tile] + ".svg" : null;
}
function tileFace(tile) {
  const matched = /^([1-9])([wbt])$/.exec(tile || "");
  if (matched) {
    const suitNames = { w: "万", b: "筒", t: "条" };
    return { label: matched[1] + suitNames[matched[2]], fortune: false };
  }
  const character = tile || "?";
  return {
    label: character === "?" ? "未知牌" : character === "白" ? "白板（财神）" : character,
    // 财神固定为「白」：牌面右上角打金色「财」标记，便于一眼清点。
    fortune: character === "白",
  };
}
function tileSortKey(tile) {
  const matched = /^([1-9])([wbt])$/.exec(tile || "");
  if (matched) return [SUIT_ORDER[matched[2]], Number(matched[1])];
  const honor = HONOR_ORDER[tile];
  return [3, honor === undefined ? 9 : honor];
}
function sortHandTiles(tiles, drawnTile) {
  // 刚摸的那张摘出手牌参与排序后再放回最右端，单独留白显示。
  const rest = (tiles || []).slice();
  if (drawnTile) {
    const index = rest.lastIndexOf(drawnTile);
    if (index >= 0) rest.splice(index, 1);
  }
  rest.sort((left, right) => {
    const a = tileSortKey(left);
    const b = tileSortKey(right);
    return a[0] !== b[0] ? a[0] - b[0] : a[1] - b[1];
  });
  if (drawnTile) rest.push(drawnTile);
  return rest;
}
function tileImage(className, source, label) {
  const img = document.createElement("img");
  img.className = className;
  img.src = TILE_ASSET_ROOT + source;
  img.alt = label || "";
  img.draggable = false;
  return img;
}
function appendTile(parent, tile, drawn = false, lastDiscard = false) {
  // 牌面素材是透明图形，牌身来自 Front.svg：两层叠加才是完整麻将牌。
  const face = tileFace(tile);
  const classes = "tile" + (drawn ? " drawn" : "") + (lastDiscard ? " last-discard" : "") + (face.fortune ? " fortune" : "");
  const node = element("span", classes);
  node.setAttribute("aria-label", face.label);
  node.appendChild(tileImage("tile-body", "Front.svg", ""));
  const asset = tileAssetName(tile);
  if (asset) {
    node.appendChild(tileImage("tile-face", asset, face.label));
  } else {
    node.appendChild(element("span", "tile-text", tile || "?"));
  }
  parent.appendChild(node);
  return node;
}
function appendTileBack(parent) {
  // 牌墙同样用象牙牌身，背板由 CSS 画成绿色竹背，避免红色牌背在牌桌上过于刺眼。
  const node = element("span", "tile tile-back");
  node.setAttribute("aria-label", "暗牌");
  node.appendChild(tileImage("tile-body", "Front.svg", ""));
  node.appendChild(element("span", "tile-back-panel"));
  parent.appendChild(node);
  return node;
}
function fitBoard() {
  // 牌桌按可用区域等比缩放：像游戏一样铺满窗口，且不出现整页滚动条。
  // 关键是让“缩放后尺寸”参与布局——框架撑成缩放后大小、牌桌以左上角为原点缩放，
  // 于是居中与完整性由普通布局保证，不依赖 overflow 裁剪。
  if (!boardFit || !boardFrame || !boardSurface || gameView.hidden) return;
  if (typeof boardFit.getBoundingClientRect !== "function") return;
  boardSurface.style.transform = "none";
  boardFrame.style.width = "auto";
  boardFrame.style.height = "auto";
  const available = boardFit.getBoundingClientRect();
  const natural = boardSurface.getBoundingClientRect();
  if (!natural.width || !natural.height || !available.width || !available.height) return;
  const scale = Math.max(Math.min(available.width / natural.width, available.height / natural.height), 0.2);
  boardFrame.style.width = (natural.width * scale).toFixed(2) + "px";
  boardFrame.style.height = (natural.height * scale).toFixed(2) + "px";
  boardSurface.style.transform = "scale(" + scale.toFixed(4) + ")";
}
function scheduleFitBoard() {
  // 合帧处理：一次刷新可能触发多处 DOM 变化，只缩放一次。
  if (fitScheduled) return;
  fitScheduled = true;
  nextFrame(() => {
    fitScheduled = false;
    fitBoard();
  });
}
function formatTime(ms) {
  if (!Number.isInteger(ms)) return "未知";
  return new Date(ms).toLocaleTimeString("zh-CN", { hour12: false });
}
function actionText(action) {
  if (!action || !action.kind) return "未知动作";
  if (action.kind === "discard") return "弃 " + action.tile;
  if (action.kind === "peng") return "碰 " + action.tile;
  if (action.kind === "gang") return "杠 " + action.tile;
  if (action.kind === "chi") return "吃 " + (action.tiles || []).join(" ");
  if (action.kind === "hu") return "胡";
  if (action.kind === "pass") return "过";
  return action.kind;
}
function sourceLabel(source) {
  // 同一场次下每个角色只保留一个来源；run_id 是审计实现细节，不增加选择负担。
  return source.role || source.participant_id || "未命名角色";
}
function tableLabel(gameId) {
  // 官方场次名形如 a_xxx_r1_b0_t0；提取 b0 桌号做短标签。
  const matched = /_(b\d+)_/.exec(gameId || "");
  return matched ? "桌" + matched[1] : (gameId || "未知场次");
}
function gameBrief(game) {
  // 下拉框摘要：本家手牌里的财神张数（财神牌见 rule_state.wealth_god，当前为白）
  // 与本座位当前桌内积分；完整快照未到达时对应项为 null。
  const obs = game.observation;
  if (!obs) return { table: tableLabel(game.game_id), roundNo: null, fortuneCount: null, myScore: null };
  const god = (obs.rule_state && obs.rule_state.wealth_god) || "白";
  const fortuneCount = (obs.my_hand || []).filter(tile => tile === god).length;
  const seat = Number.isInteger(obs.seat) ? obs.seat : null;
  const myScore = seat !== null && Array.isArray(obs.scores) ? obs.scores[seat] : null;
  return { table: tableLabel(game.game_id), roundNo: obs.round_no, fortuneCount, myScore };
}
function activeGames() {
  // 四个 Token 可能都记录同一个官方场次；按 game_id 聚合后让人只选一次。
  // 排序：财神多、我方分数高的桌排在前面，便于优先观战；同序再按 game_id 稳定排序。
  const byId = new Map();
  for (const source of (current?.sources || [])) {
    for (const game of (source.games || [])) {
      if (!game.finished && !byId.has(game.game_id)) byId.set(game.game_id, game);
    }
  }
  return [...byId.values()].sort((left, right) => {
    const a = gameBrief(left);
    const b = gameBrief(right);
    const fortuneDelta = (b.fortuneCount ?? -1) - (a.fortuneCount ?? -1);
    if (fortuneDelta !== 0) return fortuneDelta;
    const scoreDelta = (b.myScore ?? -Infinity) - (a.myScore ?? -Infinity);
    if (scoreDelta !== 0) return scoreDelta;
    return left.game_id.localeCompare(right.game_id);
  });
}
function sourcesForSelectedGame() {
  if (!selectedGameId) return [];
  return (current?.sources || []).filter(source =>
    (source.games || []).some(game => game.game_id === selectedGameId && !game.finished)
  );
}
function selectedSource() {
  return sourcesForSelectedGame().find(source => source.source_id === selectedSourceId) || null;
}
function selectedGame() {
  return selectedSource()?.games?.find(game => game.game_id === selectedGameId && !game.finished) || null;
}

function renderTiles(id, tiles, drawnTile) {
  const node = document.querySelector(id);
  clear(node);
  // 手牌按万→筒→条→字排序展示；刚摸的那张排在最右并单独留白。
  const ordered = sortHandTiles(tiles, drawnTile);
  ordered.forEach((tile, index) => {
    const isDrawn = Boolean(drawnTile) && index === ordered.length - 1 && tile === drawnTile;
    appendTile(node, tile, isDrawn);
  });
  if (!ordered.length) node.appendChild(element("span", "muted", "当前没有可显示的本家手牌。"));
}
function renderFacts(id, pairs) {
  const node = document.querySelector(id);
  clear(node);
  for (const [label, value] of pairs) {
    node.appendChild(element("dt", "", label));
    node.appendChild(element("dd", "", value));
  }
}
function renderConcealedHand(id, count) {
  const node = document.querySelector(id);
  clear(node);
  const safeCount = Number.isInteger(count) && count > 0 ? count : 0;
  for (let index = 0; index < safeCount; index += 1) appendTileBack(node);
  node.appendChild(element("span", "wall-count", safeCount ? "暗手 " + safeCount + " 张" : "暗手张数未知"));
}
function renderSeatMelds(id, melds) {
  const node = document.querySelector(id);
  clear(node);
  const kindNames = { peng: "碰", chi: "吃", gang: "杠", angang: "暗杠" };
  for (const meld of (melds || [])) {
    const isGang = meld.kind === "gang" || meld.kind === "angang";
    const label = kindNames[meld.kind] || meld.kind || "副露";
    const group = element("div", "seat-meld" + (isGang ? " meld-gang" : ""));
    group.setAttribute("aria-label", label + " " + (meld.tiles || []).join(" "));
    group.appendChild(element("span", "meld-kind", label));
    const tiles = element("span", "meld-tiles");
    for (const tile of (meld.tiles || [])) appendTile(tiles, tile);
    group.appendChild(tiles);
    node.appendChild(group);
  }
}
function renderRiver(id, tiles, lastDiscard) {
  const node = document.querySelector(id);
  clear(node);
  const list = tiles || [];
  const lastIndex = lastDiscard ? list.lastIndexOf(lastDiscard.tile) : -1;
  list.forEach((tile, index) => {
    const placed = appendTile(node, tile, false, index === lastIndex);
    placed.title = "第 " + (index + 1) + " 张弃牌" + (index === lastIndex ? "（最近）" : "");
  });
}
function relativeSeat(mySeat, offset) {
  return Number.isInteger(mySeat) ? (mySeat + offset) % 4 : null;
}
function renderPerspective(observation) {
  // 官方快照不提供对手身份；以相对座位命名（本家/下家/对家/上家）并保留
  // 座位号，庄家加“庄”标记，轮到行动时加提示。
  const placements = [
    ["bottom", 0, "本家（我）"],
    ["right", 1, "下家"],
    ["top", 2, "对家"],
    ["left", 3, "上家"],
  ];
  const mySeat = observation.seat;
  const god = (observation.rule_state && observation.rule_state.wealth_god) || "白";
  const myFortuneCount = (observation.my_hand || []).filter(tile => tile === god).length;
  for (const [position, offset, name] of placements) {
    const seat = relativeSeat(mySeat, offset);
    const isMe = position === "bottom";
    const holder = document.querySelector("#player-" + position);
    const isTurn = seat !== null && seat === observation.turn_seat;
    holder.classList.toggle("is-turn", isTurn);
    const nameParts = [name, "座位 " + (seat ?? "—")];
    if (seat !== null && seat === observation.dealer_seat) nameParts.push("庄");
    if (isTurn) nameParts.push("行动中");
    const label = document.querySelector("#seat-label-" + position);
    text(label, name);
    label.title = "座位 " + (seat ?? "—");
    const windIndex = seat !== null && Number.isInteger(observation.dealer_seat)
      ? (seat - observation.dealer_seat + 4) % 4
      : offset;
    const wind = document.querySelector("#wind-" + position);
    text(wind, SEAT_WINDS[windIndex] || "—");
    wind.classList.toggle("is-dealer", seat !== null && seat === observation.dealer_seat);
    const scoreValue = seat === null || !Array.isArray(observation.scores) ? null : observation.scores[seat];
    const score = document.querySelector("#score-" + position);
    text(score, scoreValue);
    score.classList.toggle("is-positive", typeof scoreValue === "number" && scoreValue > 0);
    score.classList.toggle("is-negative", typeof scoreValue === "number" && scoreValue < 0);
    document.querySelector("#dealer-" + position).hidden = !(seat !== null && seat === observation.dealer_seat);
    document.querySelector("#turn-" + position).hidden = !isTurn;
    // 信息权限：只有本家手牌可见，因此只有本家能显示财神张数。
    const fortuneBadge = document.querySelector("#fortune-" + position);
    fortuneBadge.hidden = !isMe;
    if (isMe) text(fortuneBadge, "财神×" + myFortuneCount);
    renderSeatMelds("#melds-" + position, seat === null ? [] : observation.melds?.[seat]);
    renderRiver("#river-" + position, seat === null ? [] : observation.discards?.[seat], seat === null || observation.last_discard?.seat !== seat ? null : observation.last_discard);
    if (!isMe) renderConcealedHand("#hand-" + position, seat === null ? null : observation.hand_counts?.[seat]);
  }
  renderDial(observation);
}
function renderDial(observation) {
  // 中央风盘：门风按出牌顺序以庄家为东排定；另显示牌墙余量与当前局数。
  const winds = SEAT_WINDS;
  const mySeat = observation.seat;
  const dealerSeat = observation.dealer_seat;
  for (const [position, offset] of [["bottom", 0], ["right", 1], ["top", 2], ["left", 3]]) {
    const seat = relativeSeat(mySeat, offset);
    const windIndex = seat !== null && Number.isInteger(dealerSeat) ? (seat - dealerSeat + 4) % 4 : offset;
    const node = document.querySelector("#dial-wind-" + position);
    text(node, winds[windIndex] || "—");
    node.classList.toggle("is-dealer", seat !== null && seat === dealerSeat);
  }
  text(document.querySelector("#dial-remaining"), observation.remaining_tile_count ?? null);
  text(document.querySelector("#dial-round"), "第 " + (observation.round_no ?? "—") + " 局");
}
function usefulText(usefulTiles) {
  if (!usefulTiles || !usefulTiles.length) return "无";
  return usefulTiles.map(tile => tile.code + " × " + tile.remaining_estimate).join("，");
}
function renderCandidates(candidates) {
  const node = document.querySelector("#candidates");
  clear(node);
  if (!candidates?.length) {
    node.appendChild(element("p", "muted", "尚未收到该官方场次的决策候选。"));
    return;
  }
  for (const candidate of candidates) {
    const card = element("article", "candidate");
    const head = element("div", "candidate-head");
    head.appendChild(element("strong", "", "#" + (candidate.rank ?? "—") + " " + actionText(candidate.action)));
    if (candidate.is_emergency) head.appendChild(element("span", "badge", "保底动作"));
    if (candidate.total_score !== null && candidate.total_score !== undefined) head.appendChild(element("span", "muted", "策略分 " + candidate.total_score));
    card.appendChild(head);
    if (candidate.facts) {
      const facts = candidate.facts;
      const details = [];
      if (facts.fact_kind) details.push(facts.fact_kind === "win" ? "当前可胡" : "向听 " + (facts.shanten_after ?? "未知"));
      if (facts.useful_tiles?.length) details.push("有效牌（公开估计）: " + usefulText(facts.useful_tiles));
      if (facts.best_followup_discard) details.push("鸣牌后建议弃 " + facts.best_followup_discard);
      if (facts.replacement_draw_unknown) details.push("杠上补牌未知");
      if (facts.note) details.push(facts.note);
      card.appendChild(element("div", "candidate-facts", details.join(" · ") || "牌效事实未提供"));
    }
    if (candidate.reasons?.length) card.appendChild(element("p", "", candidate.reasons.join("；")));
    node.appendChild(card);
  }
}
function renderEvents(events) {
  const node = document.querySelector("#events");
  clear(node);
  if (!events?.length) { node.appendChild(element("li", "", "暂无增量事件。")); return; }
  for (const event of events) {
    const parts = ["seq " + (event.seq ?? "?"), event.type || "unknown"];
    if (Number.isInteger(event.seat)) parts.push("座位 " + event.seat);
    if (event.tile) parts.push(event.tile);
    node.appendChild(element("li", "", parts.join(" · ")));
  }
}
function renderGame(game) {
  const observation = game.observation;
  gameView.hidden = !observation;
  if (!observation) return;
  emptyState.hidden = true;
  text(document.querySelector("#game-title"), game.game_id + " · 单局 " + (observation.round_no ?? "—"));
  const freshness = game.freshness || {};
  const warning = document.querySelector("#warning");
  warning.hidden = !freshness.event_ahead_of_table_snapshot;
  text(warning, freshness.event_ahead_of_table_snapshot ? "收到更晚的增量事件。为避免错误推演，牌桌仍展示最后一份完整观察；请结合右侧事件列表阅读。" : "");
  renderTiles("#my-hand", observation.my_hand, observation.drawn_tile);
  text(document.querySelector("#drawn-tile"), observation.drawn_tile ? "刚摸牌（黄框）：" + observation.drawn_tile : "当前没有单列摸牌。");
  renderPerspective(observation);
  const rule = observation.rule_state || {};
  renderFacts("#rule-state", [["财神", rule.wealth_god], ["爆头", rule.baotou === true ? "是" : rule.baotou === false ? "否" : "未知"], ["动作链", rule.chain_count], ["抓打圈", rule.catch_play === true ? "是" : rule.catch_play === false ? "否" : "未知"]]);
  text(document.querySelector("#turn-state"), (observation.phase || "未知阶段") + " · 行动座位 " + (observation.turn_seat ?? "—"));
  text(document.querySelector("#last-discard"), observation.last_discard ? "最近弃牌：座位 " + (observation.last_discard.seat ?? "—") + " · " + (observation.last_discard.tile || "未知") : "最近弃牌：无");
  renderFacts("#table-facts", [["庄家", observation.dealer_seat], ["响应座位", (observation.responding_seats || []).join("，") || "无"], ["牌墙余量", observation.remaining_tile_count], ["观察来源", game.observation_source]]);
  renderCandidates(game.candidates);
  const submission = game.latest_submission;
  text(document.querySelector("#submission"), submission ? [submission.action_key || "动作键未知", submission.outcome || "结果未知", submission.official_code || ""].filter(Boolean).join(" · ") : "暂无提交审计。");
  renderEvents(game.events);
  scheduleFitBoard();
}
function renderIssues(source) {
  clear(issues);
  const list = source?.issues || [];
  issues.hidden = !list.length;
  if (!list.length) return;
  issues.appendChild(element("strong", "", "读取提示"));
  const ul = document.createElement("ul");
  list.forEach(issue => ul.appendChild(element("li", "", issue)));
  issues.appendChild(ul);
}
function myWindowLabel(observation) {
  // 本家是否正处于动作窗口：响应名单含本人座位，或当前轮到本人摸牌。
  if (!observation || !Number.isInteger(observation.seat)) return null;
  const responding = Array.isArray(observation.responding_seats) ? observation.responding_seats : [];
  if (responding.includes(observation.seat)) return "待我响应";
  if (observation.turn_seat === observation.seat) return "轮到我";
  return null;
}
function gameSignature(game) {
  // 只在完整观察、候选、提交或事件水位变化时才重绘牌桌；新鲜度文字仍每轮更新。
  const events = game.events || [];
  return JSON.stringify([
    game.observation,
    game.candidates,
    game.latest_submission,
    game.finished,
    game.observation_source,
    events.length,
    events.length ? events[0].seq : null,
  ]);
}
function buildSidebarItem(gameId) {
  const button = element("button", "game-item-button");
  button.type = "button";
  button.dataset.gameId = gameId;
  button.setAttribute("aria-pressed", "false");
  const head = element("span", "game-item-head");
  const table = element("strong", "game-item-table");
  const score = element("span", "game-item-score");
  head.appendChild(table);
  head.appendChild(score);
  const meta = element("span", "game-item-meta");
  const roundBadge = element("span", "badge-pill");
  const fortuneBadge = element("span", "badge-pill is-fortune");
  const windowBadge = element("span", "badge-pill is-turn");
  windowBadge.hidden = true;
  meta.appendChild(roundBadge);
  meta.appendChild(fortuneBadge);
  meta.appendChild(windowBadge);
  button.appendChild(head);
  button.appendChild(meta);
  const item = document.createElement("li");
  item.className = "game-item";
  item.appendChild(button);
  return { element: item, button, table, score, roundBadge, fortuneBadge, windowBadge };
}
function updateSidebarItem(item, game) {
  const brief = gameBrief(game);
  if (item.table.textContent !== brief.table) item.table.textContent = brief.table;
  const scoreLabel = brief.myScore === null || brief.myScore === undefined ? "—" : brief.myScore + " 分";
  if (item.score.textContent !== scoreLabel) item.score.textContent = scoreLabel;
  item.score.classList.toggle("is-positive", typeof brief.myScore === "number" && brief.myScore > 0);
  item.score.classList.toggle("is-negative", typeof brief.myScore === "number" && brief.myScore < 0);
  const roundLabel = brief.roundNo === null || brief.roundNo === undefined ? "第—局" : "第" + brief.roundNo + "局";
  if (item.roundBadge.textContent !== roundLabel) item.roundBadge.textContent = roundLabel;
  const fortuneLabel = brief.fortuneCount === null ? "财神？" : "财神×" + brief.fortuneCount;
  if (item.fortuneBadge.textContent !== fortuneLabel) item.fortuneBadge.textContent = fortuneLabel;
  const windowLabel = myWindowLabel(game.observation);
  item.windowBadge.hidden = !windowLabel;
  if (windowLabel && item.windowBadge.textContent !== windowLabel) item.windowBadge.textContent = windowLabel;
  const pressed = game.game_id === selectedGameId ? "true" : "false";
  if (item.button.getAttribute("aria-pressed") !== pressed) item.button.setAttribute("aria-pressed", pressed);
}
function renderSidebar(games) {
  const seen = new Set();
  for (const game of games) {
    let item = sidebarItems.get(game.game_id);
    if (!item) {
      item = buildSidebarItem(game.game_id);
      sidebarItems.set(game.game_id, item);
    }
    updateSidebarItem(item, game);
    seen.add(game.game_id);
  }
  for (const [gameId, entry] of sidebarItems) {
    if (!seen.has(gameId)) {
      entry.element.remove();
      sidebarItems.delete(gameId);
    }
  }
  // 仅在排序结果变化时重排节点，避免每轮轮询都把节点挪动一遍。
  const order = games.map(game => game.game_id).join("|");
  if (gameList.dataset.order !== order) {
    for (const game of games) gameList.appendChild(sidebarItems.get(game.game_id).element);
    gameList.dataset.order = order;
  }
  text(gameCount, games.length ? games.length + " 桌进行中" : "无进行中场次");
}
function updateSourceSelect(sources) {
  const ids = sources.map(source => source.source_id).join("|");
  if (sourceSelect.dataset.ids !== ids) {
    sourceSelect.dataset.ids = ids;
    clear(sourceSelect);
    for (const source of sources) {
      const option = element("option", "", sourceLabel(source));
      option.value = source.source_id;
      sourceSelect.appendChild(option);
    }
  }
  if (!sources.some(source => source.source_id === selectedSourceId)) {
    selectedSourceId = sources.length ? sources[0].source_id : null;
  }
  if (selectedSourceId) sourceSelect.value = selectedSourceId;
  sourceSelect.disabled = !sources.length;
}
function renderFreshness(game) {
  const freshness = game.freshness || {};
  text(document.querySelector("#freshness"), "牌桌 seq " + (freshness.snapshot_seq ?? "—") + " · 事件 seq " + (freshness.latest_event_seq ?? "—") + " · " + freshness.message);
}
function selectGame(gameId) {
  if (!gameId || gameId === selectedGameId) return;
  selectedGameId = gameId;
  selectedSourceId = null;
  renderedSignature = null;  // 切换场次后强制重绘牌桌
  render();
}
function render() {
  const games = activeGames();
  if (!games.some(game => game.game_id === selectedGameId)) {
    // 原场次结束或首轮加载：切到排序后的第一桌。
    selectedGameId = games.length ? games[0].game_id : null;
    selectedSourceId = null;
    renderedSignature = null;
  }
  renderSidebar(games);
  updateSourceSelect(sourcesForSelectedGame());
  const source = selectedSource();
  const game = selectedGame();
  const hasBoard = Boolean(game?.observation);
  emptyState.hidden = hasBoard;
  gameView.hidden = !hasBoard;
  if (!hasBoard) {
    renderedSignature = null;
    renderIssues(source);
    return;
  }
  const signature = gameSignature(game);
  if (signature !== renderedSignature) {
    renderGame(game);
    renderedSignature = signature;
  }
  renderFreshness(game);
  renderIssues(source);
  scheduleFitBoard();
}
async function refresh() {
  try {
    const response = await fetch("/api/snapshot", { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    current = await response.json();
    connection.className = "connection ok";
    text(connection, "已读取 · " + formatTime(current.generated_at_unix_ms));
    text(lastRefresh, "更新于 " + formatTime(current.generated_at_unix_ms));
    render();
  } catch (error) {
    connection.className = "connection failed";
    text(connection, "读取失败 · " + error.message);
  }
}
gameList.addEventListener("click", event => {
  const button = event.target.closest(".game-item-button");
  if (button) selectGame(button.dataset.gameId);
});
sourceSelect.addEventListener("change", () => {
  selectedSourceId = sourceSelect.value;
  renderedSignature = null;
  render();
});
refreshButton.addEventListener("click", refresh);
refresh();
refreshTimer = window.setInterval(refresh, 750);
window.addEventListener("resize", scheduleFitBoard);
window.addEventListener("beforeunload", () => window.clearInterval(refreshTimer));
if (typeof ResizeObserver === "function" && boardFit) {
  // 窗口尺寸、侧栏折叠等变化都会改变可用区域，交给观察器统一触发缩放。
  new ResizeObserver(scheduleFitBoard).observe(boardFit);
}
