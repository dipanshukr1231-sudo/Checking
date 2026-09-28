
import os
import json
import time
import hmac
import hashlib
import sqlite3
from threading import Thread
from urllib.parse import parse_qsl

from flask import Flask, request, jsonify, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "")
PORT = int(os.environ.get("PORT", "10000"))
DB_PATH = os.environ.get("DB_PATH", "device_verification.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")
if not WEB_APP_URL:
    raise RuntimeError("WEB_APP_URL is missing")

app = Flask(__name__)

HTML = r"""
    
"""<!DOCTYPE html>
<html lang="en" data-scheme="light" data-state="idle">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>Device Verification</title>

<!-- Telegram Mini Apps SDK (required). The page degrades gracefully if it fails to load. -->
<script src="https://telegram.org/js/telegram-web-app.js"></script>

<style>
/* ==========================================================================
   Design tokens
   Colours are stored as space-separated RGB triplets so we can derive every
   tint with rgb(var(--x) / alpha). Telegram theme values are injected by JS.
   ========================================================================== */
:root {
  --font: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --ease: cubic-bezier(.22, 1, .36, 1);
  --spring: cubic-bezier(.34, 1.56, .64, 1);

  /* Light defaults (used outside Telegram, or if a theme value is missing) */
  --bg-rgb: 238 241 246;
  --card-rgb: 255 255 255;
  --text-rgb: 17 24 39;
  --hint-rgb: 107 114 128;
  --accent-rgb: 47 128 237;
  --accent-text-rgb: 255 255 255;
  --success-rgb: 22 163 74;
  --danger-rgb: 220 38 38;
  --shadow-rgb: 15 23 42;
  --highlight: .75;

  /* Active tone follows the verification state */
  --tone-rgb: var(--accent-rgb);

  /* Safe areas: device notch/gesture bars + Telegram header/fullscreen insets */
  --safe-top: calc(max(env(safe-area-inset-top, 0px), var(--tg-safe-area-inset-top, 0px)) + var(--tg-content-safe-area-inset-top, 0px));
  --safe-right: max(env(safe-area-inset-right, 0px), var(--tg-safe-area-inset-right, 0px));
  --safe-bottom: max(env(safe-area-inset-bottom, 0px), var(--tg-safe-area-inset-bottom, 0px));
  --safe-left: max(env(safe-area-inset-left, 0px), var(--tg-safe-area-inset-left, 0px));
}

:root[data-scheme="dark"] {
  --bg-rgb: 14 22 33;
  --card-rgb: 23 33 43;
  --text-rgb: 245 247 250;
  --hint-rgb: 125 142 160;
  --accent-rgb: 63 142 245;
  --success-rgb: 52 211 153;
  --danger-rgb: 248 113 113;
  --shadow-rgb: 0 0 0;
  --highlight: .06;
}

:root[data-state="success"] { --tone-rgb: var(--success-rgb); }
:root[data-state="failure"] { --tone-rgb: var(--danger-rgb); }

/* ==========================================================================
   Base
   ========================================================================== */
*, *::before, *::after { box-sizing: border-box; }
[hidden] { display: none !important; }

html, body {
  margin: 0;
  min-height: 100%;
  overflow-x: hidden;
  background: rgb(var(--bg-rgb));
  color: rgb(var(--text-rgb));
  font-family: var(--font);
  -webkit-font-smoothing: antialiased;
  -webkit-text-size-adjust: 100%;
  -webkit-tap-highlight-color: transparent;
  touch-action: manipulation;
  overscroll-behavior: none;
}
h1, p, dl, dd, ol { margin: 0; padding: 0; }
ol { list-style: none; }

.sr-only {
  position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0;
  overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
}

/* ==========================================================================
   Layout
   ========================================================================== */
.app {
  position: relative;
  min-height: var(--tg-viewport-stable-height, 100vh);
  min-height: var(--tg-viewport-stable-height, 100dvh);
  display: flex;
  align-items: center;
  justify-content: center;
  padding:
    calc(16px + var(--safe-top))
    calc(16px + var(--safe-right))
    calc(16px + var(--safe-bottom))
    calc(16px + var(--safe-left));
  overflow-x: clip;
}

/* One soft, tone-coloured glow behind the card. It shifts colour with state. */
.ambient {
  position: fixed; inset: 0; overflow: hidden; pointer-events: none; z-index: 0;
}
.ambient::before {
  content: "";
  position: absolute; left: 50%; top: 24%;
  width: min(440px, 110vw); aspect-ratio: 1;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: rgb(var(--tone-rgb) / .17);
  filter: blur(80px);
  transition: background-color .9s ease;
}

/* ==========================================================================
   Card (glass / soft UI)
   ========================================================================== */
.card {
  position: relative; z-index: 1;
  width: 100%; max-width: 400px;
  padding: 28px 24px 22px;
  border-radius: 28px;
  background: rgb(var(--card-rgb) / .8);
  -webkit-backdrop-filter: blur(24px) saturate(1.5);
  backdrop-filter: blur(24px) saturate(1.5);
  border: 1px solid rgb(var(--text-rgb) / .07);
  box-shadow:
    inset 0 1px 0 rgb(255 255 255 / var(--highlight)),
    0 1px 2px rgb(var(--shadow-rgb) / .05),
    0 12px 28px -10px rgb(var(--shadow-rgb) / .14),
    0 36px 64px -28px rgb(var(--shadow-rgb) / .22);
  animation: card-in .8s var(--ease) both;
}
@keyframes card-in {
  from { opacity: 0; transform: translateY(14px) scale(.985); }
  to   { opacity: 1; transform: none; }
}

