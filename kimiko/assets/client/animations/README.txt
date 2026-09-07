ANIMATIONS
==========

These are what <emote:...> tags turn into. When she writes <emote:wave>, the
word is matched against the names below and the closest one plays.


WHICH FOLDERS ARE ACTUALLY SCANNED
----------------------------------
Only the top level of three folders, set in ANIMATION_SOURCES in
server/config.py:

  vrma/     *.vrma   hand-made, generally better quality  (searched first)
  vrma_xr/  *.vrma
  mixamo/   *.fbx                                          (searched last)

Earlier folders win when two contain the same name.

SUBFOLDERS ARE NOT SCANNED. `mixamo/Gestures Pack Basic/` and
`mixamo/female_locomotion_pack/` are spare parts, not part of the pool.


ADDING AN ANIMATION
-------------------
1. Drop the .fbx (Mixamo) or .vrma file into `mixamo/` or `vrma/` itself,
   not into a subfolder.
2. Name it after what it looks like — the FILENAME is what gets matched, so
   "shrug.fbx" is found by <emote:shrug> and "anim_047.fbx" is found by
   nothing.
3. Either restart, or say "/reload" to her — it re-scans without a restart.

Spaces in filenames are fine ("Cross Punch.fbx" works).

Mixamo files must be downloaded WITHOUT skin, in FBX Binary. Get them free at
https://mixamo.com.


IF AN ANIMATION NEVER PLAYS
---------------------------
Press F12 in the browser and look at the Console tab. A 404 there names the
file it could not find. That is almost always the whole story: a typo, or a
file sitting in a subfolder where nothing looks for it.
