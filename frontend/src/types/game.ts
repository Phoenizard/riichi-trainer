// TypeScript types matching the WebSocket protocol

export interface MeldView {
  type: 'chi' | 'pon' | 'ankan' | 'minkan' | 'kakan';
  tiles: string[];
  from_player: number;
  called_tile: string;
}

export interface PlayerView {
  discards: string[];
  melds: MeldView[];
  is_riichi: boolean;
  riichi_turn: number;
  hand_count: number;
  seat_wind: string;
  // Only for seat 0 (self)
  hand?: string[];
  draw_tile?: string | null;
}

export interface GameInfo {
  round_wind: string;
  round_number: number;
  honba: number;
  riichi_sticks: number;
  scores: number[];
  dora_indicators: string[];
  tiles_remaining: number;
  dealer: number;
  current_turn: number;
  players: PlayerView[];
}

export interface ActionOption {
  type: string;
  tile?: string;
  meld_tiles?: string[];
}

export interface CoachAnalysis {
  recommended: string;
  recommended_action: string;  // "dahai"/"none"/"pon"/"chi"/"hora"/"reach"/...
  shanten: number;
  candidates: { tile: string; score: number; rank: number }[];
}

export interface EfficiencyRow {
  discard: string;
  accepts: string[];
  total: number;
  remaining: number;
}

export interface RoundResultData {
  result: string;
  winner: number;
  loser: number;
  han: number;
  fu: number;
  yaku: string[];
  score_deltas: number[];
  scores: number[];
  winning_hand?: string[];
  winning_melds?: MeldView[];
}

export interface GameState {
  phase: 'lobby' | 'playing' | 'round_result' | 'game_over';
  gameInfo: GameInfo | null;
  hand: string[];
  drawTile: string | null;
  availableActions: ActionOption[] | null;
  coach: CoachAnalysis | null;
  efficiency: EfficiencyRow[] | null;
  efficiencyShanten: number | null;
  roundResult: RoundResultData | null;
  finalScores: number[] | null;
  aiThinking: boolean;
}

// Server → Client messages
export type ServerMessage =
  | { type: 'game_info' } & GameInfo
  | { type: 'game_event'; event: Record<string, unknown> }
  | { type: 'action_required'; available_actions: ActionOption[]; hand: string[]; draw_tile: string | null; efficiency?: EfficiencyRow[]; shanten?: number | null }
  | { type: 'coach'; analysis: CoachAnalysis }
  | { type: 'round_result' } & RoundResultData
  | { type: 'game_over'; scores: number[] }
  | { type: 'ai_thinking'; active: boolean }
  | { type: 'error'; message: string };

// Client → Server messages
export type ClientMessage =
  | { type: 'new_game' }
  | { type: 'action'; action_type: string; tile?: string; meld_tiles?: string[] }
  | { type: 'continue_round' };
