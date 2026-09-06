"use strict";

const sourceSelect = document.querySelector("#source-select");
const gameSelect = document.querySelector("#game-select");
const refreshButton = document.querySelector("#refresh-button");
const connection = document.querySelector("#connection");
const emptyState = document.querySelector("#empty-state");
const gameView = document.querySelector("#game-view");
const issues = document.querySelector("#issues");

let current = null;
let selectedSourceId = null;
let selectedGameId = null;
let refreshTimer = null;

function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function text(node, value) { node.textContent = value === null || value === undefined || value === "" ? "—" : String(value); }
function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined) text(node, value);
  return node;
}
function tileFace(tile) {
  const matched = /^([1-9])([wbt])$/.exec(tile || "");
  if (!matched) {
    const character = tile || "?";
    return {
      kind: "honor" + (character === "中" || character === "发" ? " honor-red" : ""),
      character,
      label: character === "?" ? "未知牌" : character,
    };
  }
  const suits = {
    w: {character: "萬", label: "万"},
    b: {character: "筒", label: "筒"},
    t: {character: "索", label: "条"},
  };
  return {
    kind: "number " + matched[2],
    rank: matched[1],
    character: suits[matched[2]].character,
    label: matched[1] + suits[matched[2]].label,
  };
}
function appendTile(parent, tile, drawn = false, lastDiscard = false) {
  const face = tileFace(tile);
  const classes = "tile tile-" + face.kind.replace(" ", " tile-") + (drawn ? " drawn" : "") + (lastDiscard ? " last-discard" : "");
  const node = element("span", classes);
  node.setAttribute("aria-label", face.label);
  if (face.rank) {
    node.appendChild(element("span", "tile-rank", face.rank));
    node.appendChild(element("span", "tile-suit", face.character));
  } else {
    node.appendChild(element("span", "tile-honor", face.character));
  }
  parent.appendChild(node);
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
function updateOptions(select, items, getId, getLabel, selectedId) {
  const prior = selectedId;
  clear(select);
  for (const item of items) {
    const option = element("option", "", getLabel(item));
    option.value = getId(item);
    select.appendChild(option);
  }
  const exists = items.some(item => getId(item) === prior);
  select.value = exists ? prior : (items.length ? getId(items[0]) : "");
  return select.value || null;
}
function activeGames() {
  // 四个 Token 可能都记录同一个官方场次；按 game_id 聚合后让人只选一次。
  const byId = new Map();
  for (const source of (current?.sources || [])) {
    for (const game of (source.games || [])) {
      if (!game.finished && !byId.has(game.game_id)) byId.set(game.game_id, game);
    }
  }
  return [...byId.values()].sort((left, right) => left.game_id.localeCompare(right.game_id));
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
  for (const tile of (tiles || [])) appendTile(node, tile, tile === drawnTile);
  if (!tiles || !tiles.length) node.appendChild(element("span", "muted", "当前没有可显示的本家手牌。"));
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
  for (let index = 0; index < safeCount; index += 1) {
    const back = element("span", "tile tile-back", "");
    back.setAttribute("aria-label", "暗牌");
    node.appendChild(back);
  }
  node.appendChild(element("span", "muted", safeCount ? "暗手 " + safeCount + " 张" : "暗手张数未知"));
}
function renderSeatMelds(id, melds) {
  const node = document.querySelector(id);
  clear(node);
  for (const meld of (melds || [])) {
    const group = element("div", "seat-meld");
    group.setAttribute("aria-label", meld.kind || "副露");
    for (const tile of (meld.tiles || [])) appendTile(group, tile);
    node.appendChild(group);
  }
}
function renderRiver(id, tiles, lastDiscard) {
  const node = document.querySelector(id);
  clear(node);
  const lastIndex = lastDiscard && tiles ? tiles.lastIndexOf(lastDiscard.tile) : -1;
  (tiles || []).forEach((tile, index) => appendTile(node, tile, false, index === lastIndex));
}
function relativeSeat(mySeat, offset) {
  return Number.isInteger(mySeat) ? (mySeat + offset) % 4 : null;
}
function renderPerspective(observation) {
  const placements = [
    ["bottom", 0, "本家"],
    ["right", 1, "右侧座位"],
    ["top", 2, "对家"],
    ["left", 3, "左侧座位"],
  ];
  const mySeat = observation.seat;
  for (const [position, offset, name] of placements) {
    const seat = relativeSeat(mySeat, offset);
    const isMe = position === "bottom";
    const holder = document.querySelector("#player-" + position);
    holder.classList.toggle("is-turn", seat !== null && seat === observation.turn_seat);
    text(document.querySelector("#seat-label-" + position), name + " · 座位 " + (seat ?? "—"));
    text(document.querySelector("#score-" + position), seat === null ? null : observation.scores?.[seat]);
    renderSeatMelds("#melds-" + position, seat === null ? [] : observation.melds?.[seat]);
    renderRiver("#river-" + position, seat === null ? [] : observation.discards?.[seat], seat === null || observation.last_discard?.seat !== seat ? null : observation.last_discard);
    if (!isMe) renderConcealedHand("#hand-" + position, seat === null ? null : observation.hand_counts?.[seat]);
  }
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
  text(document.querySelector("#freshness"), "牌桌 seq " + (freshness.snapshot_seq ?? "—") + " · 事件 seq " + (freshness.latest_event_seq ?? "—") + " · " + freshness.message);
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
function render() {
  const games = activeGames();
  selectedGameId = updateOptions(gameSelect, games, item => item.game_id, item => item.game_id, selectedGameId);
  gameSelect.disabled = !games.length;
  const sources = sourcesForSelectedGame();
  selectedSourceId = updateOptions(sourceSelect, sources, item => item.source_id, sourceLabel, selectedSourceId);
  sourceSelect.disabled = !sources.length;
  const source = selectedSource();
  const game = selectedGame();
  emptyState.hidden = Boolean(games.length && game?.observation);
  gameView.hidden = !game?.observation;
  if (game) renderGame(game);
  renderIssues(source);
}
async function refresh() {
  try {
    const response = await fetch("/api/snapshot", { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    current = await response.json();
    connection.className = "connection ok";
    text(connection, "已读取 · " + formatTime(current.generated_at_unix_ms));
    render();
  } catch (error) {
    connection.className = "connection failed";
    text(connection, "读取失败 · " + error.message);
  }
}
gameSelect.addEventListener("change", () => { selectedGameId = gameSelect.value; selectedSourceId = null; render(); });
sourceSelect.addEventListener("change", () => { selectedSourceId = sourceSelect.value; render(); });
refreshButton.addEventListener("click", refresh);
refresh();
refreshTimer = window.setInterval(refresh, 750);
window.addEventListener("beforeunload", () => window.clearInterval(refreshTimer));
