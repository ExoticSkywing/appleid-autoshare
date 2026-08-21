"use strict";

const STORAGE_KEY = "aid-relay-state-v1";
const requestHeaders = {
  "Content-Type": "application/json",
  "X-Requested-With": "XMLHttpRequest",
};

const state = {
  config: null,
  token: "",
  account: null,
  purchaseLink: "",
  widgetId: null,
  busy: false,
  attempt: 1,
  copied: { username: false, password: false },
  usernameEntered: false,
  feedbackLocked: false,
  leftForAttempt: false,
  pendingAction: null,
  toastTimer: null,
  intent: "",
  loginSucceeded: false,
  resultsVisible: false,
};

const byId = (id) => document.getElementById(id);
const views = ["bootView", "verifyView", "accountView", "successView", "emptyView"];
const resultButtons = () => document.querySelectorAll("[data-result]");

function announce(text) {
  byId("message").textContent = text;
}

function hideCopyConfirmation() {
  window.clearTimeout(state.toastTimer);
  state.toastTimer = null;
  byId("copyToast").classList.add("hidden");
  byId("copyToast").classList.remove("is-visible");
}

function showCopyConfirmation(text, sourceButton = null) {
  const toast = byId("copyToast");
  byId("copyToastText").textContent = text;
  toast.classList.remove("hidden", "is-visible");
  void toast.offsetWidth;
  toast.classList.add("is-visible");
  if (sourceButton) {
    sourceButton.classList.remove("is-confirming");
    void sourceButton.offsetWidth;
    sourceButton.classList.add("is-confirming");
    window.setTimeout(() => sourceButton.classList.remove("is-confirming"), 850);
  }
  if (navigator.vibrate) navigator.vibrate(18);
  window.clearTimeout(state.toastTimer);
  state.toastTimer = window.setTimeout(() => {
    toast.classList.add("hidden");
    toast.classList.remove("is-visible");
  }, 2600);
  announce(text);
}

function saveSession() {
  try {
    if (!state.account) {
      sessionStorage.removeItem(STORAGE_KEY);
      return;
    }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      account: state.account,
      purchaseLink: state.purchaseLink,
      attempt: state.attempt,
      copied: state.copied,
      usernameEntered: state.usernameEntered,
      feedbackLocked: state.feedbackLocked,
      intent: state.intent,
      loginSucceeded: state.loginSucceeded,
      resultsVisible: state.resultsVisible,
    }));
  } catch (_) {
    // The current page remains fully usable when sessionStorage is unavailable.
  }
}

function clearSession() {
  try { sessionStorage.removeItem(STORAGE_KEY); } catch (_) { /* no-op */ }
}

function restoreSession() {
  try {
    const payload = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null");
    if (!payload || !payload.account || !payload.account.id || !payload.account.username || !payload.account.password) {
      return false;
    }
    state.account = payload.account;
    state.purchaseLink = typeof payload.purchaseLink === "string" ? payload.purchaseLink : "";
    state.attempt = Number.isInteger(payload.attempt) && payload.attempt > 0 ? payload.attempt : 1;
    state.copied = {
      username: Boolean(payload.copied && payload.copied.username),
      password: Boolean(payload.copied && payload.copied.password),
    };
    state.usernameEntered = Boolean(payload.usernameEntered) || Boolean(state.copied.password);
    state.feedbackLocked = Boolean(payload.feedbackLocked);
    state.intent = payload.intent === "other_app" ? "other_app" : "target_app";
    state.loginSucceeded = Boolean(payload.loginSucceeded);
    state.resultsVisible = Boolean(payload.resultsVisible);
    updateIntentUI();
    showAccount(state.account, { restored: true, feedbackLocked: state.feedbackLocked, resultsVisible: state.resultsVisible });
    if (state.resultsVisible) showResultChoices();
    return true;
  } catch (_) {
    clearSession();
    return false;
  }
}

async function jsonRequest(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    cache: "no-store",
    ...options,
    headers: { ...requestHeaders, ...(options.headers || {}) },
  });

  let payload = null;
  if (response.status !== 204) {
    try { payload = await response.json(); } catch (_) { payload = null; }
  }
  if (!response.ok) {
    const error = new Error(`request_failed_${response.status}`);
    error.status = response.status;
    error.code = payload && payload.error ? payload.error.code : "request_failed";
    throw error;
  }
  return payload;
}

