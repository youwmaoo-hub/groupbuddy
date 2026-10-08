"use strict";

// 面板前端：只做展示与转发，所有权限判定都在后端（前端隐藏按钮不是授权）。
const TOKEN_KEY = "groupbuddy.panel.token";

let session = null;
let groups = [];

const $ = (id) => document.getElementById(id);

function token() {
  return sessionStorage.getItem(TOKEN_KEY) || "";
}

async function api(path, options) {
  const opts = options || {};
  const headers = Object.assign({}, opts.headers || {});
  if (token()) headers["Authorization"] = "Bearer " + token();
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, Object.assign({}, opts, { headers }));
  const text = await response.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch (error) {
    payload = null;
  }
  if (!response.ok) {
    const message = payload && payload.error ? payload.error.message : "请求失败（HTTP " + response.status + "）";
    throw new Error(message);
  }
  return payload;
}

function setStatus(element, text, ok) {
  element.textContent = text || "";
  element.className = ok === undefined ? "status" : ok ? "status ok" : "status err";
}

function fmtTime(seconds) {
  if (!seconds) return "—";
  const date = new Date(seconds * 1000);
  return date.toLocaleString();
}

function fmtDuration(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  const total = Math.max(0, Math.floor(seconds));
  const day = Math.floor(total / 86400);
  const hour = Math.floor((total % 86400) / 3600);
  const minute = Math.floor((total % 3600) / 60);
  if (day) return day + " 天 " + hour + " 小时";
  if (hour) return hour + " 小时 " + minute + " 分钟";
  return minute + " 分钟";
}

function fmtBool(value) {
  if (value === null || value === undefined) return "—";
  return value ? "正常" : "异常";
}

function define(term, value) {
  const dt = document.createElement("dt");
  dt.textContent = term;
  const dd = document.createElement("dd");
  dd.textContent = value;
  return [dt, dd];
}

function renderOverview(data) {
  const list = $("overview");
  list.textContent = "";
  const quota = (daily, monthly) => {
    if (!daily && !monthly) return "未设置限额";
    return "日 " + (daily || "不限") + " / 月 " + (monthly || "不限");
  };
  const rows = [
    ["实例", data.instance || "—"],
    ["心跳", data.heartbeat_at ? "正常（" + Math.round(data.heartbeat_age_s || 0) + " 秒前）" : "没有心跳文件"],
    ["机器人状态", fmtBool(data.health_ok)],
    ["数据库", fmtBool(data.db_ok)],
    ["运行时长", fmtDuration(data.uptime_s)],
    ["最后处理更新", fmtTime(data.last_update_at)],
    ["出站队列", data.outbound_pending === null ? "—" : data.outbound_pending + " 条待发"],
    ["群 / 消息总数", data.chats + " / " + data.messages],
    ["今日模型调用", data.calls + " 次"],
    ["今日 Token", "输入 " + data.input_tokens + " / 缓存 " + data.cached_tokens + " / 输出 " + data.output_tokens],
    ["今日工具调用", data.tool_calls + " 次"],
    ["配额", quota(data.quota_daily_tokens, data.quota_monthly_tokens)],
  ];
  for (const [term, value] of rows) {
    list.append(...define(term, String(value)));
  }
}

function renderGroups() {
  const body = $("groups").querySelector("tbody");
  body.textContent = "";
  if (!groups.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 8;
    td.textContent = "还没有任何群消息或群设置。";
    tr.append(td);
    body.append(tr);
    return;
  }
  for (const group of groups) {
    const tr = document.createElement("tr");
    const cells = [
      String(group.chat_id),
      group.mode,
      group.enabled_tools.join("、") || "无",
      group.sticker_cooldown + " 秒",
      group.persona_set ? "已设置" : "默认",
      String(group.messages),
      fmtTime(group.last_message_at),
    ];
    for (const value of cells) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(td);
    }
    const action = document.createElement("td");
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "mini";
    edit.textContent = "编辑";
    edit.disabled = Boolean(session && session.readonly);
    edit.addEventListener("click", () => openEditor(group.chat_id));
    action.append(edit);
    tr.append(action);
    body.append(tr);
  }
}

function fieldValue(group, field) {
  if (field.kind === "bool") return group.toggles[field.name] ? "on" : "off";
  if (field.kind === "mode") return group.mode;
  if (field.kind === "int") return String(group.sticker_cooldown);
  return group.persona_override || "";
}

function buildControl(group, field) {
  let control;
  if (field.kind === "bool") {
    control = document.createElement("select");
    for (const [value, label] of [["on", "开"], ["off", "关"]]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      control.append(option);
    }
  } else if (field.kind === "mode") {
    control = document.createElement("select");
    for (const name of field.choices) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      control.append(option);
    }
  } else if (field.kind === "int") {
    control = document.createElement("input");
    control.type = "number";
    control.min = "0";
    if (field.maximum) control.max = String(field.maximum);
  } else {
    control = document.createElement("textarea");
    control.rows = 3;
  }
  control.value = fieldValue(group, field);
  return control;
}

