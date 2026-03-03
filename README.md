# Prod_Layer

A **productive layer** deployed on any OS. Integrated with all AI, **core memory** to store context, and the ability to **switch model mid-context**. Seamless access to AI and information—**do tasks in one go**, **save your toggle tax**.

## Future of Work & Productivity

Prod_Layer is a single layer that runs everywhere you work: browser, IDE, email. It plugs into **all major AI providers** with one config, keeps **core memory** so context is never lost, and lets you **switch models mid-context** (fast / powerful / reasoning) by task. Get **seamless access to AI and information**, **do tasks in one go**, and **save your toggle tax**—no more jumping between tabs. Overlays stay **invisible in screen share** (Meet, Zoom, Teams). See **[HACKATHON.md](HACKATHON.md)** for the full submission and demo script.

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

### Advanced Features

#### Multi-LLM Provider System

Prod_Layer supports 12+ AI providers through LiteLLM:

- **Fast Models**: Groq Llama 3.3 70B, Mistral Small, GPT-4o Mini, Gemini 2.0 Flash
- **Powerful Models**: DeepSeek Chat, Claude Sonnet, GPT-4o, Grok 2, Together Llama 3.3 70B
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
PROD_LAYER/
├── main.js                          # Electron main process
├── package.json                     # Node dependencies
├── requirements.txt                 # Python dependencies
├── .env                             # API keys (not committed)
├── config.example.env               # Example config
├── src/
│   ├── main/
│   │   └── keystore.js              # Encrypted API key storage
│   ├── python/                      # Python services
│   │   ├── ai_backend_service.py    # Persistent AI backend with streaming
│   │   ├── keyboard_inject.py       # Text injection (pynput)
│   │   ├── screenshot_vision.py     # Vision AI (Gemini)
│   │   ├── voice_transcribe.py      # Speech recognition
│   │   ├── smart_prompts.py         # Context-aware prompting
│   │   ├── human_typer.py           # Human-like code typing
│   │   ├── keystroke_monitor.py     # Monitor entry point
│   │   ├── providers/               # Multi-LLM provider system
│   │   │   ├── __init__.py          # ProviderManager interface
│   │   │   ├── router.py           # Model routing and discovery
│   │   │   ├── context.py          # Smart routing logic
│   │   │   └── memory.py           # Per-window memory management
│   │   └── keystroke_monitor/       # Monitor package
│   └── renderer/                    # Electron frontend
│       ├── lib/
│       │   └── marked.min.js       # Markdown parser
│       ├── chat.html               # Persistent chat interface
│       ├── chat_renderer.js        # Chat window logic
│       ├── index.html              # Main overlay UI
│       ├── output.html             # Suggestion popup
│       ├── explanation.html        # Code explanation window
│       ├── settings.html           # Settings UI
│       ├── styles.css              # Styles
│       ├── renderer.js             # Frontend logic
│       └── settings_renderer.js    # Settings logic
├── tests/                           # Test suite
│   ├── test_ai_backend_service.py  # AI backend tests
│   ├── test_memory.py              # Memory system tests
│   ├── test_providers.py           # Provider system tests
│   └── test_smart_routing.py       # Routing logic tests
├── tools/                           # Dev and analysis scripts
├── data/                            # Runtime-generated files
│   ├── chats/                      # Persistent chat history
│   └── memory/                     # Per-window conversation memory
└── docs/                            # Documentation
```

## Requirements

- Node.js 16+
- Python 3.8+
- Windows 10/11 (primary support)
- macOS/Linux (partial support)

## API Keys

Create `.env` file with your API keys. Prod_Layer supports 12+ providers:

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

Get keys from:
- **Mistral**: https://console.mistral.ai/api-keys/
- **Groq**: https://console.groq.com/keys
- **DeepSeek**: https://platform.deepseek.com/api-keys
- **Anthropic**: https://console.anthropic.com/settings/keys
- **OpenAI**: https://platform.openai.com/api-keys
- **Gemini**: https://makersuite.google.com/app/apikey
- **Together AI**: https://www.together.ai/
- **Perplexity**: https://www.perplexity.ai/
- **Cohere**: https://dashboard.cohere.com/api-keys
- **Replicate**: https://replicate.com/account

Keys can also be configured through the Settings UI (`Ctrl+Shift+S`).

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