function loadScript(url) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${CSS.escape(url)}"]`);
    if (existing) {
      existing.addEventListener("load", resolve, { once: true });
      existing.addEventListener("error", reject, { once: true });
      return;
    }
    const script = document.createElement("script");
    script.src = url;
    script.async = true;
    script.defer = true;
    script.addEventListener("load", resolve, { once: true });
    script.addEventListener("error", reject, { once: true });
    document.head.appendChild(script);
  });
}

function setPhase(phase, viewId) {
  document.documentElement.dataset.phase = phase;
  document.body.dataset.phase = phase;
  byId("relayStage").dataset.phase = phase;
  views.forEach((id) => byId(id).classList.toggle("hidden", id !== viewId));
  const labels = {
    boot: "安全通道准备中",
    verify: "等待访问验证",
    loading: "正在获取账号",
    ready: "账号已准备好",
    replacing: "正在更换账号",
    success: "本次流程已完成",
    empty: "共享账号已用尽",
    error: "操作需要重试",
  };
  byId("headerState").textContent = labels[phase] || labels.boot;
  byId("credential").setAttribute("aria-busy", ["boot", "loading", "replacing"].includes(phase) ? "true" : "false");
}

function runScanner() {
  const credential = byId("credential");
  credential.classList.remove("is-scanning");
  void credential.offsetWidth;
  credential.classList.add("is-scanning");
  window.setTimeout(() => credential.classList.remove("is-scanning"), 780);
}

function updateVerifyAction() {
  const button = byId("verifyButton");
  const label = byId("verifyButtonLabel");
  const hint = byId("verifyActionHint");
  const onVerifyView = !state.account && document.body.dataset.phase === "verify";
  let reason = "";
  let buttonLabel = "获取账号";

  if (!state.intent) {
    reason = "请先选择上方的下载目标；选择后才会显示人机验证。";
    buttonLabel = "先选择下载目标";
  } else if (!state.token) {
    reason = "目标已选择，请完成上方的人机验证。";
    buttonLabel = "完成验证后获取";
  }

  const blocked = Boolean(reason) || state.busy;
  button.classList.toggle("is-blocked", blocked);
  button.setAttribute("aria-disabled", String(blocked));
  label.textContent = state.busy ? "正在获取账号" : buttonLabel;
  hint.textContent = state.busy ? "正在为你分配账号，请稍候。" : reason;
  hint.classList.toggle("hidden", !state.busy && !reason);
  byId("turnstileWidget").classList.toggle("hidden", !state.intent);

  if (!onVerifyView) return;
  if (state.busy) {
    byId("credentialState").textContent = "正在分配账号";
    byId("verifyTitle").textContent = "正在获取账号";
    byId("verifyHint").textContent = "请保持页面打开，很快就好。";
    return;
  }
  if (state.token && state.intent) {
    byId("credentialState").textContent = "验证已通过";
    byId("verifyTitle").textContent = "可以获取账号";
    byId("verifyHint").textContent = "目标与验证都已完成，点击下方按钮获取账号。";
    byId("headerState").textContent = "验证已通过";
    byId("statusLight").classList.add("is-ready");
  } else if (state.intent) {
    byId("credentialState").textContent = "等待访问验证";
    byId("verifyTitle").textContent = "完成访问验证";
    byId("verifyHint").textContent = "验证完成后即可获取账号。";
    byId("headerState").textContent = "等待访问验证";
    byId("statusLight").classList.remove("is-ready");
  } else {
    byId("credentialState").textContent = "等待选择目标";
    byId("verifyTitle").textContent = "先选择下载目标";
    byId("verifyHint").textContent = "选择目标后，再完成访问验证。";
    byId("headerState").textContent = "等待选择目标";
    byId("statusLight").classList.remove("is-ready");
  }
}