/* ==========================================================================
   Emblem: shield + progress ring
   ========================================================================== */
.stage { display: grid; place-items: center; }
.emblem { width: 132px; height: 132px; display: block; overflow: visible; }

.emblem .halo,
.emblem .ripple,
.emblem .shield-wrap { transform-box: fill-box; transform-origin: center; }

.halo { fill: rgb(var(--tone-rgb) / .08); transition: fill .6s ease; }
[data-state="scanning"] .halo { animation: breathe 2.6s ease-in-out infinite; }
@keyframes breathe {
  0%, 100% { transform: scale(.94); opacity: .65; }
  50%      { transform: scale(1.06); opacity: 1; }
}

.ring-track { fill: none; stroke: rgb(var(--text-rgb) / .08); stroke-width: 3; }
.ring {
  fill: none;
  stroke: rgb(var(--tone-rgb));
  stroke-width: 3;
  stroke-linecap: round;
  stroke-dasharray: 100 100;
  stroke-dashoffset: 100;
  opacity: 0;
  transition:
    stroke-dashoffset var(--ring-ms, 600ms) linear,
    opacity .4s ease,
    stroke .6s ease;
}
[data-state="scanning"] .ring,
[data-state="success"] .ring,
[data-state="failure"] .ring { opacity: 1; }

.ripple { fill: none; stroke: rgb(var(--tone-rgb)); stroke-width: 2; opacity: 0; }
[data-state="success"] .ripple { animation: ripple 1.1s .25s ease-out both; }
@keyframes ripple {
  from { opacity: .55; transform: scale(1); }
  to   { opacity: 0;   transform: scale(1.12); }
}

.shield-fill {
  fill: rgb(var(--tone-rgb) / .1);
  transition: fill .6s ease;
  animation: fade-in .9s .55s ease both;
}
.shield-line {
  fill: none;
  stroke: rgb(var(--tone-rgb));
  stroke-width: 2.6;
  stroke-linejoin: round;
  stroke-dasharray: 100;
  stroke-dashoffset: 0;
  transition: stroke .6s ease;
  animation: draw 1.1s .15s var(--ease) both;
}
@keyframes draw {
  0%   { stroke-dashoffset: 100; opacity: 0; }
  6%   { opacity: 1; }
  100% { stroke-dashoffset: 0; opacity: 1; }
}
@keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }

/* Scan beam, clipped to the shield */
.beam { opacity: 0; }
.beam-glow { fill: url(#beamGrad); }
.beam-edge { fill: rgb(var(--tone-rgb)); opacity: .85; }
[data-state="scanning"] .beam { animation: beam 2.1s cubic-bezier(.45, 0, .55, 1) infinite; }
@keyframes beam {
  0%   { transform: translateY(0);    opacity: 0; }
  14%  { opacity: 1; }
  86%  { opacity: 1; }
  100% { transform: translateY(74px); opacity: 0; }
}

/* Glyphs inside the shield */
.glyph {
  fill: none;
  stroke: rgb(var(--tone-rgb));
  stroke-linecap: round;
  stroke-linejoin: round;
  transform-box: fill-box;
  transform-origin: center;
  transition: opacity .3s ease, transform .5s var(--spring), stroke .6s ease;
}
.glyph-device { stroke-width: 2.4; opacity: 1; animation: fade-in .8s .9s ease both; }
.glyph-check, .glyph-cross {
  opacity: 0;
  stroke-dasharray: 100;
  stroke-dashoffset: 100;
  transform: scale(.85);
}
.glyph-check { stroke-width: 4.6; }
.glyph-cross { stroke-width: 4.4; }

[data-state="success"] .glyph-device,
[data-state="failure"] .glyph-device { opacity: 0; transform: scale(.7); animation: none; }

[data-state="success"] .glyph-check,
[data-state="failure"] .glyph-cross {
  opacity: 1;
  stroke-dashoffset: 0;
  transform: scale(1);
  transition:
    opacity 0s .2s,
    stroke-dashoffset .55s .25s var(--ease),
    transform .6s .25s var(--spring),
    stroke .6s ease;
}

[data-state="success"] .shield-wrap { animation: pop .7s .1s var(--spring) both; }
[data-state="failure"] .shield-wrap { animation: shake .55s .1s ease-in-out both; }
@keyframes pop {
  0% { transform: scale(1); } 45% { transform: scale(1.07); } 100% { transform: scale(1); }
}
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-6px); } 40% { transform: translateX(5px); }
  60% { transform: translateX(-3px); } 80% { transform: translateX(2px); }
}

/* ==========================================================================
   Content
   ========================================================================== */
.morph { display: flow-root; }

.title {
  margin-top: 4px;
  text-align: center;
  font-size: 25px; line-height: 1.16; font-weight: 600; letter-spacing: -.022em;
  text-wrap: balance;
}
.title:focus { outline: none; }

.subtitle {
  margin: 8px auto 0;
  max-width: 32ch;
  text-align: center;
  font-size: 15px; line-height: 1.5;
  color: rgb(var(--hint-rgb));
  text-wrap: balance;
}

.view { display: block; }

/* Steps timeline */
.steps {
  --row-h: 40px;
  --icon: 22px;
  width: 100%; max-width: 300px;
  margin: 26px auto 0;
}
.step {
  position: relative;
  display: flex; align-items: center; gap: 14px;
  height: var(--row-h);
}
.step:not(:last-child)::after {
  content: "";
  position: absolute;
  left: calc(var(--icon) / 2 - 1px);
  top: calc((var(--row-h) + var(--icon)) / 2);
  width: 2px; height: calc(var(--row-h) - var(--icon));
  border-radius: 2px;
  background: rgb(var(--text-rgb) / .1);
  transition: background-color .5s ease;
}
.step[data-status="done"]:not(:last-child)::after { background: rgb(var(--tone-rgb) / .45); }

