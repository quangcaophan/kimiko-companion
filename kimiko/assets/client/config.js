const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:';
const host = typeof window !== 'undefined' && window.location.host ? window.location.host : 'localhost:8001';
const origin = typeof window !== 'undefined' && window.location.origin ? window.location.origin : 'http://localhost:8001';

export const VRM_PATH = "./models/Kimiko1.vrm";
export const WS_URL = `${isHttps ? 'wss:' : 'ws:'}//${host}/ws`;
export const HTTP_URL = origin;

export const MOUTH_THRESHOLD = 5;

// VR Configuration
export const VR_CONFIG = {
  // Starting position of the VR dolly rig [x, y, z].
  // Y offset lowers/raises virtual eye level; Z is distance from avatar.
  dollyPosition: [0, 0.13, 0.8],

  // Proximity touch threshold (meters) - how close hand must be to trigger touch
  touchRadius: 0.09,

  // Extended range when trigger is pressed (meters)
  triggerTouchRadius: 0.25,

  // Cooldown between touch interactions per hand (ms)
  touchCooldown: 2500,

  // Haptic feedback
  hapticIntensity: 0.8,
  hapticDuration: 150,
};

