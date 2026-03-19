import React from 'react';
import Tile from './Tile';
import MeldDisplay from './MeldDisplay';
import type { ActionOption, MeldView, CoachAnalysis } from '../types/game';

interface HandAreaProps {
  hand: string[];
  drawTile: string | null;
  melds: MeldView[];
  availableActions: ActionOption[] | null;
  coach: CoachAnalysis | null;
  onDiscard: (tile: string) => void;
}

const HandArea: React.FC<HandAreaProps> = ({ hand, drawTile, melds, availableActions, coach, onDiscard }) => {
  // Which tiles can be discarded?
  const discardableTiles = new Set<string>();
  if (availableActions) {
    for (const a of availableActions) {
      if (a.type === 'discard' && a.tile) {
        discardableTiles.add(a.tile);
      }
    }
  }

  const canDiscard = discardableTiles.size > 0;
  const recommended = coach?.recommended || '';

  return (
    <div className="hand-area">
      <div className="hand-tiles">
        {hand.map((tile, i) => (
          <Tile
            key={`h-${i}`}
            tile={tile}
            clickable={canDiscard && discardableTiles.has(tile)}
            recommended={tile === recommended}
            onClick={() => onDiscard(tile)}
          />
        ))}
        {drawTile && (
          <div className="draw-tile-gap">
            <Tile
              key="draw"
              tile={drawTile}
              clickable={canDiscard && discardableTiles.has(drawTile)}
              recommended={drawTile === recommended}
              onClick={() => onDiscard(drawTile)}
            />
          </div>
        )}
      </div>
      <MeldDisplay melds={melds} small={false} ownerSeat={0} />
    </div>
  );
};

export default HandArea;
