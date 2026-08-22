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
  preflightAcknowledged: false,
  securityAcknowledged: false,
  lightboxTrigger: null,
  pendingNoviceExitResult: "",
  signOutGuideOpened: false,
  toastTimer: null,
  mode: "novice", // 默认新手引导
  intent: "",
  verified: false,
  resultsVisible: false,
};

const byId = (id) => document.getElementById(id);
const views = ["bootView", "verifyView", "accountView", "successView", "emptyView"];
const resultButtons = () => document.querySelectorAll("[data-result]");
const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

function replayMotion(element, className = "motion-enter") {
  if (!element || motionQuery.matches) return;
  element.classList.remove(className);
  void element.offsetWidth;
  element.classList.add(className);
  window.setTimeout(() => element.classList.remove(className), 620);
}

function replayTextMotion(container) {
  if (!container || motionQuery.matches) return;
  container.classList.remove("motion-text-enter");
  void container.offsetWidth;
  container.classList.add("motion-text-enter");
  window.setTimeout(() => container.classList.remove("motion-text-enter"), 560);
}

function replayStepMotion(element) {
  replayMotion(element, "motion-step-complete");
}

function replayErrorMotion(element) {
  replayMotion(element, "motion-error");
}

function syncDetailsMotion(details) {
  if (!details) return;
  details.dataset.motionOpen = String(details.open);
}

function setupDetailsMotion() {
  document.querySelectorAll("details").forEach((details) => {
    syncDetailsMotion(details);
    details.addEventListener("toggle", () => syncDetailsMotion(details));
  });
}

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
  }, 4200);
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
      preflightAcknowledged: state.preflightAcknowledged,
      securityAcknowledged: state.securityAcknowledged,
      pendingNoviceExitResult: state.pendingNoviceExitResult,
      signOutGuideOpened: state.signOutGuideOpened,
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
    state.preflightAcknowledged = Boolean(payload.preflightAcknowledged);
    state.securityAcknowledged = Boolean(payload.securityAcknowledged);
    state.pendingNoviceExitResult = ["shadowrocket_available", "shadowrocket_missing", "login_success"].includes(payload.pendingNoviceExitResult) ? payload.pendingNoviceExitResult : "";
    state.signOutGuideOpened = Boolean(payload.signOutGuideOpened);
    state.feedbackLocked = Boolean(payload.feedbackLocked);
    state.intent = payload.intent === "other_app" ? "other_app" : (payload.intent === "expert" ? "expert" : "target_app");
    state.mode = state.intent === "expert" ? "expert" : "novice";
    state.loginSucceeded = Boolean(payload.loginSucceeded);
    state.resultsVisible = Boolean(payload.resultsVisible);
    updateIntentUI();
    showAccount(state.account, { restored: true, feedbackLocked: state.feedbackLocked, resultsVisible: state.resultsVisible });
    if (state.pendingNoviceExitResult && state.mode === "novice") {
      const pendingResult = state.pendingNoviceExitResult;
      showNoviceExitGate(pendingResult, { restored: true });
    } else if (state.resultsVisible) {
      showResultChoices();
    }
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
  const previousView = views.find((id) => !byId(id).classList.contains("hidden"));
  document.documentElement.dataset.phase = phase;
  document.body.dataset.phase = phase;
  byId("relayStage").dataset.phase = phase;
  views.forEach((id) => byId(id).classList.toggle("hidden", id !== viewId));
  const activeView = byId(viewId);
  if (previousView !== viewId) {
    window.requestAnimationFrame(() => {
      replayMotion(activeView, "motion-phase-enter");
      replayTextMotion(activeView);
    });
  }
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
  const isExpert = state.mode === "expert";
  let reason = "";
  let buttonLabel = "获取账号";

  if (!isExpert && !state.intent) {
    reason = "请先选择上方的下载目标；选择后才会显示人机验证。";
    buttonLabel = "先选择下载目标";
  } else if (!state.token) {
    reason = isExpert ? "请完成上方的人机验证。" : "目标已选择，请完成上方的人机验证。";
    buttonLabel = "完成验证后获取";
  }

  const blocked = Boolean(reason) || state.busy;
  button.classList.toggle("is-blocked", blocked);
  button.setAttribute("aria-disabled", String(blocked));
  label.textContent = state.busy ? "正在获取账号" : (isExpert && !blocked ? "获取账号（极速）" : buttonLabel);
  hint.textContent = state.busy ? "正在为你分配账号，请稍候。" : reason;
  hint.classList.toggle("hidden", !state.busy && !reason);
  byId("turnstileWidget").classList.toggle("hidden", (!isExpert && !state.intent) || Boolean(state.account));

  if (!onVerifyView) return;
  if (state.busy) {
    byId("credentialState").textContent = "正在分配账号";
    byId("verifyTitle").textContent = "正在获取账号";
    byId("verifyHint").textContent = "请保持页面打开，很快就好。";
    return;
  }
  if (state.token && (isExpert || state.intent)) {
    byId("credentialState").textContent = "验证已通过";
    byId("verifyTitle").textContent = isExpert ? "老玩家极速通道" : "可以获取账号";
    byId("verifyHint").textContent = isExpert ? "验证已完成，点击下方按钮直接获取账号。" : "目标与验证都已完成，点击下方按钮获取账号。";
    byId("headerState").textContent = "验证已通过";
    byId("statusLight").classList.add("is-ready");
  } else if (isExpert || state.intent) {
    byId("credentialState").textContent = "等待访问验证";
    byId("verifyTitle").textContent = isExpert ? "老玩家极速通道" : "完成访问验证";
    byId("verifyHint").textContent = "验证完成后即可直接获取账号。";
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
  replayErrorMotion(byId("recoveryPanel"));
  state.pendingAction = action;
  if (!state.account) {
    document.documentElement.dataset.phase = "error";
    document.body.dataset.phase = "error";
  }
}

