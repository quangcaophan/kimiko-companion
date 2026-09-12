/**
 * PlaybackController - Persistent audio element for mobile-compatible playback.
 * Handles AudioContext unlocking across browsers/platforms.
 */

/** Ensure a URL is absolute (relative paths get prefixed with origin). */
function ensureAbsoluteUrl(url) {
  try {
    new URL(url);
    return url;
  } catch {
    if (!url) return url;
    if (url.startsWith('/')) return `${location.origin}${url}`;
    return `${location.origin}/${url}`;
  }
}

export class PlaybackController {
  constructor(audioMgr) {
    this.audioMgr = audioMgr;
    this._inited = false;
    this._unlocked = false;
    this.el = null;
    this._analyserAttached = false;
  }

  initPersistent() {
    if (this._inited) return;
    this._inited = true;

    // Create persistent audio element
    if (!this.audioMgr.audioElement) {
      const a = document.createElement('audio');
      a.crossOrigin = 'anonymous';
      a.preload = 'auto';
      a.playsInline = true;
      a.setAttribute('playsinline', '');
      a.setAttribute('webkit-playsinline', '');
      a.style.display = 'none';
      document.body.appendChild(a);
      this.audioMgr.audioElement = a;
    }
    this.el = this.audioMgr.audioElement;

    // Create AudioContext if needed
    try {
      if (!this.audioMgr.audioContext) {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (AC) {
          this.audioMgr.audioContext = new AC();
        }
      }

      if (this.audioMgr.audioContext && !this.audioMgr.analyser) {
        this._tryAttachAnalyser();
      }

      // Visibility resume helper
      document.addEventListener('visibilitychange', async () => {
        if (document.visibilityState === 'visible' &&
            this.audioMgr.audioContext &&
            this.audioMgr.audioContext.state === 'suspended') {
          try {
            await this.audioMgr.audioContext.resume();
          } catch (e) {}
        }
      });
    } catch (e) {
      console.warn('PlaybackController init error:', e);
    }
  }

  // Unlock audio on user gesture - tries multiple strategies
  async unlockOnce() {
    // Even if already unlocked, always ensure the AudioContext is running
    // (it can become suspended after inactivity or if created without gesture)
    let ctx = this.audioMgr.audioContext;
    if (this._unlocked && ctx && ctx.state === 'running') return true;

    this.initPersistent();

    // 1) Try to resume/create AudioContext
    try {
      if (!this.audioMgr.audioContext) {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (AC) {
          this.audioMgr.audioContext = new AC();
        }
      }
      ctx = this.audioMgr.audioContext;
      if (ctx && ctx.state === 'suspended') {
        try { await ctx.resume(); } catch (e) { console.warn('resume() failed:', e); }
      }
    } catch (e) {
      console.warn('AudioContext creation/resume failed:', e);
    }

    // 2) Try silent buffer (works on many browsers)
    try {
      if (ctx && ctx.state === 'running') {
        const sampleRate = ctx.sampleRate || 44100;
        const length = Math.max(1, Math.floor(sampleRate * 0.01));
        const buffer = ctx.createBuffer(1, length, sampleRate);
        const src = ctx.createBufferSource();
        src.buffer = buffer;
        src.connect(ctx.destination);
        src.start(0);
        await new Promise(res => setTimeout(res, 40));
        try { src.stop(); } catch (e) {}
        this._unlocked = true;
        this._tryAttachAnalyser();
        return true;
      }
    } catch (e) {
      console.warn('Silent buffer unlock failed:', e);
    }

    // 3) Fallback: muted play/pause on persistent element
    try {
      const el = this.el;
      if (!el) throw new Error('No audio element');
      const hadSrc = !!el.src;
      if (!hadSrc) {
        el.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA=';
      }
      el.muted = true;
      el.playsInline = true;
      el.setAttribute('playsinline', '');
      el.setAttribute('webkit-playsinline', '');

      const p = new Promise((resolve, reject) => {
        let done = false;
        const onPlaying = () => { if (!done) { done = true; cleanup(); resolve(true); } };
        const onError = () => { if (!done) { done = true; cleanup(); reject(new Error('audio error')); } };
        const timeoutId = setTimeout(() => { if (!done) { done = true; cleanup(); reject(new Error('timeout')); } }, 1200);
        function cleanup() {
          el.removeEventListener('playing', onPlaying);
          el.removeEventListener('error', onError);
          clearTimeout(timeoutId);
        }
        el.addEventListener('playing', onPlaying);
        el.addEventListener('error', onError);
        try {
          const prom = el.play();
          if (prom && prom.catch) prom.catch(() => {});
        } catch (err) { cleanup(); reject(err); }
      });

      await p;
      try { el.pause(); el.currentTime = 0; } catch (e) {}
      el.muted = false;
      this._unlocked = true;
      this._tryAttachAnalyser();
      return true;
    } catch (e) {
      console.warn('Muted element fallback failed:', e);
    }

    console.warn('unlockOnce: could not unlock audio on this gesture');
    return false;
  }

