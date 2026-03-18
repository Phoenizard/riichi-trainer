"""
Mortal AI Agent — Triple mode: libriichi (local) / MJAPI (online) / Docker (local)

Usage:
  # Local libriichi mode (recommended)
  agent = MortalAgent.create_libriichi(player_id=0, model_path="model/model.pth")

  # Online mode (MJAPI)
  agent = MortalAgent.create_mjapi(player_id=0, api_url="https://mjai.xxx.org")

  # Local Docker mode
  agent = MortalAgent.create_docker(player_id=0, model_dir="/path/to/model")

  # Use in game
  agent.start_game()
  agent.start_round(mjai_start_kyoku_event)
  action, analysis = agent.react(mjai_event)
"""

from __future__ import annotations
import json
import subprocess
import logging
import requests
import random
import string
from typing import Optional
from dataclasses import dataclass, field

from game.engine import Action, ActionType, RoundState, PlayerState
from game.tiles import normalize, sort_tiles

logger = logging.getLogger(__name__)

# Red five translation: our internal "0m" ↔ mjai "5mr"
_TO_MJAI = {"0m": "5mr", "0p": "5pr", "0s": "5sr"}
_FROM_MJAI = {"5mr": "0m", "5pr": "0p", "5sr": "0s"}

def _tile_to_mjai(tile: str) -> str:
    return _TO_MJAI.get(tile, tile)

def _tile_from_mjai(tile: str) -> str:
    return _FROM_MJAI.get(tile, tile)

def _tiles_to_mjai(tiles: list[str]) -> list[str]:
    return [_tile_to_mjai(t) for t in tiles]

def _tiles_from_mjai(tiles: list[str]) -> list[str]:
    return [_tile_from_mjai(t) for t in tiles]


# ---------------------------------------------------------------------------
# Analysis result from Mortal
# ---------------------------------------------------------------------------

@dataclass
class MortalAnalysis:
    """Parsed analysis from Mortal's meta output."""
    recommended_action: str = ""       # "dahai", "none", "reach", "hora", etc.
    recommended_tile: str = ""         # tile to discard (if dahai)
    q_values: list[float] = field(default_factory=list)  # raw q-values (ACTION_SPACE)
    mask_bits: int = 0
    is_greedy: bool = True
    shanten: int = -1
    eval_time_ns: int = 0

    # Derived: candidate tiles with scores
    candidates: list[dict] = field(default_factory=list)  # [{tile, score, rank}]


# ---------------------------------------------------------------------------
# Tile index mapping for q_values
# ---------------------------------------------------------------------------

# Mortal ACTION_SPACE: 37 actions for 4p
# Index 0-33: discard tile (corresponding to 34 tile types)
# Index 34: reach (riichi)
# Index 35: chi/pon/kan
# Index 36: hora (tsumo/ron)

TILE_INDEX_ORDER = [
    "1m","2m","3m","4m","5m","6m","7m","8m","9m",
    "1p","2p","3p","4p","5p","6p","7p","8p","9p",
    "1s","2s","3s","4s","5s","6s","7s","8s","9s",
    "E","S","W","N","P","F","C",
]

def parse_mortal_meta(reaction: dict) -> MortalAnalysis:
    """Parse Mortal's reaction with meta into MortalAnalysis."""
    analysis = MortalAnalysis()
    analysis.recommended_action = reaction.get("type", "")
    analysis.recommended_tile = _tile_from_mjai(reaction.get("pai", ""))

    meta = reaction.get("meta", {})
    if not meta:
        return analysis

    analysis.q_values = meta.get("q_values", [])
    analysis.mask_bits = meta.get("mask_bits", 0)
    analysis.is_greedy = meta.get("is_greedy", True)
    analysis.shanten = meta.get("shanten", -1)
    analysis.eval_time_ns = meta.get("eval_time_ns", 0)

    # Build candidate list from q_values
    if analysis.q_values and len(analysis.q_values) >= 34:
        candidates = []
        for i, tile in enumerate(TILE_INDEX_ORDER):
            qv = analysis.q_values[i]
            if qv > -10:  # masked actions have -inf
                candidates.append({"tile": tile, "score": qv, "rank": 0})

        # Sort by score descending
        candidates.sort(key=lambda x: x["score"], reverse=True)
        for rank, c in enumerate(candidates):
            c["rank"] = rank + 1
        analysis.candidates = candidates

    return analysis


# ---------------------------------------------------------------------------
# MJAPI Client (online mode)
# ---------------------------------------------------------------------------