.step__icon { position: relative; flex: none; width: var(--icon); height: var(--icon); }
.step__icon > * {
  position: absolute; inset: 0; margin: auto;
  opacity: 0; transform: scale(.4);
  transition: opacity .3s ease, transform .45s var(--spring);
}
.step__dot { width: 8px; height: 8px; border-radius: 50%; background: rgb(var(--text-rgb) / .22); opacity: 1; transform: scale(1); }
.step__spin { width: 18px; height: 18px; }
.step__spin i {
  display: block; width: 100%; height: 100%; border-radius: 50%;
  border: 2px solid rgb(var(--tone-rgb) / .18);
  border-top-color: rgb(var(--tone-rgb));
  animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.step__done, .step__fail {
  display: grid; place-items: center;
  width: var(--icon); height: var(--icon); border-radius: 50%;
}
.step__done { background: rgb(var(--tone-rgb) / .14); }
.step__fail { background: rgb(var(--danger-rgb) / .14); }
.step__done svg, .step__fail svg {
  width: 12px; height: 12px; fill: none; stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round;
}
.step__done svg { stroke: rgb(var(--tone-rgb)); }
.step__fail svg { stroke: rgb(var(--danger-rgb)); }

.step[data-status="pending"] .step__dot { opacity: 1; transform: scale(1); }
.step:not([data-status="pending"]) .step__dot { opacity: 0; transform: scale(.4); }
.step[data-status="active"] .step__spin { opacity: 1; transform: scale(1); }
.step[data-status="done"] .step__done { opacity: 1; transform: scale(1); }
.step[data-status="error"] .step__fail { opacity: 1; transform: scale(1); }

.step__label {
  font-size: 15px; line-height: 1.3;
  color: rgb(var(--text-rgb) / .38);
  transition: color .35s ease;
}
.step[data-status="active"] .step__label { color: rgb(var(--text-rgb)); }
.step[data-status="done"] .step__label { color: rgb(var(--text-rgb) / .7); }
.step[data-status="error"] .step__label { color: rgb(var(--danger-rgb)); }

/* Facts list + notice */
.facts {
  margin-top: 22px;
  padding: 2px 16px;
  border-radius: 16px;
  background: rgb(var(--text-rgb) / .045);
}
.facts > div {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  min-height: 46px; font-size: 14.5px;
}
.facts > div + div { border-top: 1px solid rgb(var(--text-rgb) / .07); }
.facts dt { color: rgb(var(--hint-rgb)); }
.facts dd { font-weight: 500; text-align: right; font-variant-numeric: tabular-nums; letter-spacing: .01em; }

.note {
  margin-top: 20px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgb(var(--danger-rgb) / .07);
  border: 1px solid rgb(var(--danger-rgb) / .16);
  font-size: 13.5px; line-height: 1.5;
  color: rgb(var(--text-rgb) / .78);
  text-align: center;
}
.note + .facts { margin-top: 12px; }

/* Buttons */
.actions { display: grid; gap: 6px; margin-top: 18px; }
.btn {
  -webkit-appearance: none; appearance: none;
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  width: 100%; min-height: 54px; padding: 0 20px;
  border: 0; border-radius: 16px;
  font: 600 16px/1 var(--font); letter-spacing: -.005em;
  text-decoration: none; cursor: pointer; user-select: none;
  transition: transform .2s var(--ease), box-shadow .25s ease, background-color .25s ease, opacity .2s ease;
}
.btn:focus-visible { outline: 2px solid rgb(var(--accent-rgb)); outline-offset: 3px; }
.btn:disabled { opacity: .6; pointer-events: none; }
:root[data-busy] .btn { pointer-events: none; }

.btn--primary {
  background: rgb(var(--accent-rgb));
  color: rgb(var(--accent-text-rgb));
  box-shadow: 0 10px 22px -10px rgb(var(--accent-rgb) / .7), inset 0 1px 0 rgb(255 255 255 / .18);
}
.btn--primary:active { transform: scale(.972); box-shadow: 0 4px 10px -6px rgb(var(--accent-rgb) / .7), inset 0 1px 0 rgb(255 255 255 / .18); }

.btn--text { min-height: 46px; background: transparent; color: rgb(var(--accent-rgb)); font-size: 15px; font-weight: 500; }
.btn--text:active { transform: scale(.98); background: rgb(var(--accent-rgb) / .09); }

@media (hover: hover) {
  .btn--primary:hover { box-shadow: 0 14px 26px -10px rgb(var(--accent-rgb) / .75), inset 0 1px 0 rgb(255 255 255 / .18); }
  .btn--text:hover { background: rgb(var(--accent-rgb) / .07); }
}
.btn svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.btn svg.is-spinning { animation: turn .6s var(--ease); }
@keyframes turn { to { transform: rotate(360deg); } }

/* Trust footer */
.trust {
  display: flex; flex-wrap: wrap; justify-content: center; gap: 8px 18px;
  margin-top: 24px; padding-top: 16px;
  border-top: 1px solid rgb(var(--text-rgb) / .07);
  font-size: 12.5px; line-height: 1.2;
  color: rgb(var(--hint-rgb));
}
.trust__item { display: inline-flex; align-items: center; gap: 6px; }
.trust svg {
  width: 14px; height: 14px; fill: none; stroke: rgb(var(--tone-rgb)); stroke-width: 1.5;
  stroke-linecap: round; stroke-linejoin: round; transition: stroke .6s ease;
}

/* ==========================================================================
   Small screens
   ========================================================================== */
@media (max-height: 660px) {
  .emblem { width: 108px; height: 108px; }
  .card { padding-top: 20px; }
  .steps { --row-h: 34px; margin-top: 18px; }
  .trust { margin-top: 18px; padding-top: 14px; }
  .subtitle { font-size: 14.5px; }
}
@media (max-width: 350px) {
  .card { padding-left: 18px; padding-right: 18px; }
  .title { font-size: 23px; }
}

/* ==========================================================================
   Reduced motion
   ========================================================================== */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .001ms !important;
    animation-iteration-count: 1 !important;
    animation-delay: 0s !important;
    transition-duration: .001ms !important;
    transition-delay: 0s !important;
  }
  .beam { display: none; }
}
</style>
</head>