  _tryAttachAnalyser() {
    try {
      if (this.audioMgr.audioContext && this.el && !this.audioMgr.analyser && !this._analyserAttached) {
        try {
          // Use captureStream() instead of createMediaElementSource().
          // createMediaElementSource() HIJACKS the element — audio ONLY flows through
          // the Web Audio graph, bypassing the browser's default speaker output.
          // captureStream() is NON-DESTRUCTIVE: the element still outputs to speakers
          // normally, and we get a parallel copy for lip-sync analysis.
          const stream = this.el.captureStream ? this.el.captureStream()
                       : this.el.mozCaptureStream ? this.el.mozCaptureStream()
                       : null;

          if (stream && stream.getAudioTracks().length > 0) {
            const src = this.audioMgr.audioContext.createMediaStreamSource(stream);
            const analyser = this.audioMgr.audioContext.createAnalyser();
            analyser.fftSize = 2048;
            src.connect(analyser);
            // NOTE: Do NOT connect analyser to destination — we're only analysing,
            // not routing. Audio already plays via the element's default output.
            this.audioMgr.analyser = analyser;
            this.audioMgr.timeDomainData = new Uint8Array(analyser.fftSize);
            this.audioMgr.freqData = new Uint8Array(analyser.frequencyBinCount);
            this._analyserAttached = true;
            console.log('✅ Analyser attached via captureStream (non-destructive)');
          } else {
            console.warn('captureStream not available — lip sync disabled, audio plays normally');
            this._analyserAttached = true; // Prevent retry loops
          }
        } catch (e) {
          console.warn('attachAnalyser failed:', e);
          this._analyserAttached = true; // Prevent retry loops
        }
      }
    } catch (e) {
      console.warn('Error in _tryAttachAnalyser:', e);
    }
  }

  // Play audio URL using persistent element
  async playAudioUrl(url) {
    if (!url) return false;
    this.initPersistent();

    if (!this._unlocked) {
      console.warn('playAudioUrl: audio not unlocked yet. Attempting auto-unlock...');
      try { await this.unlockOnce(); } catch (e) {}
    }

    const abs = ensureAbsoluteUrl(url);
    const el = this.el;
    const ctx = this.audioMgr.audioContext;

    // --- DEEP DIAGNOSTICS ---
    console.group(`🔍 playAudioUrl: ${url}`);
    console.log('  abs URL  :', abs);
    console.log('  unlocked :', this._unlocked);
    console.log('  ctx state:', ctx ? ctx.state : 'NO CONTEXT');
    console.log('  analyser :', this._analyserAttached ? 'attached' : 'not attached');
    console.log('  el.volume:', el ? el.volume : 'NO EL');
    console.log('  el.muted :', el ? el.muted : 'N/A');

    // Listen for audio element errors
    const onError = () => {
      const err = el.error;
      console.error('❌ Audio element error!', {
        code: err?.code,
        message: err?.message,
        networkState: el.networkState,  // 0=empty 1=idle 2=loading 3=no_src
        readyState: el.readyState,      // 0=nothing 4=enough_data
        src: el.src
      });
    };
    el.addEventListener('error', onError, { once: true });

    // Stop current playback
    try { el.pause(); el.currentTime = 0; } catch (e) {}

    // Set src only if changed
    if (!el.src || el.src !== abs) {
      el.src = abs;
      try { el.load(); } catch (e) {}
    }

    // Ensure AudioContext running
    try {
      if (ctx && ctx.state !== 'running') {
        console.log('  🔄 Resuming ctx...');
        await ctx.resume();
        console.log('  ✅ ctx resumed, state:', ctx.state);
      }
    } catch (e) { console.warn('  ⚠️ ctx resume failed:', e); }

    // Try to play
    try {
      await el.play();
      el.removeEventListener('error', onError);
      console.log('  ▶ play() OK | currentTime:', el.currentTime, '| duration:', el.duration, '| paused:', el.paused, '| volume:', el.volume, '| muted:', el.muted);
      // Check if audio is actually advancing after 400ms
      setTimeout(() => {
        console.log(`  ⏱ 400ms check | currentTime: ${el.currentTime.toFixed(3)} | paused: ${el.paused} | ended: ${el.ended}`);
        console.groupEnd();
      }, 400);
      this._tryAttachAnalyser();
      return true;
    } catch (err) {
      console.warn('  play() blocked:', err.name, err.message);
    }

    // Muted-first fallback
    try {
      console.log('  🔇 Trying muted-first...');
      el.muted = true;
      await el.play();
      await new Promise(r => setTimeout(r, 80));
      el.muted = false;
      console.log('  ✅ Muted-first OK, unmuted');
      this._tryAttachAnalyser();
      console.groupEnd();
      return true;
    } catch (err) {
      console.warn('  Muted-first failed:', err);
    }

    // Transient fallback: fresh Audio element (bypasses all caching & context issues)
    try {
      console.log('  🆕 Trying fresh Audio() element...');
      const tmp = new Audio(abs);
      tmp.playsInline = true;
      tmp.volume = 1.0;
      document.body.appendChild(tmp);
      await tmp.play();
      console.log('  ✅ Fresh Audio() playing! duration:', tmp.duration);
      // Wait for it to finish, then clean up
      tmp.addEventListener('ended', () => { try { tmp.remove(); } catch(e){} });
      console.groupEnd();
      return true;
    } catch (err) {
      console.warn('  Fresh Audio() failed:', err);
    }

    el.removeEventListener('error', onError);
    console.error('  ❌ ALL strategies failed for', abs);
    console.groupEnd();
    return false;
  }
}