function setBusy(busy) {
  state.busy = busy;
  updateVerifyAction();
  document.querySelectorAll("[data-login-result], [data-result]").forEach((button) => {
    button.disabled = busy || state.feedbackLocked || !state.copied.password;
  });
  document.querySelectorAll("[data-copy]").forEach((button) => { button.setAttribute("aria-disabled", String(busy)); });
}

function hideRecovery() {
  byId("recoveryPanel").classList.add("hidden");
  state.pendingAction = null;
}

function showRecovery(title, text, action) {
  byId("recoveryTitle").textContent = title;
  byId("recoveryText").textContent = text;
  byId("recoveryPanel").classList.remove("hidden");
  state.pendingAction = action;
  document.documentElement.dataset.phase = "error";
  document.body.dataset.phase = "error";
}

function updateIntentUI() {
  document.querySelectorAll("[data-intent]").forEach((button) => {
    const selected = button.dataset.intent === state.intent;
    button.setAttribute("aria-pressed", String(selected));
    button.classList.toggle("is-selected", selected);
  });
  byId("intentPanel").classList.toggle("is-locked", Boolean(state.account));
  document.querySelectorAll("[data-intent]").forEach((button) => { button.disabled = Boolean(state.account); });
  updateVerifyAction();
}

function selectIntent(intent) {
  if (state.account || state.busy) return;
  state.intent = intent === "other_app" ? "other_app" : "target_app";
  byId("intentPanel").classList.remove("needs-attention");
  updateIntentUI();
  if (state.token) {
    updateVerifyAction();
    byId("verifyButton").focus({ preventScroll: true });
    announce("目标已选择，验证也已完成。现在可以获取账号。" );
  } else {
    announce("目标已选择，可以继续完成访问验证。" );
  }
}

function setStoreLink(url, exhausted = false) {
  state.purchaseLink = typeof url === "string" ? url : "";
  const link = byId("storeLink");
  const emptyLink = byId("emptyStoreLink");
  if (!state.purchaseLink) {
    link.removeAttribute("href");
    link.classList.add("hidden");
    emptyLink.removeAttribute("href");
    emptyLink.classList.add("hidden");
    return;
  }
  link.href = state.purchaseLink;
  emptyLink.href = state.purchaseLink;
  emptyLink.classList.toggle("hidden", !exhausted);
  link.classList.toggle("hidden", exhausted);
  const strong = link.querySelector("strong");
  const small = link.querySelector("small");
  strong.textContent = "不想继续尝试？";
  small.textContent = "购买专属账号，一次解决";
}

function showResultChoices({ returned = false } = {}) {
  hideCopyConfirmation();
  state.resultsVisible = true;
  const panel = byId("feedbackPanel");
  panel.classList.add("is-ready", "is-results");
  byId("credential").classList.add("is-result-mode");
  panel.classList.toggle("is-returned", returned);
  byId("feedbackStep").textContent = returned ? "欢迎回来" : "请选择结果";
  byId("feedbackTitle").textContent = "能否登录 App Store？";
  byId("copyProgress").textContent = "登录成功可继续；登录不上会自动换号。";
  byId("accountStep").classList.add("is-complete");
  byId("accountStep").classList.remove("is-current");
  byId("accountStep").querySelector("span").textContent = "✓";
  byId("passwordStep").classList.add("is-complete");
  byId("passwordStep").classList.remove("is-current");
  byId("passwordStep").querySelector("span").textContent = "✓";
  byId("resultStep").classList.add("is-current");
  byId("accountView").classList.add("is-summary");
  byId("attemptCount").classList.add("hidden");
  byId("resultCredentialHeading").classList.remove("hidden");
  byId("appStoreInstruction").classList.add("hidden");
  byId("showResultsButton").classList.add("hidden");
  byId("targetAppCheck").classList.add("hidden");
  byId("resultActions").classList.remove("hidden");
  document.querySelectorAll("[data-login-result], [data-result]").forEach((button) => {
    button.disabled = state.busy || state.feedbackLocked;
  });
  updateCopyUI();
  saveSession();
  if (returned) window.setTimeout(() => byId("feedbackTitle").focus({ preventScroll: true }), 80);
}

