import React from 'react';
import OpponentArea from './OpponentArea';
import DiscardPond from './DiscardPond';
import MeldDisplay from './MeldDisplay';
import type { GameInfo } from '../types/game';

const WIND_LABELS: Record<string, string> = { E: '東', S: '南', W: '西', N: '北' };

interface TableAreaProps {
  gameInfo: GameInfo;
  aiThinking: boolean;
}

const TableArea: React.FC<TableAreaProps> = ({ gameInfo, aiThinking }) => {
  const { players, scores, current_turn } = gameInfo;
  const self = players[0];

  return (
    <div className="table-area">
      {/* Top: 対面 (seat 2) */}
      <div className="table-top">
        <OpponentArea player={players[2]} seat={2} score={scores[2]} isActive={current_turn === 2} />
      </div>

      {/* Left: 上家 (seat 3) */}
      <div className="table-left">
        <OpponentArea player={players[3]} seat={3} score={scores[3]} isActive={current_turn === 3} />
      </div>

      {/* Center: AI thinking indicator */}
      <div className="table-center">
        {aiThinking && <span className="ai-thinking">AI 思考中...</span>}
      </div>

      {/* Right: 下家 (seat 1) */}
      <div className="table-right">
        <OpponentArea player={players[1]} seat={1} score={scores[1]} isActive={current_turn === 1} />
      </div>

      {/* Bottom: self discard pond */}
      <div className="table-bottom">
        <div className={`opponent-area${current_turn === 0 ? ' opponent-active' : ''}`}>
          <div className="opponent-header">
            <span>{WIND_LABELS[self.seat_wind] || self.seat_wind} 自家</span>
            <span>{scores[0]}点</span>
            {self.is_riichi && <span style={{ color: 'var(--riichi)' }}>⚡立直</span>}
          </div>
          <DiscardPond
            discards={self.discards}
            isRiichi={self.is_riichi}
            riichiTurn={self.riichi_turn}
          />
          <MeldDisplay melds={self.melds} ownerSeat={0} />
        </div>
      </div>
    </div>
  );
};

export default TableArea;
