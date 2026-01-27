# Reverse API Engineer - Cloud Implementation Plan

## Overview

This document outlines the implementation strategy for building a cloud-based version of Reverse API Engineer. The main challenges are:

1. **Cloud Browser with HAR Recording** - Providing users with a remote browser they can interact with while capturing network traffic
2. **Sandbox Environment** - Running the AI engineer in an isolated environment with access to HAR files

## Architecture Options

### Option A: Cloud Browser + Separate Sandbox (Recommended)

```
┌─────────────────────────────────────────────────────────────────┐
│                         Next.js Frontend                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Browser View │  │  Chat Panel  │  │  Generated Scripts   │  │
│  │  (WebSocket) │  │              │  │      Preview         │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend API (Next.js)                       │
│  ┌──────────────────────┐  ┌────────────────────────────────┐  │
│  │  Session Management  │  │  File Storage (S3/R2/Supabase) │  │
│  └──────────────────────┘  └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                    │                         │
                    ▼                         ▼
┌────────────────────────────┐    ┌──────────────────────────────┐
│    Cloud Browser Service   │    │      Code Sandbox Service    │
│  ┌──────────────────────┐  │    │  ┌────────────────────────┐  │
│  │     Browserbase      │  │    │  │    E2B.dev Sandbox     │  │
│  │    (HAR Recording)   │  │    │  │  - Python runtime      │  │
│  │  - Live streaming    │  │    │  │  - Claude SDK          │  │
│  │  - User interaction  │  │    │  │  - File system access  │  │
│  └──────────────────────┘  │    │  └────────────────────────┘  │
└────────────────────────────┘    └──────────────────────────────┘
```

**Pros:**
- Best separation of concerns
- Can scale browser and sandbox independently
- Browserbase handles browser complexity
- E2B provides secure code execution

**Cons:**
- Two external services to manage
- Need to transfer HAR files between services

### Option B: Unified Sandbox with Cloud Browser

```
┌─────────────────────────────────────────────────────────────────┐
│                         Next.js Frontend                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   E2B Sandbox (Desktop Template)                 │
│  ┌──────────────────────┐  ┌────────────────────────────────┐  │
│  │  Playwright Browser  │  │   Reverse API Engineer CLI     │  │
│  │  (with HAR capture)  │  │   (running in sandbox)         │  │
│  └──────────────────────┘  └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Pros:**
- Single service, simpler architecture
- HAR files already in the same filesystem
- Closer to CLI experience

**Cons:**
- E2B desktop sandbox is more expensive
- Less flexible browser interaction (no native streaming)
- Heavier sandbox instances

---

## Recommended Approach: Option A

### Phase 1: Cloud Browser Integration

#### Service Selection: Browserbase

[Browserbase](https://browserbase.com) provides:
- Playwright-compatible cloud browsers
- Built-in HAR recording via CDP
- Live session streaming via WebSocket
- Stealth mode and anti-detection

#### Implementation Steps

1. **Browser Session API**
   ```typescript
   // POST /api/browser/session
   // Creates a new Browserbase session with HAR recording enabled

   interface CreateSessionResponse {
     sessionId: string;
     connectUrl: string;      // WebSocket URL for live view
     debuggerUrl: string;     // CDP endpoint for HAR recording
   }
   ```

2. **Browser Live View Component**
   ```typescript
   // Use Browserbase's embed or custom WebSocket streaming
   // Options:
   // - Browserbase embed iframe (simplest)
   // - noVNC for VNC-based streaming
   // - Custom WebSocket with canvas rendering
   ```

3. **HAR Recording**
   ```typescript
   // Browserbase supports HAR via:
   // 1. Built-in recording (session.recording)
   // 2. CDP Network domain events
   // 3. Playwright's page.routeFromHAR() in record mode

   // On session end:
   // - Download HAR from Browserbase
   // - Store in S3/R2 with session ID
   ```

#### Alternative: Self-hosted Playwright

If cost is a concern, run Playwright in containers:
- Use [browserless.io](https://browserless.io) for managed Playwright
- Or deploy Playwright containers on Fly.io/Railway
- Implement VNC streaming with noVNC

### Phase 2: Code Sandbox Integration

#### Service Selection: E2B

[E2B](https://e2b.dev) provides:
- Secure sandboxed environments
- Python runtime with pip
- File system access
- 24-hour sandbox lifetime

#### Implementation Steps

1. **Custom Sandbox Template**
   ```dockerfile
   # e2b.Dockerfile
   FROM e2b/base

   # Install Python and dependencies
   RUN pip install anthropic httpx

   # Copy engineer code (or install from pip)
   COPY src/reverse_api /app/reverse_api
   ```

2. **Sandbox API**
   ```typescript
   // POST /api/sandbox/create
   // Creates E2B sandbox with HAR files uploaded

   interface CreateSandboxRequest {
     harSessionId: string;    // Reference to stored HAR
   }

   interface CreateSandboxResponse {
     sandboxId: string;
     status: 'ready' | 'initializing';
   }
   ```

3. **Engineer Execution**
   ```typescript
   // POST /api/sandbox/{id}/run
   // Runs the engineer with streaming output

   // Sandbox executes:
   // 1. Load HAR files from /workspace/har/
   // 2. Run engineer.py with Claude API
   // 3. Stream progress back via WebSocket
   // 4. Save generated scripts to /workspace/scripts/
   ```

4. **Script Download**
   ```typescript
   // GET /api/sandbox/{id}/scripts
   // Downloads generated Python scripts as zip
   ```

### Phase 3: Frontend Implementation

#### Pages Structure

```
src/app/
├── page.tsx                    # Landing page
├── dashboard/
│   └── page.tsx               # User's sessions list
├── session/
│   ├── new/
│   │   └── page.tsx           # Start new capture
│   └── [id]/
│       ├── page.tsx           # Active session view
│       ├── browser/           # Browser interaction
│       └── engineer/          # Engineer chat + results
└── api/
    ├── browser/
    │   ├── session/route.ts   # Create/manage browser sessions
    │   └── har/route.ts       # Download HAR files
    ├── sandbox/
    │   ├── route.ts           # Create sandbox
    │   └── [id]/
    │       ├── run/route.ts   # Run engineer
    │       └── scripts/route.ts # Download scripts
    └── auth/
        └── [...nextauth]/route.ts
