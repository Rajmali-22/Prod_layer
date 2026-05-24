# Prod_Layer

A **productive layer** deployed on any OS. Integrated with all AI, **core memory** to store context, and the ability to **switch model mid-context**. Seamless access to AI and information—**do tasks in one go**, **save your toggle tax**.

## Future of Work & Productivity

Prod_Layer is a single layer that runs everywhere you work: browser, IDE, email. It plugs into **all major AI providers** with one config, keeps **core memory** so context is never lost, and lets you **switch models mid-context** (fast / powerful / reasoning) by task. Get **seamless access to AI and information**, **do tasks in one go**, and **save your toggle tax**—no more jumping between tabs. Overlays stay **invisible in screen share** (Meet, Zoom, Teams).
## Features

- **Smart AI Responses** - Auto-detects code problems, definitions, questions, and instructions
- **Human-like Typing** - Natural typing speed with realistic variations
- **Ultra Human Mode** - Chain-of-thought code injection for coding interviews
- **Screen Share Invisible** - Windows excluded from screen capture (Zoom, Meet, Teams)
- **Voice Input** - Hold-to-talk speech recognition
- **Vision Analysis** - Screenshot + AI analysis
- **Persistent Chat** - Continue conversations across sessions with full history
- **Cross-Model Memory** - Context shared across different AI models and windows
- **Multi-LLM Provider System** - Seamless switching between 12+ AI providers
- **Smart Routing** - Automatic model selection based on task complexity
- **Per-Window Context** - Separate memory for each application window

## Quick Start

```bash
# Install dependencies
npm install
pip install -r requirements.txt

# Configure API keys
cp config.example.env .env
# Edit .env with your keys

# Run
npm start
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+D` | Process clipboard (code/question/text) |
| `Ctrl+Shift+P` | Inject AI response |
| `Ctrl+Alt+Enter` | Fix grammar / continue writing |
| `Ctrl+Shift+F` | Screenshot + Vision analysis |
| `Ctrl+Shift+E` | **Save screenshot** of current window (use when OS capture is blocked) |
| `Ctrl+Shift+V` | Voice input (hold to talk) |
| `Ctrl+Shift+S` | Open settings |
| `Ctrl+Shift+C` | Open chat window |
| `Ctrl+Shift+I` | Toggle Interview Q&A mode window |
| `Ctrl+Alt+I` | Force capture question and answer now |
| `Ctrl+Shift+Space` | Toggle overlay window |
| `Escape` | Cancel / close popup |

## Settings

Access with `Ctrl+Shift+S`:

| Setting | Description |
|---------|-------------|
| **AI Assistant** | Master on/off toggle |
| **Dark Mode** | UI theme |
| **Human-like Typing** | Natural speed variation |
| **Auto Inject** | Skip suggestion popup |
| **Live Mode** | Auto-suggest on typing pause |
| **Coding Mode** | Show code + explanation windows |
| **Ultra Human Typing** | Chain-of-thought code injection |
| **Interview Q&A Mode** | Live interview answer panel (streaming) |
| **Interview Audio Source** | Auto / Microphone / Loopback |
| **Interview Answer Model** | Fast model used for interview answers |
| **LLM Provider** | Select default AI model |
| **API Key Management** | Configure and test provider keys |

## Modes

### Smart Clipboard (Ctrl+Shift+D)

Auto-detects content type and responds appropriately:

| You Copy | AI Response |
|----------|-------------|
| `"two sum problem"` | Clean code solution |
| `"OOP"` | 25-35 word definition |
| `"What is REST?"` | Direct 2-4 sentence answer |
| Code + `"explain this"` | Follows your instruction |

### Ultra Human Typing (Interview Mode)

For coding interviews - types code like a real developer:

1. Enable **Ultra Human Typing** in Settings
2. Copy the coding problem
3. Click in your code editor
4. Press `Ctrl+Shift+P`
5. AI generates and types code with:
   - Main skeleton first with `pass`
   - Navigates up to add helper functions
   - Returns to implement main
   - Realistic typos and corrections
   - Variable pauses between sections