function showTargetAppCheck() {
  hideCopyConfirmation();
  state.loginSucceeded = true;
  state.resultsVisible = true;
  byId("feedbackPanel").classList.add("is-ready", "is-results");
  byId("intentPanel").classList.add("hidden");
  byId("credential").classList.add("is-result-mode");
  byId("accountView").classList.add("is-summary");
  byId("attemptCount").classList.add("hidden");
  byId("resultCredentialHeading").classList.remove("hidden");
  byId("feedbackStep").textContent = "最后一步";
  byId("feedbackTitle").textContent = "检查下载按钮";
  byId("copyProgress").textContent = "打开应用页面；看到云朵下载图标表示目标已达成。";
  byId("resultActions").classList.add("hidden");
  byId("appStoreInstruction").classList.add("hidden");
  byId("showResultsButton").classList.add("hidden");
  byId("targetAppCheck").classList.remove("hidden");
  byId("resultStep").classList.add("is-current");
  updateCopyUI();
  saveSession();
  announce("登录成功。现在检查是否可以下载目标应用。" );
}

function updateCopyUI() {
  const usernameCopied = Boolean(state.copied.username);
  const usernameEntered = Boolean(state.usernameEntered);
  const passwordCopied = Boolean(state.copied.password);
  const copiedCount = Number(usernameCopied) + Number(passwordCopied);
  document.querySelectorAll("[data-copy]").forEach((button) => {
    const key = button.dataset.copy;
    const copied = Boolean(state.copied[key]);
    button.classList.toggle("is-copied", copied);
    const label = button.querySelector(".copy-label");
    const resultMode = state.resultsVisible || state.loginSucceeded;
    label.textContent = resultMode ? "再次复制" : (copied ? "已复制" : "复制");
    button.setAttribute("aria-label", resultMode ? `再次复制${key === "username" ? " Apple ID" : "密码"}` : (copied ? `${key === "username" ? "Apple ID" : "密码"}已复制` : `复制${key === "username" ? " Apple ID" : "密码"}`));
  });

  const panel = byId("feedbackPanel");
  const title = byId("feedbackTitle");
  const progress = byId("copyProgress");
  const step = byId("feedbackStep");
  panel.classList.toggle("is-ready", usernameCopied);
  byId("targetAppCheck").classList.toggle("hidden", !state.loginSucceeded);

  byId("accountStep").classList.toggle("is-current", !usernameEntered);
  byId("accountStep").classList.toggle("is-complete", usernameEntered);
  byId("accountStep").querySelector("span").textContent = usernameEntered ? "✓" : "1";
  byId("passwordStep").classList.toggle("is-current", usernameEntered && !passwordCopied);
  byId("passwordStep").classList.toggle("is-complete", passwordCopied);
  byId("passwordStep").querySelector("span").textContent = passwordCopied ? "✓" : "2";
  byId("resultStep").classList.toggle("is-current", passwordCopied);

  const usernameButton = document.querySelector('[data-copy="username"]');
  const passwordButton = document.querySelector('[data-copy="password"]');
  usernameButton.classList.toggle("is-primary-copy", !usernameCopied);
  passwordButton.classList.toggle("is-primary-copy", usernameCopied && !passwordCopied);

  byId("appStoreInstruction").classList.toggle("hidden", !usernameCopied || passwordCopied || state.resultsVisible);
  byId("accountEnteredButton").classList.toggle("hidden", usernameEntered);
  byId("showResultsButton").classList.toggle("hidden", !passwordCopied || state.resultsVisible);
  byId("resultActions").classList.toggle("hidden", !state.resultsVisible || state.loginSucceeded);
  document.querySelectorAll("[data-login-result], [data-result]").forEach((button) => {
    button.disabled = state.busy || state.feedbackLocked || !passwordCopied;
  });

  if (copiedCount === 0) {
    step.textContent = "当前任务";
    title.textContent = "复制 Apple ID";
    progress.textContent = "复制后，打开 App Store 并进入账户登录页。";
  } else if (!usernameEntered) {
    step.textContent = "下一步";
    title.textContent = "打开 App Store 输入账号";
    progress.textContent = "Apple ID 已复制。打开 App Store 后，点右上角账户图标粘贴。";
  } else if (!passwordCopied) {
    step.textContent = "现在";
    title.textContent = "一键复制密码";
    progress.textContent = "账号已输入。点击下方按钮复制密码，再返回 App Store 粘贴。";
  } else if (!state.resultsVisible) {
    step.textContent = "登录后";
    title.textContent = "确认能否登录";
    progress.textContent = "密码已复制。返回 App Store 输入密码，完成后回来继续。";
  }
}

