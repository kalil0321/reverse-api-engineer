# Reverse API Engineer - Cloud Implementation Plan

## Overview

This document outlines the implementation strategy for building a cloud-based version of Reverse API Engineer. The main challenges are:

1. **Cloud Browser with HAR Recording** - Providing users with a remote browser they can interact with while capturing network traffic
2. **Sandbox Environment** - Running the AI engineer in an isolated environment with access to HAR files

---

## Architecture Options

### Option A: Unified Fly.io Sprite (Recommended)

```
┌─────────────────────────────────────────────────────────────────┐
│                         Next.js Frontend                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Browser View │  │  Chat Panel  │  │  Generated Scripts   │  │
│  │  (VNC/noVNC) │  │              │  │      Preview         │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend API (Next.js)                       │
│  ┌──────────────────────┐  ┌────────────────────────────────┐  │
│  │  Session Management  │  │  Sprite Orchestration API      │  │
│  └──────────────────────┘  └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Fly.io Sprite (per user)                    │
│  ┌──────────────────────┐  ┌────────────────────────────────┐  │
│  │  Playwright Browser  │  │   Reverse API Engineer         │  │
│  │  - HAR recording     │  │   - Claude pre-installed       │  │
│  │  - VNC streaming     │  │   - Persistent environment     │  │
│  │  - Anti-detection    │  │   - Checkpoint/restore         │  │
│  └──────────────────────┘  └────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  100GB NVMe Storage (persistent, billed per block used)  │  │
│  │  - HAR files in /workspace/har/                          │  │
│  │  - Scripts in /workspace/scripts/                        │  │
│  │  - Checkpoints at /.sprite/checkpoints/                  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Pros:**
- Single service - browser and sandbox in one VM
- Persistent state - no environment rebuild between sessions
- Checkpoint/restore in ~300ms - rollback if something breaks
- Claude, Gemini, Codex pre-installed
- 100GB storage, only pay for blocks written
- Auto-idle stops billing but preserves state
- Cheaper than E2B (~$0.02/hr vs ~$0.05/hr)
- No Docker images needed

**Cons:**
- Need to implement VNC streaming for browser view
- Slightly slower cold start (1-12s vs E2B's 400ms)

### Option B: Cloud Browser + Separate Sprite

```
┌─────────────────────────────────────────────────────────────────┐
│                         Next.js Frontend                         │
└─────────────────────────────────────────────────────────────────┘
                    │                         │
                    ▼                         ▼
┌────────────────────────────┐    ┌──────────────────────────────┐
│    Browserbase             │    │      Fly.io Sprite           │
│  - Live streaming          │    │  - Claude pre-installed      │
│  - HAR recording           │    │  - Persistent state          │
│  - Managed service         │    │  - Checkpoint/restore        │
└────────────────────────────┘    └──────────────────────────────┘
```

**Pros:**
- Better browser streaming UX (Browserbase native embed)
- Separation of concerns

**Cons:**
- Two services to manage
- Need to transfer HAR files between services
- Higher cost

---

## Recommended Approach: Option A (Unified Sprite)

### Why Fly.io Sprites over E2B?

| Feature | Fly.io Sprites | E2B |
|---------|---------------|-----|
| **State Persistence** | Survives idle, resumes instantly | Ephemeral, rebuilds each time |
| **Checkpoint/Restore** | 300ms snapshots, last 5 auto-mounted | Not built-in |
| **Pricing** | ~$0.02/hr, pay only for blocks written | ~$0.05/hr, pay for allocated |
| **Storage** | 100GB NVMe, TRIM-friendly billing | Limited, Docker-based |
| **Docker Required** | No | Yes |
| **Pre-installed AI** | Claude, Gemini, Codex | Manual setup required |
| **Idle Billing** | Stops billing, preserves state | Session ends, state lost |
| **Cold Start** | 1-12 seconds | ~400ms |

**Key insight**: Sprites are designed for exactly our use case - persistent coding agent environments. The agent can install packages once, process multiple HAR files across sessions, and checkpoint before risky operations.

---

## Phase 1: Sprite Setup

### Sprite Configuration

```typescript
// Sprite creation via Fly.io API
interface SpriteConfig {
  name: string;           // User-specific sprite
  size: 'shared-cpu-1x';  // Start small
  region: 'ord';          // Chicago (or nearest)
  env: {
    ANTHROPIC_API_KEY: string;
  };
}
```

### Pre-installed Environment

Sprites come with Claude pre-installed. We'll add:
- Playwright with Chromium
- Python 3.11+ with our dependencies
- VNC server for browser streaming
- Reverse API Engineer CLI

```bash
# Sprite init script
playwright install chromium
pip install reverse-api-engineer httpx anthropic
```

### Checkpoint Strategy

```typescript
// Checkpoint before risky operations
async function safeOperation(sprite: Sprite, operation: () => Promise<void>) {
  await sprite.checkpoint('before-operation');
  try {
    await operation();
  } catch (error) {
    await sprite.restore('before-operation');
    throw error;
  }
}
```

---

## Phase 2: Browser Integration

### VNC Streaming Setup

Since Sprites run a full Linux environment, we can use VNC for browser streaming:

```typescript
// Sprite runs VNC server
// x11vnc -display :0 -forever -shared -rfbport 5900

