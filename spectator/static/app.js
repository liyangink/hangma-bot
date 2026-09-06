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
function appendTile(parent, tile, drawn = false) {
  const node = element("span", "tile" + (drawn ? " drawn" : ""), tile);
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
  const pid = source.participant_id ? " · " + source.participant_id : "";
  const mode = source.mode ? " · " + source.mode : "";
  return source.role + pid + mode + " · " + source.run_id;
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
function selectedSource() { return (current?.sources || []).find(source => source.source_id === selectedSourceId) || null; }
function selectedGame() { return selectedSource()?.games?.find(game => game.game_id === selectedGameId) || null; }

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
function renderScores(scores) {
  for (let seat = 0; seat < 4; seat += 1) text(document.querySelector("#score-" + seat), scores?.[seat]);
}
function renderMelds(melds) {
  const node = document.querySelector("#melds");
  clear(node);
  let count = 0;
  (melds || []).forEach((seatMelds, seat) => {
    (seatMelds || []).forEach(meld => {
      count += 1;
      const row = element("div", "meld-row");
      row.appendChild(element("span", "", "座位 " + seat + " · " + (meld.kind || "副露")));
      const tiles = element("span", "tiles");
      (meld.tiles || []).forEach(tile => appendTile(tiles, tile));
      row.appendChild(tiles);
      node.appendChild(row);
    });
  });
  if (!count) node.appendChild(element("p", "muted", "暂无副露。"));
}
function renderDiscards(discards) {
  const node = document.querySelector("#discards");
  clear(node);
  for (let seat = 0; seat < 4; seat += 1) {
    const river = element("article", "river");
    river.appendChild(element("span", "river-title", "座位 " + seat));
    const tiles = element("div", "tiles");
    for (const tile of (discards?.[seat] || [])) appendTile(tiles, tile);
    river.appendChild(tiles);
    node.appendChild(river);
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
  text(document.querySelector("#my-seat"), "本家座位 " + (observation.seat ?? "—"));
  const freshness = game.freshness || {};
  text(document.querySelector("#freshness"), "牌桌 seq " + (freshness.snapshot_seq ?? "—") + " · 事件 seq " + (freshness.latest_event_seq ?? "—") + " · " + freshness.message);
  const warning = document.querySelector("#warning");
  warning.hidden = !freshness.event_ahead_of_table_snapshot;
  text(warning, freshness.event_ahead_of_table_snapshot ? "收到更晚的增量事件。为避免错误推演，牌桌仍展示最后一份完整观察；请结合右侧事件列表阅读。" : "");
  renderScores(observation.scores);
  renderTiles("#my-hand", observation.my_hand, observation.drawn_tile);
  text(document.querySelector("#drawn-tile"), observation.drawn_tile ? "刚摸牌（黄框）：" + observation.drawn_tile : "当前没有单列摸牌。");
  const rule = observation.rule_state || {};
  renderFacts("#rule-state", [["财神", rule.wealth_god], ["爆头", rule.baotou === true ? "是" : rule.baotou === false ? "否" : "未知"], ["动作链", rule.chain_count], ["抓打圈", rule.catch_play === true ? "是" : rule.catch_play === false ? "否" : "未知"]]);
  text(document.querySelector("#turn-state"), (observation.phase || "未知阶段") + " · 行动座位 " + (observation.turn_seat ?? "—"));
  renderFacts("#table-facts", [["庄家", observation.dealer_seat], ["响应座位", (observation.responding_seats || []).join("，") || "无"], ["牌墙余量", observation.remaining_tile_count], ["最近弃牌", observation.last_discard ? (observation.last_discard.tile || observation.last_discard) : "无"], ["观察来源", game.observation_source]]);
  renderMelds(observation.melds);
  renderDiscards(observation.discards);
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
  const sources = current?.sources || [];
  selectedSourceId = updateOptions(sourceSelect, sources, item => item.source_id, sourceLabel, selectedSourceId);
  sourceSelect.disabled = !sources.length;
  const source = selectedSource();
  selectedGameId = updateOptions(gameSelect, source?.games || [], item => item.game_id, item => item.game_id, selectedGameId);
  gameSelect.disabled = !(source?.games?.length);
  const game = selectedGame();
  emptyState.hidden = Boolean(sources.length && game?.observation);
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
sourceSelect.addEventListener("change", () => { selectedSourceId = sourceSelect.value; selectedGameId = null; render(); });
gameSelect.addEventListener("change", () => { selectedGameId = gameSelect.value; render(); });
refreshButton.addEventListener("click", refresh);
refresh();
refreshTimer = window.setInterval(refresh, 750);
window.addEventListener("beforeunload", () => window.clearInterval(refreshTimer));
