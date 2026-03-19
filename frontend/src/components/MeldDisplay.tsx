import React from 'react';
import Tile from './Tile';
import type { MeldView } from '../types/game';

interface MeldDisplayProps {
  melds: MeldView[];
  small?: boolean;
  ownerSeat?: number; // seat of the player who owns this meld
}

const RELATIVE_LABELS = ['', '下', '対', '上'];

const MeldDisplay: React.FC<MeldDisplayProps> = ({ melds, small = true, ownerSeat }) => {
  if (melds.length === 0) return null;

  return (
    <div className="melds-row">
      {melds.map((meld, i) => {
        if (meld.type === 'ankan') {
          return (
            <div key={i} className="meld-group">
              <Tile tile={meld.tiles[0]} faceDown small={small} />
              <Tile tile={meld.tiles[1]} small={small} />
              <Tile tile={meld.tiles[2]} small={small} />
              <Tile tile={meld.tiles[3]} faceDown small={small} />
            </div>
          );
        }

        // Compute relative direction of from_player
        // 1=下家(right), 2=対面(across), 3=上家(left)
        const rel = ownerSeat !== undefined && meld.from_player >= 0
          ? (meld.from_player - ownerSeat + 4) % 4
          : 0;
        const relLabel = RELATIVE_LABELS[rel];

        // Separate called tile from the rest
        const calledTile = meld.called_tile;
        const otherTiles = [...meld.tiles];
        const calledIdx = otherTiles.indexOf(calledTile);
        if (calledIdx >= 0) {
          otherTiles.splice(calledIdx, 1);
        }

        // Position: called tile goes left(上家=3), middle(対面=2), or right(下家=1)
        let tiles: { tile: string; sideways: boolean }[];
        if (rel === 3) {
          // 上家: called tile on the left
          tiles = [
            { tile: calledTile, sideways: true },
            ...otherTiles.map(t => ({ tile: t, sideways: false })),
          ];
        } else if (rel === 2) {
          // 対面: called tile in the middle
          tiles = [
            { tile: otherTiles[0], sideways: false },
            { tile: calledTile, sideways: true },
            ...otherTiles.slice(1).map(t => ({ tile: t, sideways: false })),
          ];
        } else {
          // 下家 or unknown: called tile on the right
          tiles = [
            ...otherTiles.map(t => ({ tile: t, sideways: false })),
            { tile: calledTile, sideways: true },
          ];
        }

        return (
          <div key={i} className="meld-group">
            {relLabel && <span className="meld-source-label">{relLabel}</span>}
            {tiles.map((t, j) => (
              <Tile key={j} tile={t.tile} small={small} sideways={t.sideways} />
            ))}
          </div>
        );
      })}
    </div>
  );
};

export default MeldDisplay;