async function openEditor(chatId) {
  const editor = $("group-editor");
  const fields = $("edit-fields");
  setStatus($("edit-status"), "");
  let group;
  try {
    group = (await api("/api/groups/" + chatId)).group;
  } catch (error) {
    setStatus($("groups-status") || $("edit-status"), error.message, false);
    return;
  }
  $("edit-chat-id").textContent = String(chatId);
  fields.textContent = "";
  for (const field of session.fields) {
    const label = document.createElement("label");
    if (field.kind === "text") label.className = "wide";
    const caption = document.createElement("span");
    caption.textContent = field.name + (field.owner_only ? "（群主人设，留空即清除）" : "");
    const control = buildControl(group, field);
    const save = document.createElement("button");
    save.type = "button";
    save.className = "mini";
    save.textContent = "保存";
    save.addEventListener("click", async () => {
      save.disabled = true;
      try {
        const payload = await api("/api/groups/" + chatId + "/settings", {
          method: "PUT",
          body: JSON.stringify({ field: field.name, value: control.value }),
        });
        const updated = payload.group;
        const target = groups.find((item) => item.chat_id === chatId);
        if (target) {
          target.mode = updated.mode;
          target.sticker_cooldown = updated.sticker_cooldown;
          target.persona_set = Boolean(updated.persona_override);
          target.enabled_tools = Object.keys(updated.toggles).filter((key) => updated.toggles[key]);
        }
        renderGroups();
        setStatus($("edit-status"), "已保存：" + field.name, true);
      } catch (error) {
        setStatus($("edit-status"), error.message, false);
      } finally {
        save.disabled = false;
      }
    });
    label.append(caption, control, save);
    fields.append(label);
  }
  editor.hidden = false;
}

function renderCredentials(data) {
  $("env-file").textContent = data.env_file;
  const body = $("credentials").querySelector("tbody");
  body.textContent = "";
  for (const item of data.credentials) {
    const tr = document.createElement("tr");
    for (const value of [item.name, item.configured ? "已配置" : "未配置", item.source]) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(td);
    }
    const inputCell = document.createElement("td");
    const input = document.createElement("input");
    input.type = "password";
    input.placeholder = "新值";
    input.autocomplete = "off";
    inputCell.append(input);
    const actionCell = document.createElement("td");
    const save = document.createElement("button");
    save.type = "button";
    save.className = "mini";
    save.textContent = "写入";
    save.addEventListener("click", async () => {
      if (!input.value) {
        setStatus($("credentials-status"), "请先填写新值。", false);
        return;
      }
      try {
        const payload = await api("/api/credentials/" + encodeURIComponent(item.name), {
          method: "PUT",
          body: JSON.stringify({ value: input.value }),
        });
        input.value = "";
        renderCredentials({ env_file: data.env_file, credentials: payload.credentials });
        setStatus($("credentials-status"), "已写入 " + item.name + "，重启机器人后生效。", true);
      } catch (error) {
        setStatus($("credentials-status"), error.message, false);
      }
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "mini danger";
    remove.textContent = "删除";
    remove.addEventListener("click", async () => {
      try {
        const payload = await api("/api/credentials/" + encodeURIComponent(item.name), { method: "DELETE" });
        renderCredentials({ env_file: data.env_file, credentials: payload.credentials });
        setStatus($("credentials-status"), "已删除 " + item.name + "，重启机器人后生效。", true);
      } catch (error) {
        setStatus($("credentials-status"), error.message, false);
      }
    });
    actionCell.append(save, remove);
    tr.append(inputCell, actionCell);
    body.append(tr);
  }
}

async function loadOverview() {
  try {
    renderOverview(await api("/api/overview"));
  } catch (error) {
    setStatus($("login-status"), error.message, false);
  }
}

async function loadGroups() {
  try {
    groups = (await api("/api/groups")).groups;
    renderGroups();
  } catch (error) {
    setStatus($("login-status"), error.message, false);
  }
}

async function loadCredentials() {
  if (session.readonly) return;
  try {
    renderCredentials(await api("/api/credentials"));
  } catch (error) {
    setStatus($("credentials-status"), error.message, false);
  }
}

async function loadLogs() {
  const lines = Number($("log-lines").value) || 200;
  try {
    const payload = await api("/api/logs?lines=" + encodeURIComponent(lines));
    $("logs").textContent = payload.lines.length ? payload.lines.join("\n") : "（日志文件还不存在）";
  } catch (error) {
    $("logs").textContent = error.message;
  }
}

async function connect() {
  sessionStorage.setItem(TOKEN_KEY, $("token").value.trim());
  try {
    session = await api("/api/session");
  } catch (error) {
    session = null;
    setStatus($("login-status"), error.message, false);
    return;
  }
  $("login").hidden = true;
  $("panel").hidden = false;
  $("credentials-card").hidden = Boolean(session.readonly);
  setStatus($("login-status"), "");
  await Promise.all([loadOverview(), loadGroups(), loadCredentials(), loadLogs()]);
}

function main() {
  $("connect").addEventListener("click", connect);
  $("token").addEventListener("keydown", (event) => {
    if (event.key === "Enter") connect();
  });
  $("refresh-overview").addEventListener("click", loadOverview);
  $("refresh-groups").addEventListener("click", loadGroups);
  $("refresh-credentials").addEventListener("click", loadCredentials);
  $("refresh-logs").addEventListener("click", loadLogs);
  $("close-editor").addEventListener("click", () => {
    $("group-editor").hidden = true;
  });
  if (token()) {
    $("token").value = token();
    connect();
  }
}

main();
