import React from 'react';

const SEAT_NAMES = ['自家 (You)', '下家 (右)', '対面', '上家 (左)'];

interface GameEndOverlayProps {
  scores: number[];
  onNewGame: () => void;
}

const GameEndOverlay: React.FC<GameEndOverlayProps> = ({ scores, onNewGame }) => {
  // Rank players by score (descending)
  const ranked = scores
    .map((score, i) => ({ seat: i, score }))
    .sort((a, b) => b.score - a.score);

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="modal-title">最終結果</div>

        <div className="modal-scores">
          {ranked.map(({ seat, score }, rank) => (
            <div
              key={seat}
              className="modal-score-row"
              style={{
                fontWeight: seat === 0 ? 700 : 400,
                fontSize: rank === 0 ? 16 : 14,
              }}
            >
              <span>{rank + 1}位</span>
              <span>{SEAT_NAMES[seat]}</span>
              <span>{score}点</span>
              {seat === 0 && <span style={{ color: 'var(--coach)' }}>★</span>}
            </div>
          ))}
        </div>

        <div style={{ textAlign: 'center', margin: '12px 0', fontSize: 16 }}>
          あなたの順位: {ranked.findIndex(r => r.seat === 0) + 1}位
        </div>

        <button className="modal-btn" onClick={onNewGame}>
          新しいゲーム
        </button>
      </div>
    </div>
  );
};

export default GameEndOverlay;