function showAccount(account, options = {}) {
  state.account = account;
  state.leftForAttempt = false;
  state.resultsVisible = Boolean(options.resultsVisible);
  byId("credential").classList.toggle("is-result-mode", state.resultsVisible);
  byId("accountView").classList.toggle("is-summary", state.resultsVisible);
  byId("attemptCount").classList.toggle("hidden", state.resultsVisible);
  byId("resultCredentialHeading").classList.toggle("hidden", !state.resultsVisible);
  byId("feedbackPanel").classList.remove("is-returned", "is-results");
  byId("username").textContent = account.username;
  byId("password").textContent = account.password;
  byId("region").textContent = account.region || "";
  byId("region").classList.toggle("hidden", !account.region || account.region === "Unknown");
  byId("attemptCount").textContent = `本次第 ${state.attempt} 组`;
  byId("resultAttemptLabel").textContent = `第 ${state.attempt} 组`;
  byId("credentialState").textContent = options.restored ? "已恢复当前账号" : "账号已准备好";
  byId("attemptCount").classList.toggle("hidden", state.resultsVisible);
  state.feedbackLocked = Boolean(options.feedbackLocked);
  byId("feedbackPanel").classList.remove("hidden");
  updateIntentUI();
  byId("archiveEdge").classList.remove("hidden");
  setPhase("ready", "accountView");
  updateCopyUI();
  setStoreLink(state.purchaseLink);
  saveSession();
  hideRecovery();
  runScanner();
  announce(options.restored ? "已恢复你刚才使用的账号，可以继续复制和反馈。" : "账号已准备好。请复制账号和密码，只在 App Store 登录。" );
}

function showSuccess() {
  hideCopyConfirmation();
  setPhase("success", "successView");
  byId("resultStep").classList.add("is-complete");
  byId("resultStep").classList.remove("is-current");
  byId("resultStep").querySelector("span").textContent = "✓";
  byId("intentPanel").classList.add("hidden");
  byId("credentialState").textContent = "反馈已记录";
  byId("feedbackPanel").classList.add("hidden");
  byId("storeLink").classList.add("hidden");
  byId("archiveEdge").classList.add("hidden");
  state.account = null;
  state.copied = { username: false, password: false };
  state.usernameEntered = false;
  state.loginSucceeded = false;
  state.resultsVisible = false;
  clearSession();
  hideRecovery();
  runScanner();
  announce("成功达成目标，结果已记录，本次流程已完成。" );
}

function showExhausted(purchaseLink) {
  hideCopyConfirmation();
  byId("intentPanel").classList.add("hidden");
  state.account = null;
  state.copied = { username: false, password: false };
  state.usernameEntered = false;
  state.loginSucceeded = false;
  state.resultsVisible = false;
  clearSession();
  byId("feedbackPanel").classList.add("hidden");
  byId("credentialState").textContent = "没有更多共享凭证";
  byId("attemptCount").textContent = `已尝试 ${state.attempt} 组`;
  setPhase("empty", "emptyView");
  setStoreLink(purchaseLink, true);
  hideRecovery();
  announce(purchaseLink ? "共享账号已试完，可以购买专属账号。" : "共享账号已试完，请稍后再试。" );
}

