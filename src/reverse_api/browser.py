"""Browser management with Playwright for HAR recording."""

import json
import random
import signal
import sys
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from playwright_stealth import Stealth
from rich.console import Console
from rich.status import Status

from .utils import get_har_dir, get_timestamp
from .tui import THEME_PRIMARY, THEME_DIM, THEME_SUCCESS

console = Console()

# Realistic Chrome user agents (updated for late 2024/2025)
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

# Stealth JavaScript to inject - bypasses common detection methods
STEALTH_JS = """
// Override navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
});

// Override navigator.plugins to look like a real browser
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
        ];
        plugins.item = (index) => plugins[index];
        plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
        plugins.refresh = () => {};
        return plugins;
    },
});

// Override navigator.languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});

// Override navigator.permissions.query for notifications
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => {
    if (parameters.name === 'notifications') {
        return Promise.resolve({ state: Notification.permission });
    }
    return originalQuery(parameters);
};

// Remove automation-related properties from window
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Object;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Proxy;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;

// Override chrome runtime to look authentic
if (!window.chrome) {
    window.chrome = {};
}
window.chrome.runtime = {
    PlatformOs: { MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd' },
    PlatformArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
    PlatformNaclArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
    RequestUpdateCheckStatus: { THROTTLED: 'throttled', NO_UPDATE: 'no_update', UPDATE_AVAILABLE: 'update_available' },
    OnInstalledReason: { INSTALL: 'install', UPDATE: 'update', CHROME_UPDATE: 'chrome_update', SHARED_MODULE_UPDATE: 'shared_module_update' },
    OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
};

// Fix iframe contentWindow detection
const originalAttachShadow = Element.prototype.attachShadow;
Element.prototype.attachShadow = function(init) {
    if (init && init.mode === 'closed') {
        init.mode = 'open';
    }
    return originalAttachShadow.call(this, init);
};

// Override WebGL vendor/renderer to look consistent
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) { // UNMASKED_VENDOR_WEBGL
        return 'Google Inc. (Apple)';
    }
    if (parameter === 37446) { // UNMASKED_RENDERER_WEBGL
        return 'ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro, Unspecified Version)';
    }
    return getParameter.call(this, parameter);
};

// Do the same for WebGL2
const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
WebGL2RenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) {
        return 'Google Inc. (Apple)';
    }
    if (parameter === 37446) {
        return 'ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro, Unspecified Version)';
    }
    return getParameter2.call(this, parameter);
};

// Override Permissions API
const originalPermissionsQuery = navigator.permissions.query;
navigator.permissions.query = function(permissionDesc) {
    if (permissionDesc.name === 'notifications') {
        return Promise.resolve({
            state: 'prompt',
            onchange: null
        });
    }
    return originalPermissionsQuery.call(navigator.permissions, permissionDesc);
};

// Spoof hardwareConcurrency to a realistic value
Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 8,
});

// Spoof deviceMemory
Object.defineProperty(navigator, 'deviceMemory', {
    get: () => 8,
});

// Spoof connection info
if (navigator.connection) {
    Object.defineProperty(navigator.connection, 'rtt', {
        get: () => 50,
    });
}

// Hide automation in chrome.app
if (window.chrome && window.chrome.app) {
    window.chrome.app.isInstalled = false;
    window.chrome.app.InstallState = { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' };
    window.chrome.app.RunningState = { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' };
}

console.log('Stealth mode activated');
"""


# Default Chrome profile path on macOS
CHROME_USER_DATA_DIR = Path.home() / "Library/Application Support/Google/Chrome"


def get_chrome_profile_dir() -> Path | None:
    """Get Chrome user data directory if it exists."""
    if CHROME_USER_DATA_DIR.exists():
        return CHROME_USER_DATA_DIR
    return None