<body>
<div class="ambient" aria-hidden="true"></div>

<main class="app">
  <article class="card" aria-labelledby="title">

    <!-- Emblem -->
    <div class="stage" id="stage" role="progressbar" aria-label="Verification progress"
         aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
      <svg class="emblem" viewBox="0 0 140 140" aria-hidden="true" focusable="false">
        <defs>
          <clipPath id="shieldClip">
            <path d="M70 33 L95 42.5 V68 C95 85.5 84.5 98 70 106 C55.5 98 45 85.5 45 68 V42.5 Z"/>
          </clipPath>
          <linearGradient id="beamGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" style="stop-color: rgb(var(--tone-rgb)); stop-opacity: 0"/>
            <stop offset="1" style="stop-color: rgb(var(--tone-rgb)); stop-opacity: .5"/>
          </linearGradient>
        </defs>

        <circle class="halo" cx="70" cy="70" r="46"/>
        <circle class="ring-track" cx="70" cy="70" r="60"/>
        <circle class="ring" id="ring" cx="70" cy="70" r="60" pathLength="100" transform="rotate(-90 70 70)"/>
        <circle class="ripple" cx="70" cy="70" r="60"/>

        <g class="shield-wrap">
          <path class="shield-fill" d="M70 33 L95 42.5 V68 C95 85.5 84.5 98 70 106 C55.5 98 45 85.5 45 68 V42.5 Z"/>
          <g clip-path="url(#shieldClip)">
            <g class="beam">
              <rect class="beam-glow" x="40" y="28" width="60" height="18"/>
              <rect class="beam-edge" x="40" y="45" width="60" height="1.4"/>
            </g>
          </g>
          <path class="shield-line" pathLength="100" d="M70 33 L95 42.5 V68 C95 85.5 84.5 98 70 106 C55.5 98 45 85.5 45 68 V42.5 Z"/>

          <g class="glyph glyph-device">
            <rect x="62" y="55" width="16" height="27" rx="3.5"/>
            <path d="M67.5 77.5 H72.5"/>
          </g>
          <path class="glyph glyph-check" pathLength="100" d="M59 70 L67 78 L82 60"/>
          <path class="glyph glyph-cross" pathLength="100" d="M61 60 L79 78 M79 60 L61 78"/>
        </g>
      </svg>
    </div>

    <!-- Everything below morphs in height between states -->
    <div class="morph" id="morph">
      <h1 class="title" id="title" tabindex="-1" data-swap>Device Verification</h1>
      <p class="subtitle" id="subtitle" data-swap>Your device is being securely checked. This usually takes just a few seconds.</p>

      <!-- Scanning -->
      <section class="view" id="view-scanning" data-swap>
        <ol class="steps" id="steps" aria-label="Verification steps"></ol>
      </section>

      <!-- Success -->
      <section class="view" id="view-success" data-swap hidden>
        <dl class="facts">
          <div><dt>Reference ID</dt><dd id="success-ref">—</dd></div>
          <div><dt>Verified at</dt><dd id="success-time">—</dd></div>
        </dl>
        <div class="actions">
          <button class="btn btn--primary" id="btn-continue" type="button">Continue</button>
        </div>
      </section>

      <!-- Failure -->
      <section class="view" id="view-failure" data-swap hidden>
        <p class="note" id="failure-note"></p>
        <dl class="facts" id="failure-facts" hidden>
          <div><dt>Reference ID</dt><dd id="failure-ref">—</dd></div>
        </dl>
        <div class="actions">
          <button class="btn btn--primary" id="btn-retry" type="button">
            <svg id="retry-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4v5h-5"/></svg>
            Try Again
          </button>
          <a class="btn btn--text" id="btn-support" role="button" hidden>Contact support</a>
        </div>
      </section>

      <footer class="trust">
        <span class="trust__item">
          <svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="7" width="9" height="6.5" rx="1.8"/><path d="M5.6 7V5.4a2.4 2.4 0 0 1 4.8 0V7"/></svg>
          Secure Verification
        </span>
        <span class="trust__item">
          <svg viewBox="0 0 16 16" aria-hidden="true"><rect x="4.6" y="1.8" width="6.8" height="12.4" rx="1.9"/><path d="M7 12h2"/></svg>
          One account per device
        </span>
      </footer>
    </div>
  </article>
</main>

<div class="sr-only" id="live" aria-live="polite" aria-atomic="true"></div>