async function revealOne({ replacement = false } = {}) {
  hideRecovery();
  if (replacement) {
    setPhase("replacing", "accountView");
    byId("credentialState").textContent = "正在归档并更换";
    byId("relayStage").classList.add("is-handoff-out");
    announce("结果已记录，正在自动更换下一组账号。" );
    await new Promise((resolve) => window.setTimeout(resolve, 360));
  } else {
    setPhase("loading", "bootView");
    byId("credentialState").textContent = "正在选择最佳账号";
  }

  try {
    const ticket = await jsonRequest("/api/v2/reveal-ticket", { method: "POST", body: "{}" });
    const payload = await jsonRequest("/api/v2/accounts/reveal", {
      method: "POST",
      body: JSON.stringify({ ticket: ticket.ticket, intent: state.intent }),
    });
    const accounts = Array.isArray(payload.accounts) ? payload.accounts : [];
    state.purchaseLink = payload.purchase_link || state.purchaseLink || "";
    byId("relayStage").classList.remove("is-handoff-out");

    if (payload.exhausted || !accounts.length) {
      showExhausted(state.purchaseLink);
      return;
    }

    if (replacement) {
      state.attempt += 1;
      state.copied = { username: false, password: false };
      state.usernameEntered = false;
      state.loginSucceeded = false;
      state.resultsVisible = false;
      byId("relayStage").classList.add("is-handoff");
      window.setTimeout(() => byId("relayStage").classList.remove("is-handoff"), 900);
    }
    showAccount(accounts[0]);
  } catch (error) {
    byId("relayStage").classList.remove("is-handoff-out");
    if (state.account) {
      showAccount(state.account, { restored: true, feedbackLocked: state.feedbackLocked });
      showRecovery("换号没有完成", "当前账号还在，网络恢复后可以继续重试换号。", () => revealOne({ replacement: true }));
    } else if (error.status === 403) {
      showVerify("会话已失效，请重新完成验证。" );
    } else {
      setPhase("error", "bootView");
      showRecovery("暂时无法获取账号", error.status === 429 ? "请求有点频繁，请稍等后再重试。" : "安全通道没有连上，请检查网络后重试。", () => revealOne());
    }
    return false;
  }
  return true;
}

async function verifyAndReveal() {
  if (!state.token || !state.intent || state.busy) return;
  setBusy(true);
  setPhase("loading", "bootView");
  byId("credentialState").textContent = "正在验证访问";
  announce("正在验证并获取账号。" );
  try {
    await jsonRequest("/api/v2/session/verify", {
      method: "POST",
      body: JSON.stringify({ token: state.token }),
    });
    await revealOne();
  } catch (error) {
    if (error.status === 403) {
      state.token = "";
      if (window.turnstile && state.widgetId !== null) window.turnstile.reset(state.widgetId);
      showVerify("验证未通过，请重新完成下方验证。" );
    }
  } finally {
    setBusy(false);
  }
}

async function submitFeedback(result) {
  if (!state.account || state.busy) return;
  setBusy(true);
  hideRecovery();
  const currentAccountId = state.account.id;
  announce("正在记录使用结果。" );

  try {
    await jsonRequest("/api/v2/accounts/feedback", {
      method: "POST",
      body: JSON.stringify({ account_id: currentAccountId, result }),
    });
    state.feedbackLocked = true;
    resultButtons().forEach((button) => { button.disabled = true; });
    if (result === "shadowrocket_available" || result === "login_success") {
      showSuccess();
    } else {
      const replaced = await revealOne({ replacement: true });
      if (!replaced) return;
    }
  } catch (_) {
    if (state.account && state.account.id === currentAccountId) {
      showAccount(state.account, { restored: true, feedbackLocked: state.feedbackLocked });
      showRecovery(
        state.feedbackLocked ? "结果已记录，但换号未完成" : "反馈没有提交",
        state.feedbackLocked ? "不要重复反馈；点击重试只会继续获取下一组账号。" : "当前账号还在，点击重试即可继续。",
        state.feedbackLocked ? () => revealOne({ replacement: true }) : () => submitFeedback(result),
      );
    }
  } finally {
    setBusy(false);
  }
}

function showVerify(hint = "完成下方验证，账号只会在本次会话中显示。") {
  state.account = null;
  byId("intentPanel").classList.remove("hidden", "is-locked");
  updateIntentUI();
  clearSession();
  byId("verifyHint").textContent = hint;
  updateVerifyAction();
  byId("credentialState").textContent = "等待访问验证";
  byId("attemptCount").textContent = "本次第 1 组";
  byId("feedbackPanel").classList.add("hidden");
  byId("storeLink").classList.add("hidden");
  byId("emptyStoreLink").classList.add("hidden");
  setPhase("verify", "verifyView");
}