// Frontend connects via noVNC (WebSocket to VNC bridge)
interface BrowserViewProps {
  spriteId: string;
  vncUrl: string;  // wss://sprite-{id}.fly.dev:5900
}
```

### HAR Recording

```typescript
// Inside Sprite - Playwright with HAR recording
import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: false });
const context = await browser.newContext({
  recordHar: {
    path: '/workspace/har/session.har',
    mode: 'full',
    content: 'embed'
  }
});

// User interacts via VNC...

await context.close();  // HAR file saved
```

### Browser Control API

```typescript
// POST /api/sprite/{id}/browser/start
interface StartBrowserRequest {
  url?: string;  // Initial URL
}

// POST /api/sprite/{id}/browser/stop
interface StopBrowserResponse {
  harPath: string;  // /workspace/har/session.har
}

// GET /api/sprite/{id}/browser/vnc
// Returns WebSocket URL for noVNC connection
```

---

## Phase 3: Engineer Integration

### Running the Engineer

```typescript
// POST /api/sprite/{id}/engineer/run
interface RunEngineerRequest {
  harPath: string;
  prompt?: string;
}

// Sprite executes:
// 1. Load HAR from /workspace/har/
// 2. Create checkpoint before generation
// 3. Run reverse-api-engineer with Claude
// 4. Stream progress via WebSocket
// 5. Save scripts to /workspace/scripts/
```

### Streaming Output

```typescript
// WebSocket connection for real-time output
const ws = new WebSocket(`wss://api/sprite/${spriteId}/engineer/stream`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  switch (data.type) {
    case 'progress':
      updateProgress(data.message);
      break;
    case 'code':
      displayCode(data.content);
      break;
    case 'complete':
      showDownloadButton(data.scriptPath);
      break;
  }
};
```

---

## Phase 4: Frontend Implementation

### Pages Structure

```
src/app/
├── page.tsx                    # Landing page
├── dashboard/
│   └── page.tsx               # User's sprites and sessions
├── sprite/
│   └── [id]/
│       ├── page.tsx           # Active sprite view
│       ├── browser/           # VNC browser view
│       │   └── page.tsx
│       └── engineer/          # Engineer chat + results
│           └── page.tsx
└── api/
    ├── sprite/
    │   ├── route.ts           # Create/list sprites
    │   └── [id]/
    │       ├── browser/
    │       │   ├── start/route.ts
    │       │   ├── stop/route.ts
    │       │   └── vnc/route.ts
    │       ├── engineer/
    │       │   ├── run/route.ts
    │       │   └── stream/route.ts
    │       ├── checkpoint/route.ts
    │       └── files/route.ts
    └── auth/
        └── [...nextauth]/route.ts
```

### Key Components

1. **VNCViewer** - Browser view via noVNC
   ```typescript
   // Uses @novnc/novnc or react-vnc
   // Full-screen browser interaction
   // Controls: URL bar, back/forward, stop recording
   ```

2. **EngineerChat** - Chat interface for engineer
   ```typescript
   // Real-time streaming output
   // Token usage and cost display
   // Code preview with syntax highlighting
   ```

3. **CheckpointManager** - Manage sprite checkpoints
   ```typescript
   // List checkpoints at /.sprite/checkpoints/
   // One-click restore
   // Create manual checkpoints
   ```

4. **FileExplorer** - Browse sprite filesystem
   ```typescript
   // View /workspace/har/ and /workspace/scripts/
   // Download files
   // Delete old sessions
   ```

---

## Data Flow

### Complete Session Flow

```
1. User logs in
   └── Check for existing Sprite
       └── Create new Sprite if none exists (1-12s cold start)
       └── Or resume existing Sprite instantly

2. User clicks "Start Capture"
   └── POST /api/sprite/{id}/browser/start
       └── Launch Playwright with HAR recording
       └── Start VNC server
       └── Return VNC WebSocket URL

3. Browser view loads
   └── noVNC connects to Sprite VNC
       └── User interacts with browser
       └── All traffic recorded to HAR

4. User clicks "Stop & Generate"
   └── POST /api/sprite/{id}/browser/stop
       └── Close browser, save HAR
       └── Create checkpoint (300ms)