### Other Modes

- **Grammar Mode** - Fix spelling/grammar (`Ctrl+Alt+Enter` on typed text)
- **Extension Mode** - Continue writing (`Ctrl+Alt+Enter` again within 2s)
- **Vision Mode** - Analyze screenshots (`Ctrl+Shift+F`)
- **Voice Mode** - Speech to text (`Ctrl+Shift+V` hold to talk)
- **Chat Mode** - Persistent conversations with full history (`Ctrl+Shift+C`)
- **Interview Q&A Mode** - Detect question and stream concise answer in a dedicated 400x800 panel (`Ctrl+Shift+I`, `Ctrl+Alt+I`)

### Advanced Features

#### Multi-LLM Provider System

Prod_Layer supports 12+ AI providers through LiteLLM:

- **Fast Models**: Groq Llama 3.3 70B, Mistral Small, GPT-4o Mini, Gemini 2.0 Flash
- **Powerful Models**: DeepSeek Chat, Claude Sonnet, GPT-4o, Grok 4, Together Llama 3.3 70B
- **Reasoning Models**: DeepSeek Reasoner, Perplexity Sonar Pro, Cohere Command R+, Replicate Llama 405B

#### Smart Routing

- **Auto Mode**: Automatically selects the best model based on task complexity
- **Manual Selection**: Choose specific models from the settings dropdown
- **Fallback System**: Seamlessly switches providers on rate limits or auth errors

#### Memory System

- **Per-Window Memory**: Each application maintains separate conversation context
- **Cross-Model Memory**: Chat and prompt bar interactions are shared across models
- **Persistent Storage**: Conversations saved to disk and restored across sessions
- **Context Window Management**: Automatically caps history sent to LLMs to avoid overflow

#### Chat Window

Access with `Ctrl+Shift+C`:

- Full conversation history with timestamps
- Model selection dropdown
- Markdown formatting support
- Streaming responses
- Search and filter past conversations

## Project Structure

```
NXlayer/
├── main.js                              # Electron main process
├── package.json                         # Node dependencies
├── requirements.txt                     # Python dependencies
├── .env                                 # API keys (not committed)
├── config.example.env                   # Example config
│
├── src/
│   ├── electron/
│   │   └── keystore.js                  # Encrypted API key storage
│   │
│   ├── services/                        # Python backend services
│   │   ├── ai/
│   │   │   ├── backend.py               # Persistent AI backend with streaming
│   │   │   └── prompts.py               # Context-aware smart prompting
│   │   ├── providers/                   # Multi-LLM provider system
│   │   │   ├── __init__.py              # ProviderManager interface
│   │   │   ├── router.py                # Model routing and discovery
│   │   │   ├── context.py               # Smart routing logic
│   │   │   └── memory.py                # Per-window memory management
│   │   ├── input/
│   │   │   ├── monitor/                 # Keystroke monitor package
│   │   │   │   ├── config.py            # Configuration constants
│   │   │   │   ├── state.py             # Global application state
│   │   │   │   ├── threads.py           # Background threads
│   │   │   │   ├── handlers/            # Keystroke & command handlers
│   │   │   │   └── managers/            # IPC, window, log, live-mode managers
│   │   │   ├── monitor.py               # Monitor entry point
│   │   │   ├── injector.py              # Text injection (pynput)
│   │   │   └── typer.py                 # Human-like code typing
│   │   └── media/
│   │       ├── vision.py                # Screenshot + AI vision analysis
│   │       └── voice.py                 # Speech recognition
│   │
│   └── renderer/                        # Electron frontend
│       ├── overlay/
│       │   ├── index.html               # Main overlay UI
│       │   └── index.js                 # Overlay window logic
│       ├── chat/
│       │   ├── index.html               # Persistent chat interface
│       │   └── index.js                 # Chat window logic
│       ├── settings/
│       │   ├── index.html               # Settings UI
│       │   └── index.js                 # Settings logic
│       ├── output/
│       │   └── index.html               # Suggestion popup
│       ├── explanation/
│       │   └── index.html               # Code explanation window
│       ├── common/
│       │   └── styles.css               # Shared styles
│       └── lib/
│           └── marked.min.js            # Markdown parser
│
├── tests/                               # Test suite
├── tools/
│   └── dev/                             # Developer analysis scripts
│       ├── math_analysis.py
│       ├── keystroke_analysis.py
│       └── typer_simulator.py
├── data/                                # Runtime-generated files
│   ├── chats/                           # Persistent chat history
│   └── memory/                          # Per-window conversation memory
└── docs/                                # Documentation
```