async function initializeTurnstile() {
  if (restoreSession()) return;
  try {
    state.config = await jsonRequest("/api/v2/config", { method: "GET", headers: {} });
    if (!state.config.turnstile_script_url || !state.config.turnstile_site_key) throw new Error("configuration_missing");
    showVerify();
    await loadScript(state.config.turnstile_script_url);
    if (!window.turnstile) throw new Error("turnstile_unavailable");
    state.widgetId = window.turnstile.render("#turnstileWidget", {
      sitekey: state.config.turnstile_site_key,
      action: state.config.turnstile_action,
      theme: "dark",
      size: "flexible",
      callback: (token) => {
        state.token = token;
        updateVerifyAction();
        if (state.intent) {
          updateVerifyAction();
          announce("验证已完成，可以获取账号。" );
        } else {
          byId("headerState").textContent = "验证已通过 · 请选择目标";
          byId("statusLight").classList.remove("is-ready");
          byId("intentPanel").classList.add("needs-attention");
          announce("验证已完成。请先选择上方的下载目标。" );
          window.setTimeout(() => byId("intentPanel").scrollIntoView({ behavior: "smooth", block: "center" }), 80);
        }
      },
      "expired-callback": () => {
        state.token = "";
        updateVerifyAction();
        byId("headerState").textContent = "验证已过期";
        byId("statusLight").classList.remove("is-ready");
        announce("验证已过期，请重新完成验证。" );
      },
      "error-callback": () => {
        state.token = "";
        updateVerifyAction();
        showRecovery("验证组件暂不可用", "请检查网络后刷新页面重试。", () => window.location.reload());
      },
    });
  } catch (_) {
    setPhase("error", "bootView");
    byId("credentialState").textContent = "验证组件未连接";
    showRecovery("验证组件加载失败", "请检查网络或内容拦截设置，然后重试。", () => window.location.reload());
  }
}

async function copyText(value) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.className = "clipboard-proxy";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("copy_failed");
}

function returnHome() {
  clearSession();
  window.location.assign(`${window.location.origin}/`);
}

function restartFlow() {
  clearSession();
  state.account = null;
  state.attempt = 1;
  state.copied = { username: false, password: false };
  state.usernameEntered = false;
  state.feedbackLocked = false;
  state.loginSucceeded = false;
  state.resultsVisible = false;
  state.token = "";
  window.location.reload();
}

byId("verifyButton").addEventListener("click", () => {
  if (state.busy) return;
  if (!state.intent) {
    byId("intentPanel").classList.add("needs-attention");
    byId("intentPanel").scrollIntoView({ behavior: "smooth", block: "center" });
    announce("请先选择下载目标。" );
    return;
  }
  if (!state.token) {
    byId("turnstileWidget").scrollIntoView({ behavior: "smooth", block: "center" });
    announce("请先完成人机验证。" );
    return;
  }
  verifyAndReveal();
});
byId("restartButton").addEventListener("click", restartFlow);
byId("returnHomeButton").addEventListener("click", returnHome);
document.querySelectorAll("[data-intent]").forEach((button) => {
  button.addEventListener("click", () => selectIntent(button.dataset.intent));
});
byId("showResultsButton").addEventListener("click", () => {
  if (state.account && state.copied.password) showResultChoices();
});
async function copyPasswordAndContinue(button) {
  try {
    await copyText(byId("password").textContent || "");
    state.copied.password = true;
    state.leftForAttempt = true;
    updateCopyUI();
    saveSession();
    const message = "密码复制成功，请返回 App Store 粘贴";
    const label = byId("accountEnteredLabel");
    const glyph = byId("accountEnteredButton").querySelector(".account-copy-glyph");
    const check = byId("accountEnteredButton").querySelector(".account-copy-check");
    label.textContent = "密码已复制，请返回 App Store 粘贴";
    glyph.classList.add("hidden");
    check.classList.remove("hidden");
    showCopyConfirmation(message, byId("accountEnteredButton"));
    window.setTimeout(() => {
      label.textContent = "已输入账号，一键复制密码";
      glyph.classList.remove("hidden");
      check.classList.add("hidden");
    }, 2600);
    window.setTimeout(() => button.scrollIntoView({ behavior: "smooth", block: "center" }), 80);
  } catch (_) {
    showRecovery("密码没有复制成功", "请点击密码右侧的复制按钮重试，当前账号不会消失。", null);
  }
}

