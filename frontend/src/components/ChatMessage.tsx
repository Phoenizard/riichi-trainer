import React from 'react';
import Tile from './Tile';
import type { ChatMessage as ChatMessageType } from '../types/game';

// Parse [3m], [0p], [E] etc. into inline Tile components
const TILE_MARKER_RE = /\[([0-9][mps]|[ESWNPFC])\]/g;

function renderContent(content: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  TILE_MARKER_RE.lastIndex = 0;
  while ((match = TILE_MARKER_RE.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push(content.slice(lastIndex, match.index));
    }
    parts.push(
      <Tile key={`tile-${match.index}`} tile={match[1]} inline />
    );
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < content.length) {
    parts.push(content.slice(lastIndex));
  }
  return parts;
}

interface Props {
  message: ChatMessageType;
}

const ChatMessageComponent: React.FC<Props> = ({ message }) => {
  if (message.role === 'system') {
    return <div className="chat-system">{message.content}</div>;
  }

  const isUser = message.role === 'user';

  return (
    <div className={`chat-bubble ${isUser ? 'chat-bubble-user' : 'chat-bubble-ai'}`}>
      {renderContent(message.content)}
    </div>
  );
};

export default ChatMessageComponent;
