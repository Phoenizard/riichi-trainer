# AI 教练侧边栏 — 设计文档

## 目标

在 Web UI 中添加一个自由对话的 AI 麻将教练侧边栏。用户可以在对局中随时提问（牌效率、攻防判断），AI 基于当前牌局上下文给出个性化指导。

## 架构

后端代理模式：前端通过 WebSocket 收发聊天消息，后端拼接牌局上下文后调用 DeepSeek V3.2 API（OpenAI 兼容接口），返回流式响应。对话历史存后端内存，每局清空。

## 技术栈

- **LLM**: DeepSeek V3.2 API（OpenAI SDK 兼容，`base_url` 切换即可换模型）
- **后端**: FastAPI WebSocket（复用现有连接，新增 chat 消息类型）
- **前端**: React 侧边栏组件 + 右键牌标记

---

## 用户交互

### 侧边栏

- 牌桌右侧弹出的聊天面板，可折叠/展开
- 消息列表：用户消息靠右，AI 回复靠左
- 底部输入框 + 发送按钮
- AI 回复支持流式显示（逐字出现）
- 新一局开始时自动清空对话历史，显示系统提示"新一局开始"

### 右键牌标记

- **左键**：出牌（现有行为不变）
- **右键**：在聊天输入框末尾插入牌标记，如 `[3m]`、`[0p]`
- 可连续右键多张牌，输入框累积标记：`为什么不打 [3m] 而打 [8s]？`
- 牌标记在消息中以小牌图标渲染（复用现有 Tile 组件，inline 小尺寸）

### 交互限制

- 对话仅在对局中可用（lobby/game end 状态下侧边栏不可用或只读）
- 每条消息最长 500 字符
- AI 回复期间禁用发送按钮（防止并发请求）

---

## 后端设计

### WebSocket 消息协议

复用现有 `/ws` 连接，新增消息类型：

```
// 前端 → 后端：用户发送聊天消息
{
  "type": "chat_message",
  "content": "为什么不打 [3m]？"
}

// 后端 → 前端：AI 回复（流式，多条）
{
  "type": "chat_reply_chunk",
  "content": "因为",       // 增量文本
  "done": false
}

// 后端 → 前端：AI 回复结束
{
  "type": "chat_reply_chunk",
  "content": "",
  "done": true
}

// 后端 → 前端：新局开始，清空对话
{
  "type": "chat_clear"
}
```

### LLM 上下文构建

后端在收到 `chat_message` 时，自动拼接当前牌局上下文到 system prompt：

**System Prompt 结构：**

```
[角色定义]
你是一位日本麻将（立直麻将）教练。用中文回答。
聚焦牌效率分析和基本攻防判断。
简洁回答，每次不超过 150 字。

[当前牌局状态]
场风: 東  局数: 東2局  本場: 0
巡目: 8
自风: 南
手牌: 1m 3m 5m 5m 2p 3p 7p 8p 9p 3s 5s 6s 7s
副露: 无
摸牌: 4p
向听数: 1
ドラ表示牌: 6m
牌河: 9m 1p W ...
点数: 自家25000 下家25000 対面25000 上家25000

[其他家可见信息]
下家牌河: ... 副露: 1s2s3s(吃)
対面牌河: ... 副露: 无 立直中
上家牌河: ... 副露: 白白白(碰)

[AI教练分析 (Mortal)]
推荐打: 9p
候选牌:
  9p: Q=2.34 (推荐)
  1m: Q=1.98
  7p: Q=1.45
  3s: Q=0.89
  5m: Q=0.12
```

**上下文数据来源：**

| 数据 | 来源 |
|------|------|
| 手牌、副露、摸牌 | `GameState.players[0]` |
| 牌河 | `GameState.players[*].discards` |
| 场风、局数、本場、巡目 | `GameState` |
| 点数 | `GameState.scores` |
| 向听数、Q-values、候选牌 | `MortalAnalysis`（最近一次 coach 分析） |
| 其他家副露 | `GameState.players[1-3].melds` |
| 其他家立直状态 | `GameState.players[1-3].is_riichi` |
| dora 表示牌 | `GameState.dora_indicators` |

### LLM 调用

