"use strict";

(() => {
  const STORAGE_KEY = "relay_sound_enabled";
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  let context = null;
  let master = null;
  let enabled = true;
  let activeVoices = 0;

  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "0") enabled = false;
  } catch (_) {
    // Sound remains enabled for this page when storage is unavailable.
  }

  function syncToggle() {
    const toggle = document.getElementById("soundToggle");
    if (!toggle) return;
    const available = Boolean(AudioContextCtor) && !reducedMotionQuery.matches;
    toggle.disabled = !available;
    toggle.hidden = !available;
    toggle.setAttribute("aria-pressed", String(enabled));
    toggle.setAttribute("aria-label", enabled ? "关闭提示音" : "开启提示音");
    toggle.classList.toggle("is-off", !enabled);
    const label = toggle.querySelector("span");
    if (label) label.textContent = enabled ? "提示音" : "静音";
    const icon = toggle.querySelector("svg");
    if (icon) icon.dataset.state = enabled ? "on" : "off";
  }

  function ensureContext() {
    if (!AudioContextCtor) return null;
    if (!context) {
      context = new AudioContextCtor();
      master = context.createGain();
      master.gain.value = 0.055;
      master.connect(context.destination);
    }
    if (context.state === "suspended") context.resume().catch(() => {});
    return context;
  }

  function unlock() {
    if (!enabled || reducedMotionQuery.matches) return;
    const ctx = ensureContext();
    if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});
  }

  function markVoicesSettled(delay) {
    window.setTimeout(() => { activeVoices = 0; }, Math.ceil(delay * 1000) + 80);
  }

  function tone({ frequency, endFrequency = frequency, start, duration, type = "sine", gain = 0.35 }) {
    const ctx = ensureContext();
    if (!ctx || !master || activeVoices >= 8) return;
    activeVoices += 1;
    markVoicesSettled((start || 0) + duration);
    const now = ctx.currentTime + (start || 0);
    const oscillator = ctx.createOscillator();
    const envelope = ctx.createGain();
    oscillator.type = type;
    oscillator.frequency.setValueAtTime(frequency, now);
    oscillator.frequency.exponentialRampToValueAtTime(Math.max(20, endFrequency), now + duration * 0.78);
    envelope.gain.setValueAtTime(0.0001, now);
    envelope.gain.exponentialRampToValueAtTime(gain, now + Math.min(0.018, duration * 0.18));
    envelope.gain.exponentialRampToValueAtTime(0.0001, now + duration);
    oscillator.connect(envelope);
    envelope.connect(master);
    oscillator.start(now);
    oscillator.stop(now + duration + 0.025);
    oscillator.onended = () => { activeVoices = Math.max(0, activeVoices - 1); };
  }

  const patterns = {
    press: [{ frequency: 190, endFrequency: 155, duration: 0.075, type: "sine", gain: 0.22 }],
    mode: [
      { frequency: 235, endFrequency: 210, duration: 0.09, type: "triangle", gain: 0.28 },
      { frequency: 330, endFrequency: 300, start: 0.055, duration: 0.13, type: "sine", gain: 0.22 },
    ],
    select: [{ frequency: 420, endFrequency: 520, duration: 0.12, type: "sine", gain: 0.25 }],
    verify: [
      { frequency: 260, endFrequency: 280, duration: 0.11, type: "sine", gain: 0.2 },
      { frequency: 390, endFrequency: 420, start: 0.09, duration: 0.13, type: "sine", gain: 0.22 },
      { frequency: 560, endFrequency: 620, start: 0.19, duration: 0.18, type: "triangle", gain: 0.2 },
    ],
    copy: [
      { frequency: 620, endFrequency: 650, duration: 0.075, type: "sine", gain: 0.22 },
      { frequency: 840, endFrequency: 900, start: 0.065, duration: 0.12, type: "sine", gain: 0.2 },
    ],
    check: [{ frequency: 540, endFrequency: 700, duration: 0.13, type: "sine", gain: 0.22 }],
    open: [{ frequency: 440, endFrequency: 620, duration: 0.16, type: "triangle", gain: 0.2 }],
    error: [
      { frequency: 280, endFrequency: 245, duration: 0.11, type: "sine", gain: 0.22 },
      { frequency: 190, endFrequency: 165, start: 0.09, duration: 0.15, type: "triangle", gain: 0.2 },
    ],
    result: [{ frequency: 390, endFrequency: 470, duration: 0.14, type: "sine", gain: 0.2 }],
    success: [
      { frequency: 392, endFrequency: 410, duration: 0.1, type: "sine", gain: 0.18 },
      { frequency: 523, endFrequency: 550, start: 0.085, duration: 0.12, type: "sine", gain: 0.2 },
      { frequency: 659, endFrequency: 710, start: 0.18, duration: 0.18, type: "triangle", gain: 0.2 },
    ],
  };

  function play(name) {
    if (!enabled || reducedMotionQuery.matches || !patterns[name]) return;
    const ctx = ensureContext();
    if (!ctx || ctx.state !== "running") return;
    patterns[name].forEach(tone);
  }

  function handleSoundToggle() {
    enabled = !enabled;
    try { window.localStorage.setItem(STORAGE_KEY, enabled ? "1" : "0"); } catch (_) {}
    syncToggle();
    if (!enabled && context && context.state === "running") context.suspend().catch(() => {});
    if (enabled) play("press");
  }

  window.addEventListener("pointerdown", unlock, { capture: true, passive: true });
  window.addEventListener("keydown", unlock, { capture: true, passive: true });
  document.addEventListener("DOMContentLoaded", () => {
    syncToggle();
    const toggleButton = document.getElementById("soundToggle");
    if (toggleButton) toggleButton.addEventListener("click", handleSoundToggle);
  }, { once: true });

  reducedMotionQuery.addEventListener?.("change", syncToggle);
  window.RelaySound = { play, unlock, toggle: handleSoundToggle, isEnabled: () => enabled, activeVoices: () => activeVoices, contextState: () => context ? context.state : "uninitialized" };
})();