class ManualBrowser:
    """Manages a Playwright browser session with HAR recording.
    
    Supports two modes:
    - Real Chrome: Uses your actual Chrome browser with existing profile (best for stealth)
    - Stealth Chromium: Falls back to Playwright's Chromium with stealth patches
    """

    def __init__(
        self, 
        run_id: str, 
        prompt: str, 
        output_dir: str | None = None,
        use_real_chrome: bool = True,  # New option to use real Chrome
    ):
        self.run_id = run_id
        self.prompt = prompt
        self.output_dir = output_dir
        self.use_real_chrome = use_real_chrome
        self.har_dir = get_har_dir(run_id, output_dir)
        self.har_path = self.har_dir / "recording.har"
        self.metadata_path = self.har_dir / "metadata.json"
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._start_time: Optional[str] = None
        self._user_agent = random.choice(USER_AGENTS)
        self._using_persistent = False  # Track if using persistent context

    def _save_metadata(self, end_time: str) -> None:
        """Save run metadata to JSON file."""
        metadata = {
            "run_id": self.run_id,
            "prompt": self.prompt,
            "start_time": self._start_time,
            "end_time": end_time,
            "har_file": str(self.har_path),
        }
        with open(self.metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

    def _handle_signal(self, signum, frame) -> None:
        """Handle interrupt signals gracefully."""
        console.print(f"\n\n [dim]terminating capture...[/dim]")
        self.close()
        sys.exit(0)

    def _inject_stealth(self, page: Page) -> None:
        """Inject stealth scripts into page before any other scripts run."""
        page.add_init_script(STEALTH_JS)

    def _start_with_real_chrome(self, start_url: Optional[str] = None) -> Path:
        """Start using the real Chrome browser with user's profile."""
        # We need to use a COPY of the profile to avoid locking issues
        # Chrome locks its profile when running, so we can't use it directly
        import shutil
        import tempfile
        
        chrome_profile = get_chrome_profile_dir()
        if not chrome_profile:
            console.print(f" [yellow]chrome profile not found, falling back to stealth mode[/yellow]")
            return self._start_with_stealth_chromium(start_url)
        
        # Create a temporary profile directory
        temp_profile_dir = Path(tempfile.mkdtemp(prefix="chrome_profile_"))
        
        console.print(f" [dim]using real chrome (profile copy)[/dim]")
        console.print(f" [dim]note: close chrome if you have it open[/dim]")
        console.print()
        
        try:
            # Use launch_persistent_context with channel="chrome" to use real Chrome binary
            # This gives us the real Chrome with a fresh profile that has all extensions/settings
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(temp_profile_dir),
                channel="chrome",  # Use real Chrome binary
                headless=False,
                record_har_path=str(self.har_path),
                record_har_content="attach",
                no_viewport=True,
                args=[
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                ],
                ignore_default_args=["--enable-automation", "--no-sandbox"],
            )
            self._using_persistent = True
            
            # Get or create page
            if self._context.pages:
                page = self._context.pages[0]
            else:
                page = self._context.new_page()
            
            if start_url:
                page.goto(start_url, wait_until="domcontentloaded")
            
            # Wait for browser to close
            try:
                while self._context.pages:
                    self._context.pages[0].wait_for_timeout(100)  # Faster polling
            except Exception:
                pass
            
            return self.close()
            
        finally:
            # Clean up temp profile
            try:
                shutil.rmtree(temp_profile_dir, ignore_errors=True)
            except Exception:
                pass

    def _start_with_stealth_chromium(self, start_url: Optional[str] = None) -> Path:
        """Start using Playwright's Chromium with stealth patches."""
        # Comprehensive stealth Chrome arguments
        chrome_args = [
            "--start-maximized",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-extensions",
            "--disable-sync",
            "--disable-translate",
            "--no-first-run",
            "--no-default-browser-check",
            "--no-service-autorun",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
            "--disable-ipc-flooding-protection",
            "--disable-hang-monitor",
            "--disable-prompt-on-repost",
            "--disable-client-side-phishing-detection",
            "--disable-webrtc-hw-encoding",
            "--disable-webrtc-hw-decoding",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--enable-features=NetworkService,NetworkServiceInProcess",
            "--disable-component-update",
            "--disable-domain-reliability",
            "--disable-features=AutofillServerCommunication",
            "--password-store=basic",
            "--use-mock-keychain",
        ]
        
        self._browser = self._playwright.chromium.launch(
            headless=False,
            args=chrome_args,
            ignore_default_args=["--enable-automation", "--no-sandbox"],
        )
        
        # Create context with HAR recording and realistic settings
        self._context = self._browser.new_context(
            record_har_path=str(self.har_path),
            record_har_content="attach",
            no_viewport=True,
            locale="en-US",
            timezone_id="America/New_York",
            user_agent=self._user_agent,
            screen={"width": 1920, "height": 1080},
            color_scheme="light",
            reduced_motion="no-preference",
            forced_colors="none",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
            },
        )
        
        # Apply playwright-stealth evasions
        stealth = Stealth()
        stealth.apply_stealth_sync(self._context)
        
        # Add custom stealth init script
        self._context.add_init_script(STEALTH_JS)

        # Open initial page
        page = self._context.new_page()
        
        if start_url:
            page.goto(start_url, wait_until="domcontentloaded")

        # Wait for browser to close
        try:
            while self._context.pages:
                self._context.pages[0].wait_for_timeout(100)  # Faster polling
        except Exception:
            pass

        return self.close()

    def start(self, start_url: Optional[str] = None) -> Path:
        """Start the browser with HAR recording enabled. Returns HAR path when done."""
        self._start_time = get_timestamp()
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        console.print(f" [dim]capture starting...[/dim]")
        console.print(f" [dim]━[/dim] [white]{self.run_id}[/white]")
        console.print(f" [dim]goal[/dim]  [white]{self.prompt}[/white]")
        console.print()
        console.print(f" [dim]navigate and interact to record traffic[/dim]")
        console.print(f" [dim]close browser or ctrl+c to finalize[/dim]")
        console.print()

        self._playwright = sync_playwright().start()
        
        # Try real Chrome first, fall back to stealth Chromium
        if self.use_real_chrome:
            return self._start_with_real_chrome(start_url)
        else:
            return self._start_with_stealth_chromium(start_url)

    def close(self) -> Path:
        """Close the browser and save HAR file. Returns HAR path."""
        end_time = get_timestamp()
        
        console.print(f" [dim]browser closed[/dim]")
        
        if self._context:
            with Status(" [dim]handling har... can take a bit[/dim]", console=console, spinner="dots") as status:
                try:
                    status.update(" [dim]saving har file...[/dim]")
                    self._context.close()  # This saves the HAR file
                except Exception:
                    pass
                self._context = None

        # Only close browser if not using persistent context
        if self._browser and not self._using_persistent:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        # Save metadata
        self._save_metadata(end_time)
        
        console.print(f" [dim]capture saved[/dim]")
        console.print(f" [dim]metadata synced[/dim]")
        
        return self.har_path