byId("accountEnteredButton").addEventListener("click", () => {
  const button = document.querySelector('[data-copy="password"]');
  if (button && !state.copied.password) {
    state.usernameEntered = true;
    updateCopyUI();
    saveSession();
    copyPasswordAndContinue(button);
  }
});
byId("appStoreHomeLink").addEventListener("click", () => {
  if (!state.account || !state.copied.username || state.copied.password) return;
  state.leftForAttempt = true;
  saveSession();
  announce("正在打开 App Store Today 首页。若未正常打开，请返回并按手动步骤继续。" );
});
byId("targetAppLink").addEventListener("click", () => {
  state.leftForAttempt = true;
  saveSession();
  announce("正在打开应用页面。检查是否出现云朵下载图标。" );
});
byId("retryButton").addEventListener("click", () => {
  if (state.pendingAction && !state.busy) state.pendingAction();
});
byId("differentPageButton").addEventListener("click", () => {
  const button = byId("differentPageButton");
  const expanded = button.getAttribute("aria-expanded") === "true";
  button.setAttribute("aria-expanded", String(!expanded));
  byId("differentPageHelp").classList.toggle("hidden", expanded);
});

document.querySelectorAll("[data-login-result]").forEach((button) => {
  button.addEventListener("click", () => {
    if (button.dataset.loginResult !== "success" || state.busy) return;
    if (state.intent === "target_app") {
      showTargetAppCheck();
    } else {
      submitFeedback("login_success");
    }
  });
});

resultButtons().forEach((button) => {
  button.addEventListener("click", () => submitFeedback(button.dataset.result));
});

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    if (!state.account || state.busy || button.getAttribute("aria-disabled") === "true") return;
    const key = button.dataset.copy;
    const target = byId(key);
    try {
      await copyText(target.textContent || "");
      if (key === "password" && !state.copied.username) {
        showRecovery("请先复制 Apple ID", "先复制 Apple ID 并在 App Store 输入，再回来复制密码。", null);
        return;
      }
      const wasCopied = Boolean(state.copied[key]);
      state.copied[key] = true;
      state.leftForAttempt = key === "username";
      updateCopyUI();
      saveSession();
      const fieldName = key === "username" ? "Apple ID" : "密码";
      const confirmation = wasCopied ? `${fieldName}再次复制成功` : `${fieldName}复制成功`;
      showCopyConfirmation(confirmation, button);
      if (!wasCopied && key === "username") announce("Apple ID 已复制。现在打开 App Store，进入账户页并粘贴。" );
      if (!wasCopied && key === "password") announce("密码复制成功。返回 App Store 输入密码，登录后回来确认结果。" );
    } catch (_) {
      showRecovery("没有复制成功", "长按文字可手动选择复制，当前账号不会消失。", null);
    }
  });
});

window.addEventListener("pageshow", (event) => {
  if (event.persisted && state.account) announce("已返回，当前账号仍保留在页面中。" );
});

document.addEventListener("visibilitychange", () => {
  if (state.account && document.hidden) state.leftForAttempt = true;
  if (!document.hidden && state.account) {
    announce(state.copied.password ? "欢迎回来。现在确认能否登录。" : "欢迎回来。请继续完成当前步骤。" );
    if (state.leftForAttempt && state.copied.username && !state.copied.password) {
      announce("欢迎回来。点击“已输入账号，一键复制密码”即可继续。" );
      window.setTimeout(() => byId("accountEnteredButton").scrollIntoView({ behavior: "smooth", block: "center" }), 80);
    }
    if (state.leftForAttempt && state.copied.password && !state.resultsVisible) {
      showResultChoices({ returned: true });
      saveSession();
      window.setTimeout(() => byId("feedbackPanel").scrollIntoView({ behavior: "smooth", block: "nearest" }), 80);
    }
  }
});

initializeTurnstile();
