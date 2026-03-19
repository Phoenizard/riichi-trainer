# Riichi Trainer — 日本麻将 AI 训练器

单人日本立直麻将训练工具。玩家与 3 个 Mortal AI 对手对局，实时 AI 教练分析每一步决策。

## 功能

- **完整四人东南战**：吃、碰、杠、立直、自摸、荣和、振听、流局
- **Mortal AI 对手**：本地 libriichi 推理，3 个 AI 对手 + 1 个影子教练
- **实时 AI 教练**：推荐打牌、候选排名（Q-value）、向听数显示
- **牌效率分析**：每张弃牌的进张数、剩余枚数，最优行高亮
- **数据记录**：SQLite 记录每个决策点，局末显示 AI 一致率
- **正规计分**：han/fu 计算，中文役名显示

## 快速开始

### 环境要求

- Python 3.9+（推荐 conda）
- Node.js 18+（前端构建）
- Rust 工具链（编译 libriichi，仅首次需要）

### 安装

```bash
# 1. 创建 conda 环境
conda create -n reach python=3.11
conda activate reach

# 2. 安装 Python 依赖
pip install mahjong torch fastapi uvicorn requests pytest

# 3. 编译 libriichi（首次）
cd tmp/Mortal
cargo build -p libriichi --lib --release
# macOS:
cp target/release/libriichi.dylib ../../libriichi.so
# Linux:
# cp target/release/libriichi.so ../../libriichi.so
cd ../..

# 4. 放置模型权重
# 将 Mortal v4 模型文件放到 model/ 目录下
# 文件名: model/model_v4_20240308_best_min.pth

# 5. 构建前端
cd frontend
npm install
npm run build
cd ..
```

### 启动

```bash
conda activate reach

# Web UI（主要）
python start_web.py
# 打开浏览器访问 http://localhost:8000

# 终端 UI（备用）
python main.py
```

> 如果没有 libriichi 或模型文件，会自动降级到 MockAgent（规则型 AI）。

## 项目结构

```
riichi-trainer/
├── start_web.py              # Web UI 启动入口
├── main.py                   # 终端 UI 启动入口
├── game/
│   ├── engine.py             # 游戏引擎：发牌、副露、计分、流程控制
│   ├── tiles.py              # 牌表示、排序、dora 计算
│   └── efficiency.py         # 牌效率计算（基于向听数）
├── ai/
│   ├── mortal_agent.py       # Mortal AI 接口（libriichi / MJAPI / Docker）
│   ├── mortal_engine.py      # PyTorch 模型加载与推理
│   ├── mortal_model.py       # 神经网络结构（Brain + DQN）
│   └── mock_agent.py         # 规则型 AI（降级备选）
├── backend/
│   ├── server.py             # FastAPI + WebSocket 服务
│   ├── web_agent.py          # WebSocket ↔ 引擎桥接
│   ├── game_session.py       # 对局生命周期管理
│   └── db.py                 # SQLite 数据记录
├── frontend/
│   ├── src/                  # React + TypeScript 源码
│   └── dist/                 # 构建产物（FastAPI 静态服务）
├── model/                    # Mortal v4 模型权重（gitignored）
├── data/                     # SQLite 数据库（gitignored）
└── tests/                    # 测试
```

## 开发

### 运行测试

```bash
conda run -n reach python -m pytest tests/ -v
```

### 引擎压力测试

```bash
conda run -n reach python -c "
from game.engine import GameEngine
from ai.mock_agent import MockAgent
agents = [MockAgent(f'P{i}') for i in range(4)]
engine = GameEngine(agents)
for r in range(5):
    state = engine.play_round()
    print(f'Round {r+1}: {state.result.value}, scores={engine.game_scores}')
"
```

### 前端开发

```bash
cd frontend
npm run dev    # Vite 开发服务器（热更新）
npm run build  # 生产构建到 dist/
```

前端构建后由 FastAPI 直接提供静态文件服务，无需额外配置。

### 牌表示规则

| 类型 | 格式 | 示例 |
|------|------|------|
| 万子 | `1m`-`9m` | `1m` = 一万 |
| 筒子 | `1p`-`9p` | `5p` = 五筒 |
| 索子 | `1s`-`9s` | `9s` = 九索 |
| 赤五 | `0m`/`0p`/`0s` | `0m` = 赤五万 |
| 风牌 | `E`/`S`/`W`/`N` | `E` = 東 |
| 三元牌 | `P`/`F`/`C` | `P` = 白, `F` = 發, `C` = 中 |

Mortal mjai 协议中赤五表示为 `5mr`/`5pr`/`5sr`，由 `mortal_agent.py` 自动转换。

## 技术栈

| 层 | 技术 |
|----|------|
| 游戏引擎 | Python, `mahjong` 库（计分） |
| AI 推理 | PyTorch, libriichi (Rust → .so) |
| 后端 | FastAPI, WebSocket, SQLite |
| 前端 | React 19, TypeScript, Vite |
| 渲染 | 纯 CSS（无图片资源） |

## 待开发功能

- **AI 教练对话**：LLM 驱动的侧边栏对话（设计文档见 `docs/superpowers/specs/`）
- **局后复盘**：通过对话触发，从数据库拉取决策历史分析
