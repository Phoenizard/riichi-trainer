import React from 'react';
import Tile from './Tile';

interface DiscardPondProps {
  discards: string[];
  isRiichi: boolean;
  riichiTurn: number;
}

const DiscardPond: React.FC<DiscardPondProps> = ({ discards, isRiichi, riichiTurn }) => {
  return (
    <div className="discard-pond">
      {discards.map((tile, i) => (
        <Tile
          key={i}
          tile={tile}
          small
          sideways={isRiichi && i === riichiTurn}
        />
      ))}
    </div>
  );
};

export default DiscardPond;
