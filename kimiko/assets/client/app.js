import * as THREE from 'three';

import { VRM_PATH, WS_URL } from './config.js';
import { createScene } from './scene/sceneSetup.js';
import { loadSceneObjects, describeObjects } from './scene/objectLoader.js';
import { SCENE_OBJECTS } from './scene/objectsConfig.js';
import { loadRoom } from './scene/roomLoader.js';
import { ROOM_CONFIG } from './scene/roomConfig.js';
import { createLocationRegistry } from './scene/locationRegistry.js';
import { NAMED_LOCATIONS, DEBUG_MARKERS } from './scene/locationsConfig.js';
import { loadVRM } from './core/vrmLoader.js';
import { AudioManager } from './core/audioManager.js';
import { PlaybackController } from './core/playbackController.js';
import { AnimationManager } from './animation/animationManager.js';
import { MovementController } from './animation/movementController.js';
import { showSubtitleStreaming, setSubtitlesEnabled, getSubtitlesEnabled } from './overlay/subtitles.js';
import { initWebcam, takePictureAndUpload } from './interaction/webcam.js';
import { connectWS, initUI } from './ui.js';
import { initVRMClickDetector } from './interaction/vrmClickDetector.js';

// --- UI Init ---
initUI();

// --- Subtitle toggle ---
const subtitleBtn = document.getElementById('toggle-subtitles-button');
if (subtitleBtn) {
  subtitleBtn.addEventListener('click', () => {
    const nowEnabled = !getSubtitlesEnabled();
    setSubtitlesEnabled(nowEnabled);
    subtitleBtn.classList.toggle('off', !nowEnabled);
  });
}

// Initialize webcam non-blockingly so missing camera never breaks 3D avatar or chat
initWebcam().catch(err => console.warn("Webcam optional init skipped:", err));

// --- App State ---
let vrm = null;
let renderer = null;
let scene = null;
let camera = null;
let controls = null;
let audioMgr = null;
let animationMgr = null;
let movementController = null;
let playbackController = null;
const clock = new THREE.Clock();