5. Run engineer
   └── POST /api/sprite/{id}/engineer/run
       └── WebSocket streams progress
       └── Engineer analyzes HAR with Claude
       └── Scripts saved to /workspace/scripts/

6. Download scripts
   └── GET /api/sprite/{id}/files?path=/workspace/scripts/
       └── Return generated Python scripts

7. Sprite idles (auto after inactivity)
   └── Billing stops
   └── State preserved
   └── Resumes instantly on next request
```

---

## Technology Stack

### Frontend
- **Next.js 16** - App router, server components
- **Tailwind CSS** - Styling
- **shadcn/ui** - UI components
- **Monaco Editor** - Code display
- **noVNC** - VNC client for browser view
- **Zustand** - Client state management

### Backend
- **Next.js API Routes** - API layer
- **Fly.io Sprites API** - Sprite management
- **Supabase / Postgres** - User data, session metadata

### Authentication
- **NextAuth.js** with GitHub/Google providers
- Or **Clerk** for managed auth

### Infrastructure
- **Vercel** - Next.js hosting
- **Fly.io Sprites** - Persistent sandboxes with browser
- **Supabase** - Database (free tier)

---

## Cost Estimation

### Per Session Estimate

| Component | Usage | Cost |
|-----------|-------|------|
| Fly.io Sprite | 15 min active | ~$0.005 |
| Sprite Storage | ~10MB HAR + scripts | ~$0.001 |
| Claude API | ~50k tokens | ~$0.15 |
| **Total** | | **~$0.16/session** |

*Note: Sprites auto-idle and stop billing. Storage only charges for blocks written.*

### Monthly Infrastructure

| Service | Plan | Cost |
|---------|------|------|
| Vercel | Pro | $20/mo |
| Fly.io Sprites | Pay-as-you-go | ~$5-20/mo* |
| Supabase | Free | $0 |
| **Total** | | **~$25-40/mo base** |

*Depends on usage. Sprites idle automatically.*

### Cost Comparison: Sprites vs E2B

| Scenario | Fly.io Sprites | E2B |
|----------|---------------|-----|
| 100 sessions/month | ~$16 | ~$22 |
| 1000 sessions/month | ~$160 | ~$220 |
| Idle sprite (24h) | ~$0 | N/A (session ends) |

---

## Implementation Phases

### Phase 1: MVP
- [ ] Basic Next.js 16 app with auth
- [ ] Fly.io Sprite creation/management
- [ ] VNC streaming with noVNC
- [ ] Playwright HAR recording in Sprite
- [ ] Basic engineer execution
- [ ] File download

### Phase 2: Polish
- [ ] Better VNC controls (URL bar, zoom)
- [ ] Checkpoint management UI
- [ ] Session history
- [ ] Script preview with Monaco
- [ ] Usage tracking

### Phase 3: Advanced Features
- [ ] Agent mode (browser-use in Sprite)
- [ ] Re-engineer from previous HAR
- [ ] Team sharing
- [ ] Custom Sprite templates
- [ ] Webhook integrations

---

## Open Questions

1. **VNC latency** - Is noVNC good enough for interactive browsing?
2. **Sprite per user vs shared pool?** - Trade-off between isolation and cost
3. **Checkpoint retention** - How many checkpoints to keep?
4. **Multi-browser sessions** - Support multiple HAR captures per Sprite?
5. **Local development** - Fly.io plans open-source local Sprites

---

## Alternatives Considered

### E2B instead of Sprites
- Faster cold start (400ms vs 1-12s)
- But ephemeral - loses state between sessions
- More expensive ($0.05/hr vs $0.02/hr)
- Requires Docker images
- No checkpoint/restore

### Browserbase + Sprites (Hybrid)
- Better browser streaming UX
- But adds complexity and cost
- HAR transfer between services
- Consider if VNC latency is unacceptable

### Modal.com
- More powerful, GPU support
- Higher learning curve
- Consider for compute-intensive features later

---

## References

- [Fly.io Sprites Announcement](https://fly.io/blog/code-and-let-live/)
- [Sprites Design & Implementation](https://fly.io/blog/design-and-implementation/)
- [Fly.io Pricing](https://fly.io/pricing/)
- [noVNC - HTML5 VNC Client](https://novnc.com/)
- [Playwright HAR Recording](https://playwright.dev/docs/network#record-and-replay-requests)

---

## Next Steps

1. Create Fly.io account and test Sprite creation
2. Set up Playwright + VNC in a Sprite
3. Test noVNC integration from Next.js
4. Implement basic session flow
5. Add authentication with NextAuth
6. Build VNC viewer component
7. Build engineer chat component
8. Test end-to-end flow