function updateIntentUI() {
  const isExpert = state.mode === "expert";
  document.body.dataset.mode = state.mode;
  document.querySelectorAll("[data-mode]").forEach((btn) => {
    const active = btn.dataset.mode === state.mode;
    btn.classList.toggle("is-selected", active);
    btn.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".page-flow-progress").forEach((el) => {
    el.classList.toggle("hidden", isExpert);
  });
  byId("intentPanel").classList.toggle("hidden", isExpert || Boolean(state.account));
  document.querySelectorAll("[data-intent]").forEach((button) => {
    const selected = !isExpert && button.dataset.intent === state.intent;
    button.setAttribute("aria-pressed", String(selected));
    button.classList.toggle("is-selected", selected);
  });
  byId("intentPanel").classList.toggle("is-locked", Boolean(state.account));
  document.querySelectorAll("[data-intent], [data-mode]").forEach((button) => { button.disabled = Boolean(state.account); });
  updateVerifyAction();
}

function selectMode(mode) {
  if (state.account || state.busy) return;
  state.mode = mode === "expert" ? "expert" : "novice";
  state.intent = state.mode === "expert" ? "expert" : "";
  try { localStorage.setItem("autoshare_mode", state.mode); } catch (_) {}
  updateIntentUI();
  replayMotion(document.querySelector(`[data-mode="${state.mode}"]`), "motion-select");
  replayMotion(byId("intentPanel"), "motion-panel-enter");
  updateVerifyAction();
  if (state.token && state.mode === "expert") {
    byId("verifyButton").focus({ preventScroll: true });
  }
}

function selectIntent(intent) {
  if (state.account || state.busy) return;
  state.intent = intent === "other_app" ? "other_app" : "target_app";
  byId("intentPanel").classList.remove("needs-attention");
  updateIntentUI();
  replayMotion(document.querySelector(`[data-intent="${state.intent}"]`), "motion-select");
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
  byId("credential").classList.remove("is-result-mode");
  byId("accountView").classList.remove("is-summary");
  byId("attemptCount").classList.remove("hidden");
  byId("resultCredentialHeading").classList.add("hidden");
  const panel = byId("feedbackPanel");
  panel.classList.add("is-ready", "is-results");
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
  byId("appStoreInstruction").classList.add("hidden");
  byId("securityGuide").classList.add("hidden");
  byId("showResultsButton").classList.add("hidden");
  byId("targetAppCheck").classList.add("hidden");
  byId("resultActions").classList.remove("hidden");
  replayMotion(panel, "motion-panel-enter");
  replayTextMotion(panel);
  replayStepMotion(byId("resultStep"));
  document.querySelectorAll("[data-login-result], [data-result]").forEach((button) => {
    button.disabled = state.busy || state.feedbackLocked;
  });
  saveSession();
  if (returned) window.setTimeout(() => byId("feedbackTitle").focus({ preventScroll: true }), 80);
}

function showTargetAppCheck() {
  hideCopyConfirmation();
  state.loginSucceeded = true;
  state.resultsVisible = true;
  byId("feedbackPanel").classList.add("is-ready", "is-results");
  byId("intentPanel").classList.add("hidden");
  byId("credential").classList.remove("is-result-mode");
  byId("accountView").classList.remove("is-summary");
  byId("attemptCount").classList.remove("hidden");
  byId("resultCredentialHeading").classList.add("hidden");
  byId("feedbackStep").textContent = "最后一步";
  byId("feedbackTitle").textContent = "检查下载按钮";
  byId("copyProgress").textContent = "打开应用页面；看到云朵下载图标表示目标已达成。";
  byId("resultActions").classList.add("hidden");
  byId("appStoreInstruction").classList.add("hidden");
  byId("securityGuide").classList.add("hidden");
  byId("showResultsButton").classList.add("hidden");
  byId("targetAppCheck").classList.remove("hidden");
  byId("resultStep").classList.add("is-current");
  replayMotion(byId("targetAppCheck"), "motion-panel-enter");
  replayTextMotion(byId("feedbackPanel"));
  replayStepMotion(byId("resultStep"));
  updateCopyUI();
  saveSession();
  announce("登录成功。现在检查是否可以下载目标应用。" );
}

function updateCopyUI() {
  const isExpert = state.mode === "expert";
  const usernameCopied = Boolean(state.copied.username);
  const usernameEntered = Boolean(state.usernameEntered);
  const passwordCopied = Boolean(state.copied.password);
  const copiedCount = Number(usernameCopied) + Number(passwordCopied);

  document.querySelectorAll("[data-copy]").forEach((button) => {
    const key = button.dataset.copy;
    const copied = Boolean(state.copied[key]);
    button.classList.toggle("is-copied", copied);
    const label = button.querySelector(".copy-label");
    const credentialsComplete = passwordCopied;
    const confirmedStep = !isExpert && copied && !credentialsComplete;
    button.classList.toggle("is-copy-confirmed", confirmedStep);
    const copyLabel = isExpert
      ? (copied ? "可再次复制" : "复制")
      : (credentialsComplete ? "可再次复制" : (copied ? "已复制" : "复制"));
    label.textContent = copyLabel;
    const fieldName = key === "username" ? " Apple ID" : "密码";
    button.setAttribute("aria-label", copyLabel === "已复制" ? `${key === "username" ? "Apple ID" : "密码"}已复制` : `${copyLabel}${fieldName}`);
  });

  const panel = byId("feedbackPanel");
  const title = byId("feedbackTitle");
  const progress = byId("copyProgress");
  const step = byId("feedbackStep");
  panel.classList.toggle("is-ready", isExpert || usernameCopied);
  byId("loginSuccessHint").textContent = isExpert ? "完成并结束" : (state.intent === "target_app" ? "继续确认下载结果" : "完成并结束");
  byId("targetAppCheck").classList.toggle("hidden", !state.loginSucceeded);

  byId("accountStep").classList.toggle("is-current", !isExpert && !usernameEntered);
  byId("accountStep").classList.toggle("is-complete", isExpert || usernameEntered);
  byId("accountStep").querySelector("span").textContent = (isExpert || usernameEntered) ? "✓" : "1";
  byId("passwordStep").classList.toggle("is-current", !isExpert && usernameEntered && !passwordCopied);
  byId("passwordStep").classList.toggle("is-complete", isExpert || passwordCopied);
  byId("passwordStep").querySelector("span").textContent = (isExpert || passwordCopied) ? "✓" : "2";
  byId("resultStep").classList.toggle("is-current", isExpert || passwordCopied);

  const usernameButton = document.querySelector('[data-copy="username"]');
  const passwordButton = document.querySelector('[data-copy="password"]');
  usernameButton.classList.toggle("is-primary-copy", !usernameCopied);
  passwordButton.classList.toggle("is-primary-copy", (isExpert && !passwordCopied) || (usernameCopied && !passwordCopied));

  if (isExpert) {
    byId("appStoreInstruction").classList.add("hidden");
    byId("securityGuide").classList.add("hidden");
    byId("showResultsButton").classList.add("hidden");
    byId("feedbackPanel").classList.toggle("is-ready", passwordCopied);
    byId("resultActions").classList.toggle("hidden", !passwordCopied || state.loginSucceeded);
    if (!passwordCopied) {
      step.textContent = "极速通道";
      title.textContent = "复制账号与密码";
      progress.textContent = "复制完成后去 App Store 登录，登录后再回来确认结果。";
    } else {
      step.textContent = "极速通道";
      title.textContent = "登录结果确认";
      progress.textContent = "登录成功直接结束；登录不上立即换号。";
    }
    document.querySelectorAll("[data-login-result], [data-result]").forEach((button) => {
      button.disabled = state.busy || state.feedbackLocked || !passwordCopied;
    });
    return;
  }

  byId("appStoreInstruction").classList.toggle("hidden", !usernameCopied || passwordCopied || state.resultsVisible);
  byId("accountEnteredButton").classList.toggle("hidden", usernameEntered);
  const preflightCheck = byId("accountPreflightCheck");
  if (preflightCheck) preflightCheck.checked = state.preflightAcknowledged;
  byId("appStoreHomeLink").classList.toggle("is-gated", !state.preflightAcknowledged);
  byId("securityGuide").classList.toggle("hidden", isExpert || passwordCopied || state.resultsVisible || state.loginSucceeded || !usernameCopied);
  const securityCheck = byId("securityGuideCheck");
  if (securityCheck) securityCheck.checked = state.securityAcknowledged;
  byId("accountEnteredButton").classList.toggle("is-gated", !state.securityAcknowledged && !passwordCopied);
  const passwordGateButton = document.querySelector('[data-copy="password"]');
  if (passwordGateButton) passwordGateButton.classList.toggle("is-security-gated", !isExpert && !passwordCopied && !state.securityAcknowledged);
  byId("showResultsButton").classList.toggle("hidden", !passwordCopied || state.resultsVisible);
  byId("resultActions").classList.toggle("hidden", !state.resultsVisible || state.loginSucceeded);
  if (state.resultsVisible) {
    document.querySelectorAll("[data-login-result], [data-result]").forEach((button) => {
      button.disabled = state.busy || state.feedbackLocked || !passwordCopied;
    });
    return;
  }
  document.querySelectorAll("[data-login-result], [data-result]").forEach((button) => {
    button.disabled = state.busy || state.feedbackLocked || !passwordCopied;
  });

  if (copiedCount === 0) {
    step.textContent = "当前任务";
    title.textContent = "复制 Apple ID";
    progress.textContent = "复制后，打开 App Store 并进入账户登录页。";
  } else if (!usernameEntered) {
    step.textContent = "第 1 步 · 共 2 步";
    title.textContent = "在 App Store 中登录账号";
    progress.textContent = "账号已复制到剪贴板。";
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
  replayMotion(byId("credential"), "motion-credential-ready");
  document.querySelectorAll(".credential-field").forEach((field, index) => {
    field.style.setProperty("--motion-index", String(index));
    replayMotion(field, "motion-field-enter");
  });
  updateCopyUI();
  setStoreLink(state.purchaseLink);
  saveSession();
  hideRecovery();
  runScanner();
  announce(options.restored ? "已恢复你刚才使用的账号，可以继续复制和反馈。" : "账号已准备好。请复制账号和密码，只在 App Store 登录。" );
}

function showSuccess() {
  hideCopyConfirmation();
  byId("noviceExitPanel").classList.add("hidden");
  setPhase("success", "successView");
  byId("resultStep").classList.add("is-complete");
  byId("resultStep").classList.remove("is-current");
  byId("resultStep").querySelector("span").textContent = "✓";
  replayStepMotion(byId("resultStep"));
  replayMotion(byId("successView"), "motion-success-enter");
  replayTextMotion(byId("successView"));
  byId("intentPanel").classList.add("hidden");
  byId("credentialState").textContent = "反馈已记录";
  byId("feedbackPanel").classList.add("hidden");
  byId("storeLink").classList.add("hidden");
  byId("archiveEdge").classList.add("hidden");
  state.account = null;
  state.copied = { username: false, password: false };
  state.usernameEntered = false;
  state.preflightAcknowledged = false;
  state.securityAcknowledged = false;
  state.pendingNoviceExitResult = "";
  state.signOutGuideOpened = false;
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
  state.preflightAcknowledged = false;
  state.securityAcknowledged = false;
  state.pendingNoviceExitResult = "";
  state.signOutGuideOpened = false;
  state.loginSucceeded = false;
  state.resultsVisible = false;
  clearSession();
  byId("feedbackPanel").classList.add("hidden");
  byId("credentialState").textContent = "没有更多共享凭证";
  byId("attemptCount").textContent = `已尝试 ${state.attempt} 组`;
  setPhase("empty", "emptyView");
  replayMotion(byId("emptyView"), "motion-empty-enter");
  replayTextMotion(byId("emptyView"));
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
      byId("noviceExitPanel").classList.add("hidden");
      state.attempt += 1;
      state.copied = { username: false, password: false };
      state.usernameEntered = false;
      state.preflightAcknowledged = false;
      state.securityAcknowledged = false;
      state.pendingNoviceExitResult = "";
      state.signOutGuideOpened = false;
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

function showNoviceExitGate(result, options = {}) {
  hideCopyConfirmation();
  const restored = Boolean(options.restored);
  const guideWasOpened = restored && state.signOutGuideOpened;
  state.pendingNoviceExitResult = result;
  state.signOutGuideOpened = guideWasOpened;
  byId("signOutGuideLink").classList.remove("needs-confirmation");
  byId("signOutCheck").checked = false;
  byId("finishAfterSignOutButton").disabled = true;
  byId("replaceAfterSignOutButton").disabled = true;
  byId("signOutError").classList.add("hidden");
  const isReplacement = result === "shadowrocket_missing";
  byId("noviceExitPanel").classList.toggle("is-replacement", isReplacement);
  byId("signoutPurposeLabel").textContent = isReplacement ? "尝试下一组前" : "关闭页面前";
  byId("signoutPurposeTitle").textContent = isReplacement ? "先退出当前共享账号" : "还需要完成最后的收尾";
  byId("signoutPurposeCopy").textContent = isReplacement
    ? "退出后再登录下一组账号，避免两个共享账号在 App Store 中混用。"
    : "退出当前共享账号后，你就可以重新登录自己的 App Store 账号。";
  byId("downloadWindowNote").classList.toggle("hidden", isReplacement);
  byId("finishAfterSignOutButton").classList.toggle("hidden", isReplacement);
  byId("replaceAfterSignOutButton").classList.toggle("hidden", !isReplacement);
  byId("targetAppCheck").classList.add("hidden");
  byId("resultActions").classList.add("hidden");
  byId("showResultsButton").classList.add("hidden");
  byId("noviceExitPanel").classList.remove("hidden");
  replayMotion(byId("noviceExitPanel"), "motion-panel-enter");
  replayTextMotion(byId("noviceExitPanel"));
  byId("feedbackStep").textContent = isReplacement ? "换号前" : "退出账号前";
  byId("feedbackTitle").textContent = isReplacement ? "先退出当前 App Store 账号" : "你还有些必要且值得做的事情";
  byId("copyProgress").textContent = isReplacement
    ? "不会换？点击下方自助更换"
    : "点击下方应用直接下载吧";
  byId("feedbackPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  announce(isReplacement ? "请先退出当前 App Store 账号，再尝试下一组。" : "请先下载所需应用，并在完成前退出共享账号。" );
  saveSession();
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
  try {
    const savedMode = localStorage.getItem("autoshare_mode");
    if (savedMode === "expert" || savedMode === "novice") {
      state.mode = savedMode;
      state.intent = state.mode === "expert" ? "expert" : "";
    }
  } catch (_) {}
  const restored = restoreSession();
  if (restored) return;
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

function playVerifyGooey() {
  const button = byId("verifyButton");
  const host = button.querySelector(".gooey-action-particles");
  if (!host || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  host.replaceChildren();
  button.classList.remove("is-gooey-active");
  const colors = ["#ffffff", "#ffffff", "#e5e7eb", "#f3f4f6"];
  const count = 15;
  for (let i = 0; i < count; i += 1) {
    const angle = ((Math.PI * 2) / count) * i + (Math.random() - .5) * .14;
    const startDistance = 22 + Math.random() * 14;
    const endDistance = 5 + Math.random() * 8;
    const particle = document.createElement("span");
    const point = document.createElement("span");
    particle.className = "gooey-particle";
    point.className = "gooey-point";
    particle.style.setProperty("--start-x", `${Math.cos(angle) * startDistance}px`);
    particle.style.setProperty("--start-y", `${Math.sin(angle) * startDistance}px`);
    particle.style.setProperty("--end-x", `${Math.cos(angle) * endDistance}px`);
    particle.style.setProperty("--end-y", `${Math.sin(angle) * endDistance}px`);
    particle.style.setProperty("--time", `${650 + Math.round(Math.random() * 260)}ms`);
    particle.style.setProperty("--scale", `${.75 + Math.random() * .42}`);
    particle.style.setProperty("--rotate", `${(Math.random() - .5) * 190}deg`);
    point.style.setProperty("--color", colors[Math.floor(Math.random() * colors.length)]);
    particle.appendChild(point);
    host.appendChild(particle);
  }
  void button.offsetWidth;
  button.classList.add("is-gooey-active");
  window.setTimeout(() => {
    button.classList.remove("is-gooey-active");
    host.replaceChildren();
  }, 1100);
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
  playVerifyGooey();
  window.setTimeout(() => verifyAndReveal(), 140);
});
byId("restartButton").addEventListener("click", restartFlow);
byId("returnHomeButton").addEventListener("click", returnHome);
document.querySelectorAll("[data-mode]").forEach((btn) => {
  btn.addEventListener("click", () => selectMode(btn.dataset.mode));
});
document.querySelectorAll("[data-intent]").forEach((button) => {
  button.addEventListener("click", () => selectIntent(button.dataset.intent));
});
function closeGuideLightbox() {
  const lightbox = byId("guideLightbox");
  if (lightbox.classList.contains("hidden")) return;
  lightbox.classList.add("hidden");
  document.body.classList.remove("is-lightbox-open");
  const trigger = state.lightboxTrigger;
  state.lightboxTrigger = null;
  if (trigger && document.contains(trigger)) trigger.focus({ preventScroll: true });
}

function openGuideLightbox(trigger) {
  const image = byId("guideLightboxImage");
  const caption = byId("guideLightboxCaption");
  image.src = trigger.dataset.guideImage || "";
  image.alt = trigger.querySelector("img")?.alt || "教程示例大图";
  caption.textContent = trigger.dataset.guideCaption || "教程示例";
  state.lightboxTrigger = trigger;
  byId("guideLightbox").classList.remove("hidden");
  document.body.classList.add("is-lightbox-open");
  byId("guideLightboxClose").focus({ preventScroll: true });
}

document.querySelectorAll("[data-guide-image]").forEach((button) => {
  button.addEventListener("click", () => openGuideLightbox(button));
});
byId("guideLightboxClose").addEventListener("click", closeGuideLightbox);
byId("guideLightbox").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) closeGuideLightbox();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !byId("guideLightbox").classList.contains("hidden")) closeGuideLightbox();
});

byId("showResultsButton").addEventListener("click", () => {
  if (state.account && state.copied.password) showResultChoices();
});
function requireSecurityAcknowledgement() {
  if (state.mode === "expert" || state.copied.password || state.securityAcknowledged) return true;
  const guide = byId("securityGuide");
  guide.classList.remove("hidden");
  guide.open = true;
  guide.classList.add("needs-confirmation");
  byId("securityGuideError").classList.remove("hidden");
  byId("securityGuideCheck").focus({ preventScroll: true });
  byId("securityGuideCheck").scrollIntoView({ behavior: "smooth", block: "center" });
  announce("请先阅读 Apple ID 安全提示，并勾选确认后再复制密码。" );
  return false;
}

byId("securityGuideCheck").addEventListener("change", (event) => {
  state.securityAcknowledged = Boolean(event.currentTarget.checked);
  byId("securityGuideError").classList.add("hidden");
  byId("securityGuide").classList.remove("needs-confirmation");
  updateCopyUI();
  saveSession();
  announce(state.securityAcknowledged ? "已确认 Apple ID 安全提示的正确操作。" : "第一次复制密码前需要阅读并勾选确认。" );
});

async function copyPasswordAndContinue(button) {
  if (!requireSecurityAcknowledgement()) return false;
  try {
    await copyText(byId("password").textContent || "");
    state.copied.password = true;
    state.leftForAttempt = true;
    updateCopyUI();
    replayMotion(button, "motion-copy-done");
    replayStepMotion(byId("passwordStep"));
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
    if (!requireSecurityAcknowledgement()) return;
    state.usernameEntered = true;
    updateCopyUI();
    saveSession();
    copyPasswordAndContinue(button);
  }
});
byId("accountPreflightCheck").addEventListener("change", (event) => {
  state.preflightAcknowledged = Boolean(event.currentTarget.checked);
  byId("accountPreflightError").classList.add("hidden");
  byId("accountPreflight").classList.remove("needs-confirmation");
  byId("appStoreHomeLink").classList.toggle("is-gated", !state.preflightAcknowledged);
  saveSession();
  announce(state.preflightAcknowledged ? "已确认 App Store 账户提示的正确操作。" : "打开 App Store 前需要查看示例并勾选确认。" );
});
byId("appStoreHomeLink").addEventListener("click", (event) => {
  if (!state.account || !state.copied.username || state.copied.password) {
    event.preventDefault();
    return;
  }
  if (!state.preflightAcknowledged) {
    event.preventDefault();
    const example = byId("accountPreflightExample");
    example.open = true;
    byId("accountPreflight").classList.add("needs-confirmation");
    byId("accountPreflightError").classList.remove("hidden");
    byId("accountPreflightCheck").focus({ preventScroll: true });
    byId("accountPreflightCheck").scrollIntoView({ behavior: "smooth", block: "center" });
    announce("请先查看第二项示例，并勾选确认。" );
    return;
  }
  state.leftForAttempt = true;
  saveSession();
  announce("正在打开 App Store Today 首页。若未正常打开，请返回并按手动步骤继续。" );
});
byId("needAccountButton").addEventListener("click", () => {
  if (!state.purchaseLink) {
    announce("专属账号入口暂不可用。" );
    return;
  }
  window.open(state.purchaseLink, "_blank", "noopener,noreferrer");
  announce("正在打开专属账号店铺。" );
});