```

#### Key Components

1. **BrowserView** - Live browser streaming
   ```typescript
   // Uses iframe embed or WebSocket canvas
   // Controls: URL bar, back/forward, stop recording
   ```

2. **EngineerChat** - Chat interface for engineer
   ```typescript
   // Similar to CLI interface
   // Shows progress, token usage, costs
   // Displays generated code with syntax highlighting
   ```

3. **ScriptPreview** - View and download generated scripts
   ```typescript
   // Monaco editor for viewing
   // Download as zip
   // Copy to clipboard
   ```

---

## Data Flow

### Capture Flow

```
1. User clicks "Start Capture"
   └── POST /api/browser/session
       └── Create Browserbase session with HAR recording

2. Browser view loads
   └── WebSocket connection to Browserbase
       └── User interacts with browser

3. User clicks "Stop & Generate"
   └── POST /api/browser/session/{id}/stop
       └── Download HAR from Browserbase
       └── Store HAR in S3/R2
       └── Return harSessionId

4. Create sandbox
   └── POST /api/sandbox/create
       └── Create E2B sandbox
       └── Upload HAR files to sandbox

5. Run engineer
   └── POST /api/sandbox/{id}/run (WebSocket)
       └── Execute engineer in sandbox
       └── Stream progress to frontend

6. Download scripts
   └── GET /api/sandbox/{id}/scripts
       └── Return generated Python scripts
```

---

## Technology Stack

### Frontend
- **Next.js 15** - App router, server components
- **Tailwind CSS** - Styling
- **shadcn/ui** - UI components
- **Monaco Editor** - Code display
- **Zustand** - Client state management

### Backend
- **Next.js API Routes** - API layer
- **Browserbase SDK** - Cloud browser management
- **E2B SDK** - Sandbox management
- **Cloudflare R2 / AWS S3** - HAR file storage
- **Supabase / Postgres** - Session metadata

### Authentication
- **NextAuth.js** with GitHub/Google providers
- Or **Clerk** for managed auth

### Infrastructure
- **Vercel** - Next.js hosting
- **Browserbase** - Cloud browsers
- **E2B** - Code sandboxes
- **Cloudflare R2** - File storage (free egress)

---

## Cost Estimation

### Per Session Estimate

| Service | Usage | Cost |
|---------|-------|------|
| Browserbase | 5 min session | ~$0.05 |
| E2B Sandbox | 10 min runtime | ~$0.02 |
| Claude API | ~50k tokens | ~$0.15 |
| R2 Storage | 1 MB HAR | ~$0.00 |
| **Total** | | **~$0.22/session** |

### Monthly Infrastructure

| Service | Plan | Cost |
|---------|------|------|
| Vercel | Pro | $20/mo |
| Browserbase | Starter | $0 (100 sessions) |
| E2B | Hobby | $0 (100 hours) |
| R2 | Free tier | $0 |
| Supabase | Free | $0 |
| **Total** | | **~$20/mo base** |

---

## Implementation Phases

### Phase 1: MVP (2-3 weeks)
- [ ] Basic Next.js app with auth
- [ ] Browserbase integration (create session, embed view)
- [ ] HAR download and storage
- [ ] E2B sandbox with engineer
- [ ] Basic chat UI for engineer output

### Phase 2: Polish (1-2 weeks)
- [ ] Better browser controls (URL bar, navigation)
- [ ] Session history and management
- [ ] Script preview with syntax highlighting
- [ ] Download scripts as zip
- [ ] Usage tracking and limits

### Phase 3: Advanced Features (2-3 weeks)
- [ ] Agent mode (browser-use in cloud)
- [ ] Re-engineer from previous HAR
- [ ] Team sharing and collaboration
- [ ] Custom sandbox templates
- [ ] Webhook integrations

---

## Open Questions

1. **Browser streaming quality** - iframe embed vs custom WebSocket?
2. **Sandbox persistence** - How long to keep sandboxes alive?
3. **HAR storage** - Keep indefinitely or time-limited?
4. **Pricing model** - Per session? Subscription? Free tier limits?
5. **Agent mode complexity** - Worth implementing in v1?

---

## Alternatives Considered

### Browserless.io instead of Browserbase
- Similar features, different pricing
- Less native HAR support
- Consider if Browserbase pricing is prohibitive

### Modal.com instead of E2B
- More powerful, GPU support
- Higher learning curve
- Consider for future scaling

### Fly.io Machines
- Self-managed containers
- More control, more complexity
- Consider for cost optimization later

---

## Next Steps

1. Create Browserbase account and test session creation
2. Create E2B account and build custom sandbox template
3. Implement basic session flow in Next.js
4. Add authentication with NextAuth
5. Build browser view component
6. Build engineer chat component
7. Test end-to-end flow
