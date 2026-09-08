import asyncio
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from kimiko.core.memory.db import MemoryDB
from kimiko.core.avatar.reactions import build_click_reaction


# ---------------------------------------------------------------------------
# Pydantic Schemas for Strict Request Validation & Error Handling
# ---------------------------------------------------------------------------
class TalkRequest(BaseModel):
    audio_path: str = Field(..., description="Path or URL to the audio file")
    expression: str = Field("neutral", description="Facial expression")
    audio_text: str = Field("", description="Subtitles or transcript")
    audio_duration: Optional[float] = Field(None, alias="audio_duraction", description="Duration in seconds")


class AnimateRequest(BaseModel):
    animation_url: str = Field(..., description="Path to .fbx or .vrma animation file")
    type: str = Field("start_mixamo", description="'start_mixamo' or 'start_vrma'")
    play_once: bool = Field(False, description="Play once or loop")
    crop_start: float = Field(0.0, description="Crop start in seconds")
    crop_end: float = Field(0.0, description="Crop end in seconds")
    lock_position: bool = Field(False, description="Lock model root bone")
    track_position: bool = Field(True, description="Track root bone position")


class AnimateAndTalkRequest(BaseModel):
    audio_path: str
    animation_url: str
    expression: str = "relaxed"
    audio_text: str = ""
    audio_duration: Optional[float] = Field(None, alias="audio_duraction")
    delay: float = 0.0


class StateRequest(BaseModel):
    state: str = Field(..., description="One of: 'idle', 'listening', 'thinking', 'talking'")


class ClickInteractionRequest(BaseModel):
    region: str = Field(..., description="Hit body region")
    bone: str = Field("", description="Hit VRM bone name")


class MoveRequest(BaseModel):
    x: float
    y: float
    z: float
    speed: Optional[float] = None


# ---------------------------------------------------------------------------
# WebSocket Connection Manager with Dead Connection Pruning
# ---------------------------------------------------------------------------
class ConnectionManager:
    """Thread-safe WebSocket manager with dead-socket pruning and sync/async broadcast."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        print(f"[WebSocket] Client connected. Total active: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        print(f"[WebSocket] Client disconnected. Remaining: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Asynchronously broadcast JSON payload to all active WebSocket clients."""
        async with self._lock:
            dead_connections = []
            for connection in self.active_connections:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    print(f"[WebSocket] Failed to send to client: {e}. Marking for cleanup.")
                    dead_connections.append(connection)

            for dead in dead_connections:
                if dead in self.active_connections:
                    self.active_connections.remove(dead)

    def broadcast_sync(self, message: Dict[str, Any]) -> None:
        """Synchronously broadcast from background threads to asyncio loop."""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self.loop)
        else:
            print("[WebSocket] No running event loop for synchronous broadcast.")


# ---------------------------------------------------------------------------
# Application Initialization
# ---------------------------------------------------------------------------
app = FastAPI(title="Kimiko Companion Server", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ws_manager = ConnectionManager()
db = MemoryDB()


@app.on_event("startup")
async def on_startup() -> None:
    ws_manager.loop = asyncio.get_running_loop()
    print("=" * 60)
    print("Kimiko FastAPI Server Started on port 8001")
    print("WebSocket URL: ws://localhost:8001/ws")
    print("HTTP UI URL:   http://localhost:8001")
    print("=" * 60)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    print(f"[Server] Unhandled exception on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": str(exc), "path": request.url.path}
    )


# ---------------------------------------------------------------------------
# WebSocket Endpoint
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep receiving client packets / pings
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as e:
        print(f"[WebSocket] Unexpected client connection error: {e}")
        await ws_manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# REST Endpoints (Adhering to contract.md)
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check() -> Dict[str, Any]:
    return {"status": "ok", "timestamp": time.time(), "clients": len(ws_manager.active_connections)}


@app.post("/talk")
async def talk_endpoint(payload: TalkRequest) -> Dict[str, Any]:
    """Broadcast an audio line with subtitles and facial expression."""
    msg = {
        "type": "start_animation",
        "audio_path": payload.audio_path,
        "expression": payload.expression,
        "audio_text": payload.audio_text,
        "audio_duraction": payload.audio_duration or 1.0,
    }
    await ws_manager.broadcast(msg)
    return {"status": "success", "broadcast": msg}