```python
# 使用 openai SDK，兼容 DeepSeek API
from openai import OpenAI

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

# 流式调用
stream = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": system_prompt},
        *conversation_history,
        {"role": "user", "content": user_message}
    ],
    stream=True,
    max_tokens=300,
    temperature=0.7
)
```

### 对话历史管理

- 存在 `GameSession` 内存中，`list[dict]`（role + content）
- 每局开始时清空（`_on_round_start` 发送 `chat_clear`）
- 不持久化到数据库（未来收集训练数据时再加）
- system prompt 每次请求重新拼接（牌局状态是动态的）
- 对话历史不包含 system prompt，只有 user/assistant 轮次

### 新增文件

| 文件 | 职责 |
|------|------|
| `backend/llm_coach.py` | LLM 客户端封装：构建 system prompt、管理对话历史、流式调用 DeepSeek API |

### 修改文件

| 文件 | 改动 |
|------|------|
| `backend/server.py` | WebSocket handler 新增 `chat_message` 类型路由 |
| `backend/game_session.py` | 持有 `LLMCoach` 实例，新局时调用清空，转发 chat 请求 |
| `backend/web_agent.py` | 暴露 `get_game_context()` 方法，返回当前牌局状态供 LLM 使用 |

---

## 前端设计

### 新增组件

| 组件 | 职责 |
|------|------|
| `ChatSidebar.tsx` | 侧边栏容器：消息列表 + 输入框 + 折叠按钮 |
| `ChatMessage.tsx` | 单条消息渲染：用户/AI 气泡，内联牌标记解析 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `App.tsx` | 布局调整：牌桌 + 侧边栏并排 |
| `hooks/useGameSocket.ts` | 新增 `chat_reply_chunk`、`chat_clear` handler；新增 `sendChatMessage` 方法 |
| `types/game.ts` | 新增 `ChatMessage` 类型 |
| `components/Tile.tsx` | 支持 `inline` prop（小尺寸，用于消息内嵌牌图标） |
| `components/HandArea.tsx`（或持有手牌点击事件的组件） | 右键事件处理：`onContextMenu` 插入牌标记到聊天输入 |
| `styles/tiles.css` | 侧边栏样式、消息气泡样式、inline 牌样式 |

### 状态管理

在现有 `useReducer` 中新增：

```typescript
// GameState 新增
chatMessages: ChatMessage[];    // 对话历史
chatInput: string;              // 输入框内容（用于右键插入标记）
chatLoading: boolean;           // AI 回复中

// ChatMessage 类型
interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
}

// 新增 action 类型
| { type: 'CHAT_SEND'; payload: string }
| { type: 'CHAT_CHUNK'; payload: string }
| { type: 'CHAT_DONE' }
| { type: 'CHAT_CLEAR' }
| { type: 'CHAT_INPUT'; payload: string }
```

### 牌标记渲染

消息文本中的 `[3m]`、`[0p]` 等标记，渲染时解析为 inline Tile 组件：

```
"为什么不打 [3m]？" → "为什么不打 " + <Tile tile="3m" inline /> + "？"
```

正则匹配：`/\[([0-9][mps]|[ESWNPFC])\]/g`

---

## 配置

环境变量（`.env`）：

```
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com   # 可选，默认值
DEEPSEEK_MODEL=deepseek-chat                  # 可选，默认值
```

后端启动时检查 `DEEPSEEK_API_KEY`，缺失则禁用聊天功能（侧边栏显示"未配置 API Key"）。

---

## 不在本次范围

- 局后复盘功能（未来通过侧边栏对话触发，从 decisions 表拉数据）
- 对话历史持久化/训练数据收集
- 本地模型推理（Ollama）
- 复杂读牌分析、顺位判断
- 多语言支持

---

## 未来演进路线

1. **收集训练数据** — 对话历史存 SQLite，标注质量
2. **微调 7B 模型** — 用收集的对话数据微调 DeepSeek-R1-Distill-7B 或 Qwen2.5-7B
3. **本地推理** — Ollama 部署微调模型，`base_url` 切换为 `http://localhost:11434/v1`
4. **局后复盘** — 侧边栏输入"复盘"触发，从 decisions 表拉取本局决策历史注入上下文
