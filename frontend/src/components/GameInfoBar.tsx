import React from 'react';
import Tile from './Tile';
import type { GameInfo } from '../types/game';

const SEAT_NAMES = ['自家', '下家', '対面', '上家'];

interface GameInfoBarProps {
  gameInfo: GameInfo;
}

const GameInfoBar: React.FC<GameInfoBarProps> = ({ gameInfo }) => {
  const {
    round_wind, round_number, honba, riichi_sticks,
    scores, dora_indicators, tiles_remaining, players, current_turn,
  } = gameInfo;

  const roundLabel = `${round_wind}${round_number + 1}局`;

  return (
    <div className="game-info-bar">
      <div className="game-info-section">
        <span style={{ fontWeight: 700 }}>{roundLabel}</span>
        {honba > 0 && <span>{honba}本場</span>}
        {riichi_sticks > 0 && <span>供託:{riichi_sticks}</span>}
        <span>残り:{tiles_remaining}</span>
        <div className="dora-section">
          <span className="dora-label">ドラ:</span>
          {dora_indicators.map((d, i) => (
            <Tile key={i} tile={d} small />
          ))}
        </div>
      </div>
      <div className="game-info-section">
        {scores.map((score, i) => {
          const wind = players[i]?.seat_wind || '';
          const isActive = i === current_turn;
          const isRiichi = players[i]?.is_riichi;
          return (
            <div
              key={i}
              className={`score-badge ${isActive ? 'score-badge-active' : ''} ${isRiichi ? 'score-badge-riichi' : ''}`}
            >
              <span className="wind-label">{wind}</span>
              <span>{SEAT_NAMES[i]}</span>
              <span style={{ fontWeight: 600 }}>{score}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default GameInfoBar;
