import { useReducer, useCallback, useRef, useEffect } from 'react';
import type { GameState, ServerMessage, ClientMessage, GameInfo, EfficiencyRow } from '../types/game';

// Tile sort order: 1m-9m, 1p-9p, 1s-9s, E/S/W/N, P/F/C
const TILE_ORDER: Record<string, number> = {};
['m', 'p', 's'].forEach((suit, si) => {
  for (let n = 1; n <= 9; n++) {
    TILE_ORDER[`${n}${suit}`] = si * 9 + n - 1;
  }
});
['E', 'S', 'W', 'N', 'P', 'F', 'C'].forEach((t, i) => {
  TILE_ORDER[t] = 27 + i;
});

function sortTiles(tiles: string[]): string[] {
  return [...tiles].sort((a, b) => {
    // Normalize red fives (0m→5m etc.) for ordering
    const na = a.startsWith('0') ? '5' + a[1] : a;
    const nb = b.startsWith('0') ? '5' + b[1] : b;
    const ia = TILE_ORDER[na] ?? 999;
    const ib = TILE_ORDER[nb] ?? 999;
    if (ia !== ib) return ia - ib;
    // Red fives sort before regular fives
    const ra = a.startsWith('0') ? 0 : 1;
    const rb = b.startsWith('0') ? 0 : 1;
    return ra - rb;
  });
}

const initialState: GameState = {
  phase: 'lobby',
  gameInfo: null,
  hand: [],
  drawTile: null,
  availableActions: null,
  coach: null,
  efficiency: null,
  efficiencyShanten: null,
  roundResult: null,
  finalScores: null,
  aiThinking: false,
};

type GameAction =
  | { type: 'GAME_INFO'; payload: GameInfo }
  | { type: 'GAME_EVENT'; payload: Record<string, unknown> }
  | { type: 'ACTION_REQUIRED'; payload: { available_actions: any[]; hand: string[]; draw_tile: string | null; efficiency?: EfficiencyRow[]; shanten?: number | null } }
  | { type: 'COACH'; payload: any }
  | { type: 'ROUND_RESULT'; payload: any }
  | { type: 'GAME_OVER'; payload: { scores: number[] } }
  | { type: 'AI_THINKING'; payload: { active: boolean } }
  | { type: 'DISMISS_RESULT' }
  | { type: 'RESET' };

