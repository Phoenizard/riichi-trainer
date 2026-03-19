import React, { useState } from 'react';
import Tile from './Tile';
import DiscardPond from './DiscardPond';
import MeldDisplay from './MeldDisplay';
import type { PlayerView } from '../types/game';

const SEAT_NAMES = ['自家', '下家', '対面', '上家'];
const WIND_LABELS: Record<string, string> = { E: '東', S: '南', W: '西', N: '北' };

interface OpponentAreaProps {
  player: PlayerView;
  seat: number;
  score: number;
  isActive?: boolean;
}

const OpponentArea: React.FC<OpponentAreaProps> = ({ player, seat, score, isActive }) => {
  const [showHand, setShowHand] = useState(false);

  return (
    <div className={`opponent-area${isActive ? ' opponent-active' : ''}`}>
      <div className="opponent-header">
        <span>{WIND_LABELS[player.seat_wind] || player.seat_wind} {SEAT_NAMES[seat]}</span>
        <span>{score}点</span>
        {player.is_riichi && <span style={{ color: 'var(--riichi)' }}>⚡立直</span>}
        <button
          className="peek-btn"
          onClick={() => setShowHand(!showHand)}
          title={showHand ? '隐藏手牌' : '查看手牌'}
        >
          {showHand ? '🔓' : '🔒'}
        </button>
      </div>
      {/* Opponent hand (peek mode) */}
      {showHand && player.hand && (
        <div style={{ display: 'flex', gap: 1, flexWrap: 'wrap', margin: '4px 0', paddingBottom: 6, borderBottom: '1px dashed #ccc' }}>
          {player.hand.map((tile, i) => (
            <Tile key={i} tile={tile} small />
          ))}
          {player.draw_tile && (
            <div className="draw-tile-gap">
              <Tile tile={player.draw_tile} small />
            </div>
          )}
        </div>
      )}
      <DiscardPond
        discards={player.discards}
        isRiichi={player.is_riichi}
        riichiTurn={player.riichi_turn}
      />
      <MeldDisplay melds={player.melds} ownerSeat={seat} />
    </div>
  );
};

export default OpponentArea;