byId("signOutGuideLink").addEventListener("click", () => {
  state.signOutGuideOpened = true;
  byId("signOutError").classList.add("hidden");
  announce("退出教程已打开。完成后返回并勾选确认。" );
});

byId("signOutCheck").addEventListener("change", (event) => {
  const checked = Boolean(event.currentTarget.checked);
  byId("signOutError").classList.add("hidden");
  byId("finishAfterSignOutButton").disabled = !checked;
  byId("replaceAfterSignOutButton").disabled = !checked;
});

async function completeNoviceExit(expectedReplacement) {
  const result = state.pendingNoviceExitResult;
  const isReplacement = result === "shadowrocket_missing";
  if (!result || isReplacement !== expectedReplacement) return;
  if (!state.signOutGuideOpened || !byId("signOutCheck").checked) {
    byId("signOutError").classList.remove("hidden");
    byId("signOutGuideLink").classList.add("needs-confirmation");
    byId("signOutCheck").focus({ preventScroll: true });
    byId("signOutCheck").scrollIntoView({ behavior: "smooth", block: "center" });
    announce("请先打开退出教程，并确认已经退出当前 App Store 账号。" );
    return;
  }
  byId("signOutGuideLink").classList.remove("needs-confirmation");
  await submitFeedback(result);
  state.pendingNoviceExitResult = "";
  state.signOutGuideOpened = false;
}