function gameReducer(state: GameState, action: GameAction): GameState {
  switch (action.type) {
    case 'GAME_INFO': {
      const info = action.payload;
      return {
        ...state,
        phase: state.phase === 'lobby' ? 'playing' : state.phase,
        gameInfo: info,
      };
    }
    case 'GAME_EVENT': {
      const event = action.payload;
      if (!state.gameInfo) return state;

      // Update player state from events
      const info = { ...state.gameInfo };
      const players = info.players.map(p => ({ ...p, discards: [...p.discards], melds: [...p.melds] }));

      const etype = event.type as string;
      const player = event.player as number;

      if (etype === 'discard' && player >= 0 && player < 4) {
        players[player].discards.push(event.tile as string);
        if (player === 0) {
          // Merge draw tile into hand, then remove the discarded tile
          const tile = event.tile as string;
          const newHand = [...state.hand];
          if (state.drawTile) {
            newHand.push(state.drawTile);
          }
          const idx = newHand.indexOf(tile);
          if (idx >= 0) {
            newHand.splice(idx, 1);
          }
          return {
            ...state,
            gameInfo: { ...info, players, current_turn: (player + 1) % 4 },
            hand: sortTiles(newHand),
            drawTile: null,
            availableActions: null,
            coach: null,
            efficiency: null,
            efficiencyShanten: null,
          };
        }
        // AI discard — advance current_turn
        return {
          ...state,
          gameInfo: { ...info, players, current_turn: player },
          aiThinking: false,
        };
      }

      if (etype === 'draw' && player === 0) {
        return {
          ...state,
          gameInfo: { ...info, players, tiles_remaining: (event.tiles_remaining as number) ?? info.tiles_remaining },
          drawTile: (event.tile as string) || null,
          aiThinking: false,
        };
      }

      if (etype === 'draw' && player !== 0) {
        return {
          ...state,
          gameInfo: { ...info, players, current_turn: player },
          aiThinking: true,
        };
      }

      if ((etype === 'chi' || etype === 'pon' || etype === 'kan' || etype === 'ankan' ||
           etype === 'kakan' || etype === 'daiminkan') && player >= 0 && player < 4) {
        // Add meld to player
        if (event.meld) {
          players[player].melds.push(event.meld as any);
        }
        // Remove called tile from discard pond of the source player
        if (event.from_player !== undefined) {
          const fromP = event.from_player as number;
          if (fromP >= 0 && fromP < 4 && players[fromP].discards.length > 0) {
            players[fromP].discards.pop();
          }
        }
        return {
          ...state,
          gameInfo: { ...info, players, current_turn: player },
          aiThinking: player !== 0,
        };
      }

      if (etype === 'reach' && player >= 0 && player < 4) {
        players[player].is_riichi = true;
        players[player].riichi_turn = players[player].discards.length;
      }

      if (etype === 'dora') {
        info.dora_indicators = [...info.dora_indicators, event.tile as string];
      }

      if (etype === 'start_round') {
        // Full state reset for new round comes via game_info
        return {
          ...state,
          phase: 'playing',
          availableActions: null,
          coach: null,
          roundResult: null,
          aiThinking: false,
        };
      }

      return {
        ...state,
        gameInfo: { ...info, players },
      };
    }
    case 'ACTION_REQUIRED':
      return {
        ...state,
        phase: 'playing',
        hand: action.payload.hand,
        drawTile: action.payload.draw_tile,
        availableActions: action.payload.available_actions,
        efficiency: action.payload.efficiency || null,
        efficiencyShanten: action.payload.shanten ?? null,
        aiThinking: false,
      };
    case 'COACH':
      return { ...state, coach: action.payload };
    case 'ROUND_RESULT':
      return {
        ...state,
        phase: 'round_result',
        roundResult: action.payload,
        availableActions: null,
        coach: null,
        efficiency: null,
        efficiencyShanten: null,
        aiThinking: false,
      };
    case 'GAME_OVER':
      return {
        ...state,
        phase: 'game_over',
        finalScores: action.payload.scores,
        availableActions: null,
        coach: null,
        efficiency: null,
        efficiencyShanten: null,
        aiThinking: false,
      };
    case 'AI_THINKING':
      return { ...state, aiThinking: action.payload.active };
    case 'DISMISS_RESULT':
      return { ...state, phase: 'playing', roundResult: null };
    case 'RESET':
      return initialState;
    default:
      return state;
  }
}

export function useGameSocket() {
  const [state, dispatch] = useReducer(gameReducer, initialState);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
      const msg: ServerMessage = JSON.parse(event.data);

      switch (msg.type) {
        case 'game_info':
          dispatch({ type: 'GAME_INFO', payload: msg as GameInfo });
          break;
        case 'game_event':
          dispatch({ type: 'GAME_EVENT', payload: msg.event });
          break;
        case 'action_required':
          dispatch({
            type: 'ACTION_REQUIRED',
            payload: {
              available_actions: msg.available_actions,
              hand: msg.hand,
              draw_tile: msg.draw_tile,
              efficiency: (msg as any).efficiency,
              shanten: (msg as any).shanten,
            },
          });
          break;
        case 'coach':
          dispatch({ type: 'COACH', payload: msg.analysis });
          break;
        case 'round_result':
          dispatch({ type: 'ROUND_RESULT', payload: msg });
          break;
        case 'game_over':
          dispatch({ type: 'GAME_OVER', payload: { scores: msg.scores } });
          break;
        case 'ai_thinking':
          dispatch({ type: 'AI_THINKING', payload: { active: msg.active } });
          break;
        case 'error':
          console.error('Server error:', msg.message);
          break;
      }
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
    };

    return () => {
      ws.close();
    };
  }, []);

  const send = useCallback((msg: ClientMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const startNewGame = useCallback(() => {
    dispatch({ type: 'RESET' });
    send({ type: 'new_game' });
  }, [send]);

  const sendAction = useCallback(
    (actionType: string, tile?: string, meldTiles?: string[]) => {
      const msg: ClientMessage = {
        type: 'action',
        action_type: actionType,
        ...(tile && { tile }),
        ...(meldTiles && { meld_tiles: meldTiles }),
      };
      send(msg);
      // Clear available actions immediately for responsiveness
      dispatch({ type: 'ACTION_REQUIRED', payload: { available_actions: [], hand: state.hand, draw_tile: state.drawTile, efficiency: undefined, shanten: null } });
    },
    [send, state.hand, state.drawTile]
  );

  const continueRound = useCallback(() => {
    send({ type: 'continue_round' });
    dispatch({ type: 'DISMISS_RESULT' });
  }, [send]);

  return { state, startNewGame, sendAction, continueRound };
}