@app.post("/animate")
async def animate_endpoint(payload: AnimateRequest) -> Dict[str, Any]:
    """Broadcast an avatar body animation (Mixamo FBX or VRMA)."""
    msg = payload.dict()
    await ws_manager.broadcast(msg)
    return {"status": "success", "broadcast": msg}


@app.post("/animate_and_talk")
async def animate_and_talk_endpoint(payload: AnimateAndTalkRequest, bg: BackgroundTasks) -> Dict[str, Any]:
    """Broadcast animation and voice line sequentially or with delay."""
    talk_msg = {
        "type": "start_animation",
        "audio_path": payload.audio_path,
        "expression": payload.expression,
        "audio_text": payload.audio_text,
        "audio_duraction": payload.audio_duration or 1.0,
    }
    anim_msg = {
        "type": "start_mixamo" if payload.animation_url.endswith(".fbx") else "start_vrma",
        "animation_url": payload.animation_url,
        "play_once": True,
        "crop_start": 0.0,
        "crop_end": 0.0,
        "lock_position": False,
        "track_position": True,
    }

    await ws_manager.broadcast(anim_msg)
    if payload.delay > 0:
        async def delayed_talk():
            await asyncio.sleep(payload.delay)
            await ws_manager.broadcast(talk_msg)
        bg.add_task(delayed_talk)
    else:
        await ws_manager.broadcast(talk_msg)

    return {"status": "success"}


@app.post("/set_state")
async def set_state_endpoint(payload: StateRequest) -> Dict[str, Any]:
    """Change Kimiko's interactive state: 'idle', 'listening', 'thinking', 'talking'."""
    msg = {"type": "set_state", "state": payload.state}
    await ws_manager.broadcast(msg)
    return {"status": "success", "state": payload.state}


@app.post("/walk_to")
async def walk_to_endpoint(payload: MoveRequest) -> Dict[str, Any]:
    msg = {"type": "walk_to", "x": payload.x, "y": payload.y, "z": payload.z, "speed": payload.speed}
    await ws_manager.broadcast(msg)
    return {"status": "success"}


@app.post("/teleport_to")
async def teleport_to_endpoint(payload: MoveRequest) -> Dict[str, Any]:
    msg = {"type": "teleport_to", "x": payload.x, "y": payload.y, "z": payload.z}
    await ws_manager.broadcast(msg)
    return {"status": "success"}


@app.post("/send_click_interaction")
async def send_click_interaction_endpoint(payload: ClickInteractionRequest, bg: BackgroundTasks) -> Dict[str, Any]:
    """Process physical click/touch interaction on avatar body."""
    try:
        reaction = build_click_reaction(payload.region, payload.bone)
        
        # 1. Broadcast immediate sound & reaction animation
        await ws_manager.broadcast(reaction["sound"])
        await ws_manager.broadcast(reaction["animation"])

        # 2. Schedule delayed return to idle
        idle_delay = reaction.get("idle_delay", 2.0)
        idle_payload = reaction.get("idle")

        if idle_payload:
            async def return_to_idle():
                await asyncio.sleep(idle_delay)
                await ws_manager.broadcast(idle_payload)
            bg.add_task(return_to_idle)

        # 3. Store pending action in SQLite for conversation context
        db.insert_pending_action(payload.region, payload.bone, time.time())

        return {"status": "success", "reaction": reaction}
    except Exception as e:
        print(f"[Server.send_click_interaction] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/pop_pending_actions")
def pop_pending_actions_endpoint() -> List[Dict[str, Any]]:
    """Atomically fetch and consume pending click actions from database."""
    try:
        return db.pop_pending_actions()
    except Exception as e:
        print(f"[Server.pop_pending_actions] Database query error: {e}")
        return []


# ---------------------------------------------------------------------------
# Static Web Client Mounting
# ---------------------------------------------------------------------------
_server_dir = Path(__file__).resolve().parent
CLIENT_DIR = _server_dir.parent.parent / "assets" / "client"
if not CLIENT_DIR.is_dir():
    CLIENT_DIR = Path("kimiko/assets/client").resolve()

if CLIENT_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(CLIENT_DIR), html=True), name="client")
    print(f"[StaticFiles] Mounted Web 3D Client from: {CLIENT_DIR.resolve()}")
else:
    print(f"[StaticFiles] Warning: Client directory {CLIENT_DIR} not found. Static files not mounted.")