## Requirements

- Node.js 16+
- Python 3.8+
- Windows 10/11 (primary support)
- macOS/Linux (partial support)

## API Keys

Create `.env` file with your API keys. Prod_Layer supports 12+ providers. Keys can also be configured through the Settings UI (`Ctrl+Shift+S`).

### All Agents & API Key Links

#### Fast Models

| Agent | Env var | Get API key |
|-------|---------|-------------|
| **Groq Llama 3.3 70B** | `GROQ_API_KEY` | https://console.groq.com/keys |
| **Mistral Small** | `MISTRAL_API_KEY` | https://console.mistral.ai/api-keys/ |
| **GPT-4o Mini** | `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| **Gemini 2.0 Flash** | `GEMINI_API_KEY` | https://aistudio.google.com/apikey |

#### Powerful Models

| Agent | Env var | Get API key |
|-------|---------|-------------|
| **DeepSeek Chat** | `DEEPSEEK_API_KEY` | https://platform.deepseek.com/api_keys |
| **Claude Sonnet** | `ANTHROPIC_API_KEY` | https://console.anthropic.com/settings/keys |
| **GPT-4o** | `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| **Grok 4** | `XAI_API_KEY` | https://console.x.ai/ |
| **Together Llama 3.3 70B** | `TOGETHERAI_API_KEY` | https://api.together.xyz/settings/api-keys |
| **Perplexity Sonar Pro** | `PERPLEXITYAI_API_KEY` | https://www.perplexity.ai/settings/api |
| **Cohere Command R+** | `COHERE_API_KEY` | https://dashboard.cohere.com/api-keys |
| **Replicate Llama 405B** | `REPLICATE_API_TOKEN` | https://replicate.com/account/api-tokens |

#### Reasoning Models

| Agent | Env var | Get API key |
|-------|---------|-------------|
| **DeepSeek Reasoner** | `DEEPSEEK_API_KEY` | https://platform.deepseek.com/api_keys |

#### Vision (Screenshots)

| Provider | Env var | Get API key |
|----------|---------|-------------|
| **Google / Gemini Vision** | `GOOGLE_API_KEY` or `GEMINI_API_KEY` | https://aistudio.google.com/apikey |

### Example `.env`

```env
# Primary providers
MISTRAL_API_KEY=your-mistral-key
GROQ_API_KEY=your-groq-key
DEEPSEEK_API_KEY=your-deepseek-key

# Additional providers (optional)
ANTHROPIC_API_KEY=your-anthropic-key
OPENAI_API_KEY=your-openai-key
GEMINI_API_KEY=your-gemini-key
XAI_API_KEY=your-xai-key
TOGETHERAI_API_KEY=your-togetherai-key
PERPLEXITYAI_API_KEY=your-perplexity-key
COHERE_API_KEY=your-cohere-key
REPLICATE_API_TOKEN=your-replicate-token
GOOGLE_API_KEY=your-google-key
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Shortcuts not working | Run as Administrator |
| Module not found | `pip install -r requirements.txt` |
| Unicode errors | Set `PYTHONIOENCODING=utf-8` |
| API errors | Check keys in `.env` |
| Window visible in screen share | Restart app after enabling |

## License

MIT License
