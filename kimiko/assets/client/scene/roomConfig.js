/**
 * Room (environment) configuration.
 *
 * One room at a time. Set `enabled: false` to run without any room.
 * position / rotation / scale are [x, y, z]. Rotation is in radians.
 *
 * `fixDepth`: enables depthWrite/depthTest + polygonOffset on every mesh.
 * Useful for rooms that show z-fighting artifacts (e.g. KimikoRoomFixed).
 */

export const ROOM_CONFIG = {
  enabled: false,


  // --- Alternatives (copy values over `url`/transform above to switch) ---
  // Japanese classroom:
    url: './backgrounds/glb/japanese_classroom.glb',
    position: [2, -0.04, -4], rotation: [0, 2, 0], scale: [0.7, 0.7, 0.7],
    fixDepth: false,

};