byId("finishAfterSignOutButton").addEventListener("click", () => completeNoviceExit(false));
byId("replaceAfterSignOutButton").addEventListener("click", () => completeNoviceExit(true));

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
  const panel = byId("differentPageHelp");
  const expanded = button.getAttribute("aria-expanded") === "true";
  button.setAttribute("aria-expanded", String(!expanded));
  panel.classList.toggle("hidden", expanded);
  if (!expanded) replayMotion(panel, "motion-disclosure-enter");
});

document.querySelectorAll("[data-login-result]").forEach((button) => {
  button.addEventListener("click", async () => {
    if (button.dataset.loginResult !== "success" || state.busy || state.feedbackLocked) return;
    if (state.mode === "expert") {
      await submitFeedback("login_success");
      return;
    }
    if (state.intent === "target_app") {
      showTargetAppCheck();
    } else {
      showNoviceExitGate("login_success");
    }
  });
});

resultButtons().forEach((button) => {
  button.addEventListener("click", () => {
    const result = button.dataset.result;
    if (state.mode === "novice" && (result === "shadowrocket_available" || result === "shadowrocket_missing")) {
      showNoviceExitGate(result);
      return;
    }
    submitFeedback(result);
  });
});

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    if (!state.account || state.busy || button.getAttribute("aria-disabled") === "true") return;
    const key = button.dataset.copy;
    const target = byId(key);
    try {
      if (key === "password" && !state.copied.username && state.intent !== "expert") {
        showRecovery("请先复制 Apple ID", "先复制 Apple ID 并在 App Store 输入，再回来复制密码。", null);
        announce("请先复制 Apple ID，再复制密码。当前账号不会消失。" );
        return;
      }
      if (key === "password" && !requireSecurityAcknowledgement()) return;
      await copyText(target.textContent || "");
      const wasCopied = Boolean(state.copied[key]);
      state.copied[key] = true;
      state.leftForAttempt = key === "username";
      hideRecovery();
      if (state.resultsVisible) {
        const fieldName = key === "username" ? "Apple ID" : "密码";
        saveSession();
        showCopyConfirmation(`${fieldName}再次复制成功`, button);
        return;
      }
      updateCopyUI();
      replayMotion(button, "motion-copy-done");
      if (!wasCopied) replayStepMotion(key === "username" ? byId("accountStep") : byId("passwordStep"));
      saveSession();
      const fieldName = key === "username" ? "Apple ID" : "密码";
      const confirmation = wasCopied ? `${fieldName}再次复制成功` : `${fieldName}复制成功`;
      showCopyConfirmation(confirmation, button);
      if (!wasCopied && key === "username" && state.mode === "novice") {
        announce("Apple ID 已复制。现在打开 App Store，进入账户页并粘贴。" );
        window.setTimeout(() => byId("feedbackPanel").scrollIntoView({ behavior: "smooth", block: "start" }), 120);
      }
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

setupDetailsMotion();
initializeTurnstile();
