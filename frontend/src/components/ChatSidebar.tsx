import React, { useRef, useEffect } from 'react';
import ChatMessageComponent from './ChatMessage';
import type { ChatMessage } from '../types/game';

interface Props {
  messages: ChatMessage[];
  input: string;
  loading: boolean;
  onSend: (content: string) => void;
  onInputChange: (value: string) => void;
  gamePhase: string;
}

const ChatSidebar: React.FC<Props> = ({ messages, input, loading, onSend, onInputChange, gamePhase }) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !loading) {
      onSend(input);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const isDisabled = gamePhase !== 'playing' && gamePhase !== 'round_result';

  return (
    <div className="chat-sidebar">
      <div className="chat-header">AI 教练</div>
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">对局中随时提问，AI 教练为你分析牌局。</div>
        )}
        {messages.map((msg, i) => {
          // Show turn divider when turnNumber changes between non-system messages
          let showDivider = false;
          let turnLabel = 0;
          if (msg.turnNumber !== undefined && msg.role !== 'system') {
            // Find previous non-system message with a turnNumber
            for (let j = i - 1; j >= 0; j--) {
              if (messages[j].role !== 'system' && messages[j].turnNumber !== undefined) {
                if (messages[j].turnNumber !== msg.turnNumber) {
                  showDivider = true;
                  turnLabel = msg.turnNumber!;
                }
                break;
              }
            }
            // First message with turnNumber also gets a label
            if (!showDivider && i === 0 || (!showDivider && messages.slice(0, i).every(m => m.role === 'system' || m.turnNumber === undefined))) {
              showDivider = true;
              turnLabel = msg.turnNumber!;
            }
          }
          return (
            <React.Fragment key={i}>
              {showDivider && (
                <div className="chat-turn-divider">
                  <span>第 {turnLabel} 巡</span>
                </div>
              )}
              <ChatMessageComponent message={msg} />
            </React.Fragment>
          );
        })}
        <div ref={messagesEndRef} />
      </div>
      <form className="chat-input-area" onSubmit={handleSubmit}>
        <textarea
          className="chat-input"
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isDisabled ? '对局中可用' : '输入问题... (Shift+Enter 换行)'}
          disabled={isDisabled || loading}
          maxLength={500}
          rows={2}
        />
        <button
          type="submit"
          className="chat-send-btn"
          disabled={isDisabled || loading || !input.trim()}
        >
          {loading ? '...' : '发送'}
        </button>
      </form>
    </div>
  );
};

export default ChatSidebar;
