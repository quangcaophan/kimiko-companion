import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict

from kimiko.core.logger import get_logger
from kimiko.core.memory.db import MemoryDB
from kimiko.core.avatar.reactions import build_click_reaction

logger = get_logger("server")


# ---------------------------------------------------------------------------
# Pydantic Schemas for Strict Request Validation & Error Handling
# ---------------------------------------------------------------------------
class TalkRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
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
    model_config = ConfigDict(populate_by_name=True)
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

    @property
    def has_active_clients(self) -> bool:
        """Return True if at least one WebSocket client is connected."""
        return len(self.active_connections) > 0

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        client_info = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
        async with self._lock:
            self.active_connections.append(websocket)
            total = len(self.active_connections)
        logger.info(f"WebSocket client connected from {client_info}. Total active: {total}")

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            total = len(self.active_connections)
        logger.info(f"WebSocket client disconnected. Remaining active: {total}")

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Asynchronously broadcast JSON payload to all active WebSocket clients."""
        msg_type = message.get("type", "unknown")
        async with self._lock:
            dead_connections = []
            logger.debug(f"Broadcasting '{msg_type}' to {len(self.active_connections)} client(s)...")
            for connection in self.active_connections:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send to client ({e}). Marking dead connection.")
                    dead_connections.append(connection)

            for dead in dead_connections:
                if dead in self.active_connections:
                    self.active_connections.remove(dead)

    def broadcast_sync(self, message: Dict[str, Any]) -> None:
        """Synchronously broadcast from background threads to asyncio loop."""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self.loop)
        else:
            logger.warning("No running event loop available for synchronous WebSocket broadcast.")


ws_manager = ConnectionManager()

# Module-level MemoryDB reference — set from main.py via set_db() to avoid duplicate instances
_db: Optional['MemoryDB'] = None


def set_db(db_instance: 'MemoryDB') -> None:
    """Inject the shared MemoryDB instance from the orchestrator."""
    global _db
    _db = db_instance
    logger.info("Shared MemoryDB instance injected into server module.")


def _get_db() -> 'MemoryDB':
    """Get the shared MemoryDB, creating a fallback if not injected."""
    global _db
    if _db is None:
        logger.warning("No shared MemoryDB injected — creating standalone fallback instance.")
        _db = MemoryDB()
    return _db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    ws_manager.loop = asyncio.get_running_loop()
    logger.info("=" * 60)
    logger.info("Kimiko FastAPI Server Started on port 8001")
    logger.info("WebSocket URL: ws://localhost:8001/ws")
    logger.info("HTTP UI URL:   http://localhost:8001")
    logger.info("=" * 60)
    yield
    logger.info("Kimiko FastAPI Server shutting down.")


# ---------------------------------------------------------------------------
# Application Initialization
# ---------------------------------------------------------------------------
app = FastAPI(title="Kimiko Companion Server", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
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
            logger.debug(f"Received WebSocket message from client: {data[:60]}")
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Unexpected WebSocket client error: {e}")
        await ws_manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# REST Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check() -> Dict[str, Any]:
    return {"status": "ok", "timestamp": time.time(), "clients": len(ws_manager.active_connections)}


@app.post("/talk")
async def talk_endpoint(payload: TalkRequest) -> Dict[str, Any]:
    """Broadcast an audio line with subtitles and facial expression."""
    logger.info(f"Endpoint /talk: {payload.audio_text[:50]!r} (dur={payload.audio_duration}s)")
    msg = {
        "type": "start_animation",
        "audio_path": payload.audio_path,
        "expression": payload.expression,
        "audio_text": payload.audio_text,
        "audio_duration": payload.audio_duration or 1.0,
        "audio_duraction": payload.audio_duration or 1.0,
    }
    await ws_manager.broadcast(msg)
    return {"status": "success", "broadcast": msg}


@app.post("/animate")
async def animate_endpoint(payload: AnimateRequest) -> Dict[str, Any]:
    """Broadcast an avatar body animation (Mixamo FBX or VRMA)."""
    logger.info(f"Endpoint /animate: {payload.animation_url}")
    msg = payload.model_dump()
    await ws_manager.broadcast(msg)
    return {"status": "success", "broadcast": msg}


@app.post("/animate_and_talk")
async def animate_and_talk_endpoint(payload: AnimateAndTalkRequest, bg: BackgroundTasks) -> Dict[str, Any]:
    """Broadcast animation and voice line sequentially or with delay."""
    logger.info(f"Endpoint /animate_and_talk: anim={payload.animation_url}, talk={payload.audio_text[:40]!r}")
    talk_msg = {
        "type": "start_animation",
        "audio_path": payload.audio_path,
        "expression": payload.expression,
        "audio_text": payload.audio_text,
        "audio_duration": payload.audio_duration or 1.0,
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
    logger.info(f"Endpoint /set_state: {payload.state}")
    msg = {"type": "set_state", "state": payload.state}
    await ws_manager.broadcast(msg)
    return {"status": "success", "state": payload.state}


@app.post("/walk_to")
async def walk_to_endpoint(payload: MoveRequest) -> Dict[str, Any]:
    logger.info(f"Endpoint /walk_to: ({payload.x}, {payload.y}, {payload.z})")
    msg = {"type": "walk_to", "x": payload.x, "y": payload.y, "z": payload.z, "speed": payload.speed}
    await ws_manager.broadcast(msg)
    return {"status": "success"}


@app.post("/teleport_to")
async def teleport_to_endpoint(payload: MoveRequest) -> Dict[str, Any]:
    logger.info(f"Endpoint /teleport_to: ({payload.x}, {payload.y}, {payload.z})")
    msg = {"type": "teleport_to", "x": payload.x, "y": payload.y, "z": payload.z}
    await ws_manager.broadcast(msg)
    return {"status": "success"}


@app.post("/send_click_interaction")
async def send_click_interaction_endpoint(payload: ClickInteractionRequest, bg: BackgroundTasks) -> Dict[str, Any]:
    """Process physical click/touch interaction on avatar body."""
    logger.info(f"Endpoint /send_click_interaction: region={payload.region}, bone={payload.bone}")
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
        db = _get_db()
        db.insert_pending_action(payload.region, payload.bone, time.time())

        return {"status": "success", "reaction": reaction}
    except Exception as e:
        logger.error(f"Error processing click interaction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/pop_pending_actions")
def pop_pending_actions_endpoint() -> List[Dict[str, Any]]:
    """Atomically fetch and consume pending click actions from database."""
    try:
        db = _get_db()
        actions = db.pop_pending_actions()
        if actions:
            logger.info(f"Popped {len(actions)} pending click action(s) from DB.")
        return actions
    except Exception as e:
        logger.error(f"Database error popping pending actions: {e}", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Web UI Chat & Audio Integration
# ---------------------------------------------------------------------------
class MessageRequest(BaseModel):
    message_text: str = Field(..., description="User input message text from Web UI")


_chat_handler: Optional[Callable[[str], Any]] = None
_voice_handler: Optional[Callable[[str], Any]] = None


def register_chat_handler(handler: Callable[[str], Any]) -> None:
    """Register the Kimiko conversational turn handler for Web UI chat messages."""
    global _chat_handler
    _chat_handler = handler
    logger.info("Registered chat turn handler with FastAPI server.")


def register_voice_handler(handler: Callable[[str], Any]) -> None:
    """Register handler for user audio uploads from Web UI mic."""
    global _voice_handler
    _voice_handler = handler
    logger.info("Registered voice audio upload handler with FastAPI server.")


@app.post("/send_message")
async def send_message_endpoint(payload: MessageRequest, bg: BackgroundTasks) -> Dict[str, Any]:
    """Receive text message submitted from the Web UI input box and process turn."""
    msg = payload.message_text.strip()
    logger.info(f"Endpoint /send_message received from Web UI: {msg!r}")
    if not msg:
        return {"status": "error", "message": "Empty message"}

    if _chat_handler is None:
        logger.warning("No chat handler registered to process /send_message.")
        return {"status": "error", "message": "Companion backend not ready"}

    bg.add_task(_chat_handler, msg)
    return {"status": "success", "message": f"Processing message: {msg[:30]}"}


@app.post("/upload-audio/")
async def upload_audio_endpoint(file: UploadFile, bg: BackgroundTasks) -> Dict[str, Any]:
    """Receive recorded audio blob from Web client microphone button."""
    try:
        temp_dir = Path("kimiko/assets/client/audio/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)
        filename = file.filename or "recording.webm"
        temp_path = temp_dir / f"web_upload_{int(time.time())}_{filename}"
        content = await file.read()
        with open(temp_path, "wb") as f:
            f.write(content)
        logger.info(f"Received web audio upload: {temp_path} ({len(content)} bytes)")

        if _voice_handler:
            bg.add_task(_voice_handler, str(temp_path))
        return {"status": "success", "message": "Audio received and processing"}
    except Exception as e:
        logger.error(f"Error handling audio upload: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Static Web Client Mounting
# ---------------------------------------------------------------------------
_server_dir = Path(__file__).resolve().parent
CLIENT_DIR = _server_dir.parent.parent / "assets" / "client"
if not CLIENT_DIR.is_dir():
    CLIENT_DIR = Path("kimiko/assets/client").resolve()

if CLIENT_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(CLIENT_DIR), html=True), name="client")
    logger.info(f"Mounted Web 3D Client from: {CLIENT_DIR.resolve()}")
else:
    logger.warning(f"Client directory {CLIENT_DIR} not found. Static files not mounted.")
