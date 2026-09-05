import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

/**
 * Loads a single room (environment) GLB into the scene.
 * Shares loader/pattern with objectLoader but applies room-specific tweaks:
 *   - fixDepth: per-mesh depthWrite / polygonOffset to suppress z-fighting
 *     (ported from client/reference/app-RIKOROOM.js)
 * Works automatically in VR — the room lives in the same scene graph as the
 * VR dolly and controllers.
 */

const loader = new GLTFLoader();

export async function loadRoom(scene, config) {
  if (!config || !config.enabled || !config.url) return null;

  try {
    const gltf = await loader.loadAsync(config.url);
    const model = gltf.scene;

    const [px, py, pz] = config.position ?? [0, 0, 0];
    const [rx, ry, rz] = config.rotation ?? [0, 0, 0];
    const s = config.scale ?? [1, 1, 1];
    const [sx, sy, sz] = Array.isArray(s) ? s : [s, s, s];

    model.position.set(px, py, pz);
    model.rotation.set(rx, ry, rz);
    model.scale.set(sx, sy, sz);
    model.name = 'room';

    model.traverse((child) => {
      if (!child.isMesh) return;
      child.castShadow = false;
      child.receiveShadow = true;

      if (config.fixDepth) {
        child.geometry.computeBoundingBox();
        child.geometry.computeBoundingSphere();
        child.geometry.computeVertexNormals();

        if (child.material) {
          child.material.depthWrite = true;
          child.material.depthTest = true;
          child.material.polygonOffset = true;
          child.material.polygonOffsetFactor = -1;
          child.material.polygonOffsetUnits = -1;
        }

        child.updateMatrix();
        child.updateMatrixWorld(true);
      }
    });

    scene.add(model);
    console.log(`🏠 Room loaded: ${config.url}`);
    return model;
  } catch (err) {
    console.error(`Failed to load room from ${config.url}:`, err);
    return null;
  }
}