<script>
(() => {
  'use strict';

  /* ========================================================================
     1. CONFIG
     Flip `useMock` to false and set `apiBaseUrl` to connect a real backend.
     While mocking, preview outcomes with:  ?mock=success | fail | error | random
     ======================================================================== */
  const CONFIG = {
    useMock: true,
    mockOutcome: new URLSearchParams(location.search).get('mock') || 'success',
    apiBaseUrl: '',                       // e.g. 'https://api.example.com'
    endpoints: { verify: '/v1/device/verify' },
    requestTimeoutMs: 20000,
    supportUrl: '',                       // e.g. 'https://t.me/your_support_bot' (hides the link when empty)
    introDelayMs: 1300                    // pause on the first screen before scanning starts
  };

  /* Verification steps shown in the UI. `ms` is the minimum time each step is
     displayed, so the sequence feels deliberate even if the API answers fast.
     The last step waits for the real API response before completing. */
  const STEPS = [
    { id: 'init',      label: 'Initializing secure check...',   ms: 900  },
    { id: 'env',       label: 'Analyzing device environment...', ms: 1250 },
    { id: 'signature', label: 'Checking device signature...',    ms: 1300 },
    { id: 'telegram',  label: 'Verifying Telegram account...',   ms: 1100 },
    { id: 'finalize',  label: 'Finalizing verification...',      ms: 1000 }
  ];

  const COPY = {
    scanning: {
      title: 'Device Verification',
      message: 'Your device is being securely checked. This usually takes just a few seconds.'
    },
    success: {
      title: 'Device Verified',
      message: 'Your device has been successfully verified.'
    }
  };

  const FAILURE_COPY = {
    DEVICE_ALREADY_LINKED: {
      title: 'Verification Failed',
      message: 'This device is already linked to another account.',
      hint: 'Each device can be linked to one account. Contact support if you think this is a mistake.'
    },
    NETWORK_ERROR: {
      title: 'Verification Failed',
      message: 'We couldn’t reach the verification service.',
      hint: 'Check your connection, then try again.'
    },
    SERVER_ERROR: {
      title: 'Verification Failed',
      message: 'The verification service is temporarily unavailable.',
      hint: 'Please try again in a moment.'
    },
    DEFAULT: {
      title: 'Verification Failed',
      message: 'We couldn’t verify this device.',
      hint: 'Please try again. If the problem continues, contact support.'
    }
  };

  /* ========================================================================
     2. UTILITIES
     ======================================================================== */
  const $ = (sel) => document.querySelector(sel);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const RM = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const EASE = 'cubic-bezier(.22, 1, .36, 1)';
  const dur = (ms) => (RM ? 0 : ms);

  const hexToTriplet = (hex) => {
    if (typeof hex !== 'string') return null;
    let h = hex.trim().replace('#', '');
    if (h.length === 3) h = h.split('').map((c) => c + c).join('');
    if (!/^[0-9a-f]{6}$/i.test(h)) return null;
    return `${parseInt(h.slice(0, 2), 16)} ${parseInt(h.slice(2, 4), 16)} ${parseInt(h.slice(4, 6), 16)}`;
  };

  const makeId = () =>
    (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
      : 'att-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);

  const makeRef = () => {
    const chunk = () => Math.random().toString(16).slice(2, 6).toUpperCase().padEnd(4, '0');
    return `VRF-${chunk()}-${chunk()}`;
  };

  const formatTime = (iso) => {
    const d = iso ? new Date(iso) : new Date();
    try { return d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }); }
    catch { return d.toLocaleString(); }
  };

  /* ========================================================================
     3. TELEGRAM BRIDGE
     Thin wrapper so the rest of the app never touches window.Telegram directly.
     Every call is version-guarded and safe outside Telegram.
     ======================================================================== */
  const Tg = (() => {
    const wa = window.Telegram && window.Telegram.WebApp;
    const supports = (v) => !!wa && typeof wa.isVersionAtLeast === 'function' && wa.isVersionAtLeast(v);
    const root = document.documentElement;
    const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');

    const applyTheme = () => {
      const p = (wa && wa.themeParams) || {};
      const scheme = (wa && wa.colorScheme) || (darkQuery.matches ? 'dark' : 'light');
      root.dataset.scheme = scheme;

      const vars = {
        '--bg-rgb': p.secondary_bg_color || p.bg_color,
        '--card-rgb': p.section_bg_color || p.bg_color,
        '--text-rgb': p.text_color,
        '--hint-rgb': p.hint_color,
        '--accent-rgb': p.button_color || p.link_color,
        '--accent-text-rgb': p.button_text_color
      };
      Object.entries(vars).forEach(([name, hex]) => {
        const triplet = hexToTriplet(hex);
        if (triplet) root.style.setProperty(name, triplet);
        else root.style.removeProperty(name);
      });
    };

    const haptic = {
      impact: (s = 'light') => { try { wa && wa.HapticFeedback && wa.HapticFeedback.impactOccurred(s); } catch {} },
      notify: (t) => { try { wa && wa.HapticFeedback && wa.HapticFeedback.notificationOccurred(t); } catch {} },
      select: () => { try { wa && wa.HapticFeedback && wa.HapticFeedback.selectionChanged(); } catch {} }
    };

    return {
      wa,
      inTelegram: !!(wa && wa.initData),
      haptic,

      init() {
        applyTheme();
        if (wa) {
          wa.ready();
          wa.expand();
          if (supports('7.7')) wa.disableVerticalSwipes();      // avoid accidental swipe-to-close mid-check
          if (supports('6.1')) {
            wa.setHeaderColor('secondary_bg_color');
            wa.setBackgroundColor('secondary_bg_color');
          }
          if (supports('7.10')) wa.setBottomBarColor('secondary_bg_color');
          wa.onEvent('themeChanged', applyTheme);
        } else {
          darkQuery.addEventListener && darkQuery.addEventListener('change', applyTheme);
        }
      },

      /* Data your backend needs. `initData` is the signed string the server
         must validate (HMAC) before trusting anything about the user. */
      getContext(attemptId) {
        return {
          attemptId,
          initData: (wa && wa.initData) || '',
          client: {
            platform: (wa && wa.platform) || 'web',
            telegramVersion: (wa && wa.version) || null,
            colorScheme: root.dataset.scheme
          }
        };
      },

      setClosingConfirmation(on) {
        if (!supports('6.2')) return;
        on ? wa.enableClosingConfirmation() : wa.disableClosingConfirmation();
      },

      openLink(url) {
        if (!url) return;
        if (wa && /^https:\/\/t\.me\//i.test(url) && wa.openTelegramLink) wa.openTelegramLink(url);
        else if (wa && wa.openLink) wa.openLink(url);
        else window.open(url, '_blank', 'noopener');
      },

      close() {
        if (wa && this.inTelegram) wa.close();
        else location.reload();          // local preview: replay the demo
      }
    };
  })();

  /* ========================================================================
     4. VERIFICATION API
     Contract used by the UI (adapt `normalizeResult` if your backend differs):

       verify(context) -> Promise<{
         status: 'verified' | 'rejected',
         referenceId?: string,
         verifiedAt?: string (ISO 8601),
         reason?: 'DEVICE_ALREADY_LINKED' | 'CHECK_FAILED' | ...
       }>

     Throws ApiError('NETWORK_ERROR' | 'SERVER_ERROR') on transport problems.

     Note: a web page cannot read IMEI, MAC address, SIM number or hardware
     serials, and this file does not try to. Device binding decisions must be
     made server-side; the client only forwards Telegram's signed `initData`.
     ======================================================================== */
  class ApiError extends Error {
    constructor(code, status) { super(code); this.code = code; this.status = status; }
  }

  const normalizeResult = (raw) => {
    if (raw && (raw.status === 'verified' || raw.verified === true)) {
      return { status: 'verified', referenceId: raw.referenceId, verifiedAt: raw.verifiedAt };
    }
    return {
      status: 'rejected',
      reason: (raw && raw.reason) || 'CHECK_FAILED',
      referenceId: raw && raw.referenceId
    };
  };

  const HttpApi = {
    async verify(ctx) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), CONFIG.requestTimeoutMs);
      try {
        const res = await fetch(CONFIG.apiBaseUrl + CONFIG.endpoints.verify, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `tma ${ctx.initData}`     // validate server-side
          },
          body: JSON.stringify({ attemptId: ctx.attemptId, client: ctx.client }),
          signal: controller.signal
        });
        // 409/403 style responses may carry a structured rejection body.
        if (!res.ok && ![403, 409].includes(res.status)) throw new ApiError('SERVER_ERROR', res.status);
        return normalizeResult(await res.json());
      } catch (err) {
        if (err instanceof ApiError) throw err;
        throw new ApiError('NETWORK_ERROR');
      } finally {
        clearTimeout(timer);
      }
    }
  };

  const MockApi = {
    async verify(ctx) {
      console.info('[MockApi] verify()', ctx);
      await sleep(2200 + Math.random() * 900);
      const mode = CONFIG.mockOutcome === 'random'
        ? (Math.random() < 0.5 ? 'success' : 'fail')
        : CONFIG.mockOutcome;
      if (mode === 'error') throw new ApiError('NETWORK_ERROR');
      if (mode === 'fail') return { status: 'rejected', reason: 'DEVICE_ALREADY_LINKED', referenceId: makeRef() };
      return { status: 'verified', referenceId: makeRef(), verifiedAt: new Date().toISOString() };
    }
  };

  const Api = CONFIG.useMock ? MockApi : HttpApi;

  /* ========================================================================
     5. UI LAYER
     ======================================================================== */
  const root = document.documentElement;
  const els = {
    stage: $('#stage'), ring: $('#ring'), morph: $('#morph'),
    title: $('#title'), subtitle: $('#subtitle'), live: $('#live'),
    steps: $('#steps'),
    successRef: $('#success-ref'), successTime: $('#success-time'),
    failureNote: $('#failure-note'), failureFacts: $('#failure-facts'), failureRef: $('#failure-ref'),
    btnContinue: $('#btn-continue'), btnRetry: $('#btn-retry'), btnSupport: $('#btn-support'),
    retryIcon: $('#retry-icon')
  };
  const VIEWS = {
    scanning: $('#view-scanning'),
    success: $('#view-success'),
    failure: $('#view-failure')
  };

  let currentView = 'scanning';
  let stepEls = [];

  const announce = (msg) => { els.live.textContent = ''; setTimeout(() => { els.live.textContent = msg; }, 30); };

  const ui = {
    buildSteps() {
      els.steps.innerHTML = STEPS.map((s) => `
        <li class="step" data-status="pending">
          <span class="step__icon" aria-hidden="true">
            <i class="step__dot"></i>
            <span class="step__spin"><i></i></span>
            <span class="step__done"><svg viewBox="0 0 16 16"><path d="M3.5 8.6l3 3L12.5 5"/></svg></span>
            <span class="step__fail"><svg viewBox="0 0 16 16"><path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/></svg></span>
          </span>
          <span class="step__label">${s.label}</span>
        </li>`).join('');
      stepEls = [...els.steps.children];
    },

    setState(state) { root.dataset.state = state; },

    setProgress(pct, ms) {
      els.ring.style.setProperty('--ring-ms', dur(ms) + 'ms');
      els.ring.style.strokeDashoffset = String(100 - pct);
      els.stage.setAttribute('aria-valuenow', String(Math.round(pct)));
    },

    setStep(index, ms) {
      stepEls.forEach((el, i) => {
        el.dataset.status = i < index ? 'done' : i === index ? 'active' : 'pending';
        i === index ? el.setAttribute('aria-current', 'step') : el.removeAttribute('aria-current');
      });
      // Last step holds at 94% until the real API response arrives.
      const target = index < STEPS.length - 1 ? ((index + 1) / STEPS.length) * 100 : 94;
      ui.setProgress(target, ms);
      announce(STEPS[index].label.replace('...', ''));
    },

    completeSteps() {
      stepEls.forEach((el) => { el.dataset.status = 'done'; el.removeAttribute('aria-current'); });
      ui.setProgress(100, 450);
    },

    failActiveStep() {
      const active = stepEls.find((el) => el.dataset.status === 'active') || stepEls[stepEls.length - 1];
      if (active) active.dataset.status = 'error';
    },

    resetSteps() {
      stepEls.forEach((el) => { el.dataset.status = 'pending'; el.removeAttribute('aria-current'); });
      els.ring.style.transition = 'none';
      els.ring.style.strokeDashoffset = '100';
      void els.ring.getBoundingClientRect();     // flush, then re-enable transitions
      els.ring.style.transition = '';
    },

    renderExtras(state, data) {
      if (state === 'success') {
        els.successRef.textContent = data.referenceId || '—';
        els.successTime.textContent = formatTime(data.verifiedAt);
      }
      if (state === 'failure') {
        const c = FAILURE_COPY[data.reason] || FAILURE_COPY.DEFAULT;
        els.failureNote.textContent = c.hint;
        els.failureFacts.hidden = !data.referenceId;
        els.failureRef.textContent = data.referenceId || '—';
      }
    },

    copyFor(state, data) {
      if (state === 'success') return COPY.success;
      if (state === 'failure') return FAILURE_COPY[data.reason] || FAILURE_COPY.DEFAULT;
      return COPY.scanning;
    }
  };

  /* Animate the height of the content area so the card resizes smoothly. */
  async function morph(mutate) {
    const el = els.morph;
    const h0 = el.getBoundingClientRect().height;
    mutate();                                    // runs synchronously
    const h1 = el.getBoundingClientRect().height;
    if (RM || Math.abs(h1 - h0) < 1) return;
    el.style.overflow = 'hidden';
    try {
      await el.animate([{ height: h0 + 'px' }, { height: h1 + 'px' }], { duration: 520, easing: EASE }).finished;
    } catch {}
    el.style.overflow = '';
  }

  /* Cross-fade between states: fade out -> swap content -> fade in. */
  async function transitionTo(next, data = {}) {
    const fromEl = VIEWS[currentView];
    const toEl = VIEWS[next];

    const outTargets = [els.title, els.subtitle, fromEl];
    const outs = outTargets.map((el) => el.animate(
      [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(-6px)' }],
      { duration: dur(180), easing: 'ease-in', fill: 'forwards' }
    ));

    ui.setState(next);
    if (next === 'scanning') ui.setProgress(0, 350);
    else ui.setProgress(100, 500);

    await Promise.all(outs.map((a) => a.finished.catch(() => {})));

    const heightDone = morph(() => {
      outs.forEach((a) => a.cancel());
      const copy = ui.copyFor(next, data);
      els.title.textContent = copy.title;
      els.subtitle.textContent = copy.message;
      ui.renderExtras(next, data);
      if (next === 'scanning') ui.resetSteps();
      fromEl.hidden = true;
      toEl.hidden = false;
    });

    [els.title, els.subtitle, toEl].forEach((el, i) => {
      el.animate(
        [{ opacity: 0, transform: 'translateY(10px)' }, { opacity: 1, transform: 'none' }],
        { duration: dur(480), delay: dur(80 + i * 70), easing: EASE, fill: 'backwards' }
      );
    });

    currentView = next;
    await heightDone;

    const copy = ui.copyFor(next, data);
    announce(`${copy.title}. ${copy.message}`);
    if (next !== 'scanning') els.title.focus({ preventScroll: true });
  }

  /* ========================================================================
     6. FLOW CONTROLLER
     ======================================================================== */
  let busy = false;
  const setBusy = (v) => { busy = v; v ? root.setAttribute('data-busy', '') : root.removeAttribute('data-busy'); };

  async function runAttempt() {
    const ctx = Tg.getContext(makeId());
    Tg.setClosingConfirmation(true);

    // Fire the request immediately; the step timeline runs alongside it.
    const pending = Api.verify(ctx).then(
      (result) => ({ ok: true, result }),
      (error) => ({ ok: false, error })
    );

    ui.setState('scanning');
    for (let i = 0; i < STEPS.length; i++) {
      ui.setStep(i, STEPS[i].ms);
      if (i > 0) Tg.haptic.select();
      await sleep(STEPS[i].ms);
    }

    const outcome = await pending;                 // waits here if the API is slower than the timeline
    const result = outcome.ok
      ? outcome.result
      : { status: 'rejected', reason: (outcome.error && outcome.error.code) || 'DEFAULT' };

    Tg.setClosingConfirmation(false);

    if (result.status === 'verified') {
      ui.completeSteps();
      await sleep(dur(650));
      await transitionTo('success', result);
      Tg.haptic.notify('success');
    } else {
      ui.failActiveStep();
      await sleep(dur(750));
      await transitionTo('failure', result);
      Tg.haptic.notify('error');
    }
  }

  async function start() {
    if (busy) return;
    setBusy(true);
    try { await runAttempt(); }
    catch (err) {
      console.error(err);
      Tg.setClosingConfirmation(false);
      await transitionTo('failure', { reason: 'DEFAULT' });
    }
    finally { setBusy(false); }
  }

  async function retry() {
    if (busy) return;
    setBusy(true);
    Tg.haptic.impact('light');
    els.retryIcon.classList.remove('is-spinning');
    void els.retryIcon.getBoundingClientRect();
    els.retryIcon.classList.add('is-spinning');
    try {
      await transitionTo('scanning');
      await runAttempt();
    } catch (err) {
      console.error(err);
      Tg.setClosingConfirmation(false);
      await transitionTo('failure', { reason: 'DEFAULT' });
    } finally { setBusy(false); }
  }

  /* ========================================================================
     7. BOOT
     ======================================================================== */
  Tg.init();
  ui.buildSteps();

  els.btnRetry.addEventListener('click', retry);
  els.btnContinue.addEventListener('click', () => { Tg.haptic.impact('light'); Tg.close(); });

  if (CONFIG.supportUrl) {
    els.btnSupport.hidden = false;
    els.btnSupport.href = CONFIG.supportUrl;
    els.btnSupport.addEventListener('click', (e) => { e.preventDefault(); Tg.openLink(CONFIG.supportUrl); });
  }

  sleep(dur(CONFIG.introDelayMs)).then(start);
})();
</script>
</body>
</html>



