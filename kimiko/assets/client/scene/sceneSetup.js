import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

/**
 * Creates and returns the core Three.js scene objects: renderer, scene, camera, controls.
 * Tweak the defaults below or pass overrides to customize.
 */

const DEFAULTS = {
  // Renderer
  antialias: true,
  alpha: true, // transparent background (for OBS chroma key, etc.)
  shadowMap: true,

  // Camera
  fov: 30,
  near: 0.1,
  far: 50,
  cameraPosition: [0, 1, 0.9],
  controlsTarget: [0, 1.1, 0],

  // Scene
  background: null, // null = transparent, or set to a THREE.Color

  // Lighting
  lights: [
    { type: 'directional', color: 0xffffff, intensity: 1, position: [3, 15, -5] },
    { type: 'ambient', color: 0xffffff, intensity: 2.1 },
  ],

  // Debug helpers (set to true to enable)
  gridHelper: false,
  axesHelper: false,
};

export function createScene(overrides = {}) {
  const opts = { ...DEFAULTS, ...overrides };

  // --- Renderer ---
  const renderer = new THREE.WebGLRenderer({
    antialias: opts.antialias,
    alpha: opts.alpha,
  });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(window.devicePixelRatio);
  if (opts.shadowMap) {
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  }
  document.body.appendChild(renderer.domElement);

  // --- Scene ---
  const scene = new THREE.Scene();
  if (opts.background !== null) {
    scene.background = opts.background instanceof THREE.Color
      ? opts.background
      : new THREE.Color(opts.background);
  }

  // --- Camera ---
  const camera = new THREE.PerspectiveCamera(
    opts.fov,
    window.innerWidth / window.innerHeight,
    opts.near,
    opts.far,
  );
  camera.position.set(...opts.cameraPosition);

  // --- Controls ---
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(...opts.controlsTarget);
  controls.update();

  // --- Lighting ---
  for (const lightDef of opts.lights) {
    let light;
    if (lightDef.type === 'directional') {
      light = new THREE.DirectionalLight(lightDef.color, lightDef.intensity);
      if (lightDef.position) light.position.set(...lightDef.position);
      if (lightDef.castShadow) light.castShadow = true;
    } else if (lightDef.type === 'ambient') {
      light = new THREE.AmbientLight(lightDef.color, lightDef.intensity);
    } else if (lightDef.type === 'point') {
      light = new THREE.PointLight(lightDef.color, lightDef.intensity);
      if (lightDef.position) light.position.set(...lightDef.position);
    }
    if (light) scene.add(light);
  }

  // --- Debug helpers ---
  if (opts.gridHelper) {
    const size = typeof opts.gridHelper === 'number' ? opts.gridHelper : 50;
    scene.add(new THREE.GridHelper(size, size));
  }
  if (opts.axesHelper) {
    const size = typeof opts.axesHelper === 'number' ? opts.axesHelper : 5;
    scene.add(new THREE.AxesHelper(size));
  }

  // --- Resize handler ---
  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  return { renderer, scene, camera, controls };
}