class MjapiClient:
    """MJAPI API client for online Mortal access."""

    def __init__(self, base_url: str, timeout: float = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {}
        self.token = None
        self.username = ""
        self.secret = ""
        self.seq = -1
        self.bound = 256

    def register_and_login(self, name: str = "") -> bool:
        """Register a new user and login."""
        if not name:
            name = "rt_" + "".join(random.choices(string.ascii_lowercase, k=6))
        self.username = name

        try:
            # Register
            resp = requests.post(
                f"{self.base_url}/user/register",
                json={"name": name}, timeout=self.timeout
            )
            if not resp.ok:
                logger.error(f"Register failed: {resp.status_code} {resp.text}")
                return False
            data = resp.json()
            self.secret = data.get("secret", "")

            # Login
            resp = requests.post(
                f"{self.base_url}/user/login",
                json={"name": name, "secret": self.secret},
                timeout=self.timeout
            )
            if not resp.ok:
                logger.error(f"Login failed: {resp.status_code} {resp.text}")
                return False
            data = resp.json()
            self.token = data.get("id", "")
            self.headers["Authorization"] = f"Bearer {self.token}"
            logger.info(f"MJAPI logged in as {name}")
            return True

        except Exception as e:
            logger.error(f"MJAPI connection error: {e}")
            return False

    def list_models(self) -> list[str]:
        """Get available model names."""
        resp = requests.get(f"{self.base_url}/mjai/list",
                           headers=self.headers, timeout=self.timeout)
        if resp.ok:
            return resp.json().get("models", [])
        return []

    def start_bot(self, seat: int, model: str = "baseline") -> bool:
        """Start a bot session."""
        self.seq = -1
        resp = requests.post(
            f"{self.base_url}/mjai/start",
            json={"id": seat, "bound": self.bound, "model": model},
            headers=self.headers, timeout=self.timeout
        )
        return resp.ok

    def act(self, mjai_event: dict) -> Optional[dict]:
        """Send one mjai event, get reaction (if any)."""
        self.seq = (self.seq + 1) % self.bound
        resp = requests.post(
            f"{self.base_url}/mjai/act",
            json={"seq": self.seq, "data": mjai_event},
            headers=self.headers, timeout=self.timeout
        )
        if resp.ok and resp.content:
            data = resp.json()
            return data.get("act", data)
        return None

    def batch(self, events: list[dict]) -> Optional[dict]:
        """Send batch of mjai events."""
        batch_data = []
        for msg in events:
            self.seq = (self.seq + 1) % self.bound
            batch_data.append({"seq": self.seq, "data": msg})

        resp = requests.post(
            f"{self.base_url}/mjai/batch",
            json=batch_data,
            headers=self.headers, timeout=self.timeout
        )
        if resp.ok and resp.content:
            data = resp.json()
            return data.get("act", data)
        return None

    def stop_bot(self):
        """Stop current bot session."""
        requests.post(f"{self.base_url}/mjai/stop",
                     headers=self.headers, timeout=self.timeout)

    def logout(self):
        requests.post(f"{self.base_url}/user/logout",
                     headers=self.headers, timeout=self.timeout)


# ---------------------------------------------------------------------------
# Local libriichi Client (recommended local mode)
# ---------------------------------------------------------------------------

class LocalLibrichiClient:
    """Run Mortal inference locally via compiled libriichi + PyTorch model."""

    def __init__(self, model_path: str, player_id: int):
        import libriichi
        from ai.mortal_engine import get_engine

        self.player_id = player_id
        self._engine = get_engine(model_path)
        self.bot = libriichi.mjai.Bot(self._engine, player_id)
        logger.info(f"Local Mortal loaded for player {player_id} "
                    f"(version={self._engine.version}, device={self._engine.device})")

    def react(self, mjai_event: dict) -> Optional[dict]:
        """Feed mjai event to bot, return reaction or None."""
        result = self.bot.react(json.dumps(mjai_event))
        if result:
            return json.loads(result)
        return None


# ---------------------------------------------------------------------------
# Docker Client (local mode)
# ---------------------------------------------------------------------------

class DockerMortalClient:
    """Run Mortal inference via Docker container (stdin/stdout mjai protocol)."""

    def __init__(self, model_dir: str, player_id: int, image: str = "mortal:latest"):
        self.model_dir = model_dir
        self.player_id = player_id
        self.image = image
        self.process: Optional[subprocess.Popen] = None

    def start(self):
        """Start Mortal Docker container."""
        cmd = [
            "docker", "run", "-i", "--rm",
            "-v", f"{self.model_dir}:/mnt",
            self.image,
            str(self.player_id),
        ]
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        logger.info(f"Mortal Docker started for player {self.player_id}")

    def send_and_receive(self, mjai_event: dict) -> Optional[dict]:
        """Send mjai event via stdin, read response from stdout."""
        if not self.process:
            raise RuntimeError("Docker process not running")

        line = json.dumps(mjai_event) + "\n"
        self.process.stdin.write(line)
        self.process.stdin.flush()

        # Read response (Mortal outputs one JSON per actionable event)
        response_line = self.process.stdout.readline()
        if response_line:
            return json.loads(response_line.strip())
        return None

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None


# ---------------------------------------------------------------------------
# Unified MortalAgent
# ---------------------------------------------------------------------------

class MortalAgent:
    """Unified Mortal AI agent for our game engine.

    Supports three backends:
      - "local": Local libriichi + PyTorch (recommended)
      - "mjapi": Online MJAPI service
      - "docker": Local Docker container
    """

    def __init__(self, player_id: int, mode: str = "local"):
        self.player_id = player_id
        self.mode = mode
        self.name = f"Mortal-{player_id}"

        # Backend clients
        self._local: Optional[LocalLibrichiClient] = None
        self._mjapi: Optional[MjapiClient] = None
        self._docker: Optional[DockerMortalClient] = None

        # State
        self._event_buffer: list[dict] = []
        self._last_analysis: Optional[MortalAnalysis] = None
        self._model_name: str = "baseline"
        self._game_started: bool = False

    # --- Factory methods ---

    @classmethod
    def create_libriichi(cls, player_id: int, model_path: str) -> "MortalAgent":
        """Create agent using local libriichi + PyTorch model."""
        agent = cls(player_id, mode="local")
        agent._local = LocalLibrichiClient(model_path, player_id)
        return agent

    @classmethod
    def create_mjapi(cls, player_id: int, api_url: str,
                     model: str = "baseline") -> "MortalAgent":
        """Create agent using MJAPI online service."""
        agent = cls(player_id, mode="mjapi")
        agent._mjapi = MjapiClient(api_url)
        agent._model_name = model
        if not agent._mjapi.register_and_login():
            raise ConnectionError(f"Cannot connect to MJAPI at {api_url}")
        models = agent._mjapi.list_models()
        logger.info(f"MJAPI models available: {models}")
        if model not in models and models:
            agent._model_name = models[0]
        return agent

    @classmethod
    def create_docker(cls, player_id: int, model_dir: str,
                      image: str = "mortal:latest") -> "MortalAgent":
        """Create agent using local Docker Mortal."""
        agent = cls(player_id, mode="docker")
        agent._docker = DockerMortalClient(model_dir, player_id, image)
        agent._docker.start()
        return agent

    # --- Game lifecycle ---

    def start_game(self):
        """Initialize for a new game."""
        if self.mode == "mjapi" and self._mjapi:
            self._mjapi.start_bot(self.player_id, self._model_name)
        self._event_buffer = []
        self._send_event({"type": "start_game", "id": self.player_id,
                          "names": ["player", "ai1", "ai2", "ai3"]})

    def end_game(self):
        """Cleanup after game ends."""
        if self.mode == "local":
            pass  # No cleanup needed for libriichi
        elif self.mode == "mjapi" and self._mjapi:
            self._mjapi.stop_bot()
        elif self.mode == "docker" and self._docker:
            self._docker.stop()

    # --- Core interface for GameEngine ---

    def choose_action(
        self,
        player_id: int,
        game_state: RoundState,
        available_actions: list[Action],
    ) -> Action:
        """Choose action — called by GameEngine.

        For Mortal-controlled seats, we use the last reaction from Mortal.
        For the coach seat, we query Mortal and return its recommendation
        while letting the human decide.
        """
        # Use the last Mortal reaction to pick from available actions
        if self._last_analysis and self._last_analysis.recommended_action:
            return self._match_mortal_to_engine(self._last_analysis, available_actions)

        # Fallback: first available action
        return available_actions[0]

    def on_event(self, event: dict) -> None:
        """Receive game event from engine — forward to Mortal."""
        # Auto-send start_game before first round
        if not self._game_started and event.get("type") == "start_round":
            self._game_started = True
            self._send_event({"type": "start_game", "names": ["P0", "P1", "P2", "P3"]})

        # Translate engine event to mjai format and send
        mjai_event = self._engine_event_to_mjai(event)
        if mjai_event:
            reaction = self._send_event(mjai_event)
            if reaction and isinstance(reaction, dict):
                self._last_analysis = parse_mortal_meta(reaction)

    def get_analysis(self) -> Optional[MortalAnalysis]:
        """Get the last analysis result."""
        return self._last_analysis

    # --- Send to backend ---

    def _send_event(self, mjai_event: dict) -> Optional[dict]:
        """Send mjai event to the appropriate backend."""
        if self.mode == "local" and self._local:
            return self._local.react(mjai_event)
        elif self.mode == "mjapi" and self._mjapi:
            return self._mjapi.act(mjai_event)
        elif self.mode == "docker" and self._docker:
            return self._docker.send_and_receive(mjai_event)
        return None

    # --- Translation helpers ---

    def _engine_event_to_mjai(self, event: dict) -> Optional[dict]:
        """Convert our engine events to mjai format."""
        etype = event.get("type", "")

        if etype == "start_round":
            tehais = []
            for i in range(4):
                if i == self.player_id:
                    tehais.append(_tiles_to_mjai(event["tehais"][i]))
                else:
                    tehais.append(["?"] * 13)
            return {
                "type": "start_kyoku",
                "bakaze": event["round_wind"],
                "kyoku": event["round_number"] + 1,
                "honba": event["honba"],
                "kyotaku": event.get("riichi_sticks", 0),
                "oya": event["dealer"],
                "dora_marker": _tile_to_mjai(event["dora_indicators"][0])
                    if event.get("dora_indicators") else "",
                "scores": event["scores"],
                "tehais": tehais,
            }

        if etype == "draw":
            player = event["player"]
            tile = event["tile"]
            if player == self.player_id:
                return {"type": "tsumo", "actor": player, "pai": _tile_to_mjai(tile)}
            else:
                return {"type": "tsumo", "actor": player, "pai": "?"}

        if etype == "discard":
            return {
                "type": "dahai",
                "actor": event["player"],
                "pai": _tile_to_mjai(event["tile"]),
                "tsumogiri": event.get("tsumogiri", False),
            }

        if etype in ("chi", "pon"):
            return {
                "type": etype,
                "actor": event["player"],
                "target": event.get("target", 0),
                "pai": _tile_to_mjai(event.get("tile", "")),
                "consumed": _tiles_to_mjai(event.get("consumed", [])),
            }

        if etype == "kan":
            consumed = event.get("consumed", [])
            target = event.get("target", event["player"])
            actor = event["player"]
            if target == actor and len(consumed) >= 4:
                # Ankan: consumed has all 4 tiles, no pai/target
                return {
                    "type": "ankan",
                    "actor": actor,
                    "consumed": _tiles_to_mjai(consumed[:4]),
                }
            elif target == actor:
                # Kakan: pai is the added tile, consumed is 3 tiles from pon
                return {
                    "type": "kakan",
                    "actor": actor,
                    "pai": _tile_to_mjai(event.get("tile", "")),
                    "consumed": _tiles_to_mjai(consumed[:3]),
                }
            else:
                # Daiminkan
                return {
                    "type": "daiminkan",
                    "actor": actor,
                    "target": target,
                    "pai": _tile_to_mjai(event.get("tile", "")),
                    "consumed": _tiles_to_mjai(consumed[:3]),
                }

        if etype == "dora":
            return {"type": "dora", "dora_marker": _tile_to_mjai(event["dora_marker"])}

        if etype == "reach":
            return {"type": "reach", "actor": event["player"]}

        if etype == "reach_accepted":
            return {"type": "reach_accepted", "actor": event["player"]}

        if etype in ("tsumo", "ron"):
            return {"type": "hora", "actor": event["player"],
                    "target": event.get("from", event["player"]),
                    "pai": _tile_to_mjai(event.get("tile", ""))}

        if etype == "ryukyoku":
            return {"type": "ryukyoku"}

        if etype == "end_kyoku":
            return {"type": "end_kyoku"}

        return None

    def send_start_kyoku(self, state: RoundState):
        """Send start_kyoku event to Mortal."""
        # Build tehais: our seat sees real tiles, others see "?"
        tehais = []
        for i in range(4):
            if i == self.player_id:
                tehais.append(_tiles_to_mjai(list(state.players[i].hand)))
            else:
                tehais.append(["?"] * 13)

        event = {
            "type": "start_kyoku",
            "bakaze": state.round_wind,
            "dora_marker": _tile_to_mjai(
                state.dora_indicators[0] if state.dora_indicators else ""),
            "kyoku": state.round_number + 1,
            "honba": state.honba,
            "kyotaku": state.riichi_sticks,
            "oya": state.dealer,
            "scores": state.scores,
            "tehais": tehais,
        }
        self._send_event(event)

    def _match_mortal_to_engine(self, analysis: MortalAnalysis,
                                available: list[Action]) -> Action:
        """Match Mortal's recommendation to an available engine action."""
        atype = analysis.recommended_action
        tile = analysis.recommended_tile

        if atype == "hora":
            for a in available:
                if a.type in (ActionType.TSUMO, ActionType.RON):
                    return a

        if atype == "reach":
            for a in available:
                if a.type == ActionType.RIICHI and a.tile == tile:
                    return a

        if atype == "dahai":
            for a in available:
                if a.type == ActionType.DISCARD and a.tile == tile:
                    return a
            # Try normalized match
            for a in available:
                if a.type == ActionType.DISCARD and normalize(a.tile) == normalize(tile):
                    return a

        if atype == "none":
            for a in available:
                if a.type == ActionType.SKIP:
                    return a

        if atype in ("chi", "pon", "daiminkan", "ankan", "kakan"):
            for a in available:
                if a.type.value in (atype, "kan"):
                    return a

        return available[0]