def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            fingerprint TEXT PRIMARY KEY,
            telegram_user_id TEXT NOT NULL,
            username TEXT,
            first_verified_at INTEGER NOT NULL,
            last_seen_at INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_user_id TEXT PRIMARY KEY,
            username TEXT,
            fingerprint TEXT,
            verified_at INTEGER
        )
    """)
    conn.commit()
    conn.close()

def validate_telegram_init_data(init_data: str):
    """Validate Telegram Mini App initData using Telegram's documented HMAC scheme."""
    if not init_data:
        return None

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    # data_check_string is alphabetically sorted key=value pairs.
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(pairs.items())
    )

    secret_key = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode(),
        hashlib.sha256
    ).digest()

    calculated = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated, received_hash):
        return None

    # Optional freshness check: reject very old initData.
    auth_date = int(pairs.get("auth_date", "0") or 0)
    if not auth_date or abs(int(time.time()) - auth_date) > 86400:
        return None

    user_raw = pairs.get("user")
    if not user_raw:
        return None

    try:
        return json.loads(user_raw)
    except json.JSONDecodeError:
        return None

@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/health")
def health():
    return "OK"

@app.post("/api/verify")
def verify():
    body = request.get_json(silent=True) or {}
    init_data = body.get("init_data", "")
    fingerprint = body.get("fingerprint", "").strip()

    if not fingerprint or len(fingerprint) != 64:
        return jsonify(ok=False, message="Invalid device fingerprint."), 400

    tg_user = validate_telegram_init_data(init_data)
    if not tg_user:
        return jsonify(ok=False, message="Telegram verification failed."), 401

    user_id = str(tg_user["id"])
    username = tg_user.get("username", "")

    conn = db()
    try:
        # Same physical/browser fingerprint already linked to another Telegram ID.
        row = conn.execute(
            "SELECT telegram_user_id FROM devices WHERE fingerprint=?",
            (fingerprint,)
        ).fetchone()

        if row and row["telegram_user_id"] != user_id:
            return jsonify(
                ok=False,
                message="This device is already verified for another Telegram account."
            ), 403

        # This Telegram ID already has another fingerprint.
        user_row = conn.execute(
            "SELECT fingerprint FROM users WHERE telegram_user_id=?",
            (user_id,)
        ).fetchone()

        now = int(time.time())

        if user_row and user_row["fingerprint"] != fingerprint:
            return jsonify(
                ok=False,
                message="This Telegram account is already linked to a different device."
            ), 403

        if not row:
            conn.execute(
                """INSERT INTO devices
                   (fingerprint, telegram_user_id, username, first_verified_at, last_seen_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (fingerprint, user_id, username, now, now)
            )
        else:
            conn.execute(
                "UPDATE devices SET last_seen_at=?, username=? WHERE fingerprint=?",
                (now, username, fingerprint)
            )

        if not user_row:
            conn.execute(
                """INSERT INTO users
                   (telegram_user_id, username, fingerprint, verified_at)
                   VALUES (?, ?, ?, ?)""",
                (user_id, username, fingerprint, now)
            )
        else:
            conn.execute(
                "UPDATE users SET username=?, verified_at=? WHERE telegram_user_id=?",
                (username, now, user_id)
            )

        conn.commit()
        return jsonify(ok=True, message="Device verified.")
    finally:
        conn.close()


async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # The Mini App can send a small confirmation payload before closing.
    # The actual verification is already completed server-side.
    await update.message.reply_text(
        "✅ Device Verification Complete!\n\n"
        "Ab aap bot me wapas aa gaye hain. 🎉\n"
        "Aap next step continue kar sakte hain."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton(
            "🔐 Verify My Device",
            web_app=WebAppInfo(url=WEB_APP_URL)
        )
    ]]
    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Open the Mini App to scan the available browser/device signals "
        "and verify this Telegram account.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def run_web():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

def main():
    init_db()
    Thread(target=run_web, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))

    print("Bot + Mini App server started")
    application.run_polling()

if __name__ == "__main__":
    main()