(async () => {
  // --- Check VR support ---
  const vrSupported = false;
  if (vrSupported) console.log('WebXR VR supported - VR mode available');

  // --- Scene Setup ---
  // Adjust these options to change the scene configuration.
  // See scene/sceneSetup.js DEFAULTS for all available options.
  ({ renderer, scene, camera, controls } = createScene({
    // background: 0x000000,  // Uncomment for black background
    // gridHelper: 50,        // Uncomment for grid
    // axesHelper: 5,         // Uncomment for axes
  }));

  // --- Room (environment GLB) ---
  await loadRoom(scene, ROOM_CONFIG);

  // --- Scene Objects (GLB props) ---
  const sceneObjects = await loadSceneObjects(scene, SCENE_OBJECTS);
  window.sceneObjects = sceneObjects;
  window.describeSceneObjects = () => describeObjects(sceneObjects);

  // --- Named locations (waypoints + scene objects merged) ---
  const locations = createLocationRegistry({
    scene,
    namedLocations: NAMED_LOCATIONS,
    sceneObjects,
    debugMarkers: DEBUG_MARKERS,
  });
  window.locations = locations;
  console.log('📍 Locations registered:', locations.describe());

  // --- Load VRM ---
  const vrmData = await loadVRM(VRM_PATH, scene);
  vrm = vrmData.vrm;

  // --- Click Detection ---
  initVRMClickDetector(renderer, camera, vrm, (region, partName) => {
    console.log(`📩 Region clicked: ${region}`);
  });

  // --- Managers ---
  audioMgr = new AudioManager(vrm);
  animationMgr = new AnimationManager(vrm, audioMgr, renderer, scene, camera, controls);
  animationMgr.setState('idle');

  // --- Movement Controller ---
  movementController = new MovementController(vrm, scene, animationMgr);
  await movementController.loadIdleAnimation('./animations/mixamo/Idle.fbx');
  await movementController.loadWalkAnimation('./animations/mixamo/Walking_inplace.fbx');
  await movementController.loadAdditiveAnimation('./animations/mixamo/Waving.fbx', 'wave');

  // --- VR Setup (conditional) ---
  if (vrSupported) {
    const { VRManager } = await import('./vr/vrManager.js');
    const { VRPositionTracker } = await import('./vr/vrPositionTracker.js');

    vrManager = new VRManager(renderer, scene, camera, controls);
    vrManager.init();

    // Enable proximity-based touch interaction on the VRM in VR
    vrManager.initTouchDetection(vrm, {
      onTouch: (region, boneName, handIndex) => {
        console.log(`VR touch: ${region} (hand ${handIndex})`);
      },
    });

    vrPositionTracker = new VRPositionTracker(camera, vrManager.getDolly());

    window.addEventListener('vr-session-start', () => vrPositionTracker.enable());
    window.addEventListener('vr-session-end', () => vrPositionTracker.disable());
    window.addEventListener('vr-unlock-audio', async () => {
      try { await playbackController?.unlockOnce(); } catch (e) { }
    });

    window.vrManager = vrManager;
    window.vrPositionTracker = vrPositionTracker;
  }

  // --- Playback Controller (mobile audio unlock) ---
  playbackController = new PlaybackController(audioMgr);
  playbackController.initPersistent();

  // If user already clicked the unlock overlay before VRM finished loading, apply now
  if (window._audioUnlockedByGesture) {
    playbackController._unlocked = true;
    console.log('✅ PlaybackController marked unlocked from prior gesture.');
  }

  window.playbackController = playbackController;
  window.audioMgr = audioMgr;
  window.animationMgr = animationMgr;

  // Gesture-based audio unlock (mobile browsers require user gesture)
  const onFirstGesture = async () => {
    try { await playbackController.unlockOnce(); } catch (e) { }
    window.removeEventListener('pointerdown', onFirstGesture, { capture: true });
    window.removeEventListener('touchend', onFirstGesture, { capture: true });
    window.removeEventListener('keydown', onFirstGesture, { capture: true });
  };
  window.addEventListener('pointerdown', onFirstGesture, { capture: true });
  window.addEventListener('touchend', onFirstGesture, { capture: true });
  window.addEventListener('keydown', onFirstGesture, { capture: true });

  // --- Animation Loop ---
  clock.start();

  function animate() {
    const deltaTime = clock.getDelta();

    if (animationMgr) animationMgr.update(deltaTime);
    if (movementController) movementController.update(deltaTime);

    vrm.update(deltaTime);
    renderer.render(scene, camera);
    controls.update();
  }

  (function loop() {
    requestAnimationFrame(loop);
    animate();
  })();

  // --- WebSocket Message Handler ---
  const ws = new WebSocket(WS_URL);
  ws.onopen = () => console.log('✅ WebSocket connected');
  ws.onerror = err => console.error('WS error', err);

  ws.onmessage = async ({ data }) => {
    let msg;
    try {
      msg = JSON.parse(data);
      console.log('📨 Message received:', msg);
    } catch { return; }

    // --- Movement commands ---
    if (msg.type === 'walk_to') {
      const { x, y, z, speed } = msg;
      if (speed) movementController.setSpeed(speed);
      movementController.walkTo(x, y, z);
    }

    if (msg.type === 'stop_movement') {
      movementController.stop();
    }

    if (msg.type === 'teleport_to') {
      const { x, y, z } = msg;
      movementController.teleportTo(x, y, z);
    }

    if (msg.type === 'set_speed') {
      movementController.setSpeed(msg.speed);
    }

    if (msg.type === 'load_walk_animation') {
      await movementController.loadWalkAnimation(msg.url);
    }

    if (msg.type === 'load_idle_animation') {
      await movementController.loadIdleAnimation(msg.url);
    }

    // --- Additive blending ---
    if (msg.type === 'set_additive_weight') {
      const { anim_name, weight, duration } = msg;
      movementController.setAdditiveWeight(anim_name, weight, duration || 0.25);
    }

    if (msg.type === 'play_additive_once') {
      const { anim_name, fade_in, fade_out } = msg;
      movementController.playAdditiveOnce(anim_name, fade_in || 0.25, fade_out || 0.25);
    }

    if (msg.type === 'load_additive_animation') {
      const { url, name } = msg;
      await movementController.loadAdditiveAnimation(url, name);
    }

    if (msg.type === 'load_and_play_additive') {
      const { url, name, weight = 1.0, play_once = false, fade_in = 0.25, fade_out = 0.25 } = msg;
      try {
        const loaded = await movementController.loadAdditiveAnimation(url, name);
        if (loaded) {
          if (play_once) {
            movementController.playAdditiveOnce(name, fade_in, fade_out);
          } else {
            movementController.setAdditiveWeight(name, weight, fade_in);
          }
        }
      } catch (err) {
        console.error(`Failed to load and play additive animation ${name}:`, err);
      }
    }

    // --- State control ---
    if (msg.type === 'set_state') {
      const { state } = msg;
      if (animationMgr && ['idle', 'listening', 'thinking', 'talking'].includes(state)) {
        animationMgr.setState(state);
      }
    }

    if (msg.type === 'set_movement_lock_duration') {
      const { duration } = msg;
      if (animationMgr && typeof duration === 'number') {
        animationMgr.setMovementLockDuration(duration);
      }
    }

    // --- Audio playback ---
    if (msg.type === 'start_animation') {
      const { audio_path, expression = 'neutral', audio_text } = msg;
      const duration = msg.audio_duration ?? msg.audio_duraction;
      console.log('🎵 start_animation received:', audio_path, 'duration:', duration);
      audioMgr.setExpression(expression);

      // Show subtitles while this chunk plays
      if (audio_text && duration) {
        showSubtitleStreaming(audio_text, duration);
      }

      try {
        // Step 1: Always try to resume AudioContext — works after any prior user interaction
        const ctx = audioMgr.audioContext;
        if (ctx && ctx.state !== 'running') {
          console.log('🔄 AudioContext state:', ctx.state, '— resuming...');
          try { await ctx.resume(); console.log('✅ AudioContext resumed'); }
          catch (e) { console.warn('⚠️ AudioContext resume failed:', e); }
        } else if (ctx) {
          console.log('✅ AudioContext already running');
        } else {
          console.warn('⚠️ No AudioContext available');
        }

        // Step 2: Play audio
        const ok = await playbackController.playAudioUrl(audio_path);
        console.log('🔊 playAudioUrl result:', ok, 'for', audio_path);
        if (!ok) console.warn('Playback failed (animation will still run)');
        animationMgr.play();
      } catch (e) {
        console.error('Failed to start audio/animation:', e);
      }
    }

    // --- VRMA animation ---
    if (msg.type === 'start_vrma') {
      const {
        animation_url,
        play_once = false,
        crop_start = 0.0,
        crop_end = 0.0,
        lock_position = false,
        track_position = true,
      } = msg;
      await movementController.playVRMA(animation_url, {
        play_once, crop_start, crop_end, lock_position, track_position,
      });
    }

    // --- Mixamo animation ---
    if (msg.type === 'start_mixamo') {
      const { animation_url, play_once = false, lock_position = false, track_position = true } = msg;
      await movementController.playMixamo(animation_url, {
        play_once, lock_position, track_position,
      });
    }

    // --- Webcam ---
    if (msg.type === 'take_picture') {
      await takePictureAndUpload();
    }
  };

})();
