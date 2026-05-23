"""Design tokens for the CLI, aligned with System_Design.md (dark / terminal)."""

# Core palette (website dark mode)
COLOR_INK = "#fff7f0"
COLOR_INK_SOFT = "#c9bdb3"
COLOR_CREAM = "#14110e"
COLOR_CREAM_SOFT = "#1c1814"
COLOR_WASHED = "#1a1612"
COLOR_ORANGE = "#3a1d0e"
COLOR_MINT = "#7ec99a"
COLOR_SKY = "#7eb8ff"
COLOR_PRIMARY = "#ff3d8b"
COLOR_PRIMARY_ALT = "#e50d75"

# Rich / prompt styling aliases
THEME_PRIMARY = COLOR_PRIMARY
THEME_SECONDARY = COLOR_INK
THEME_DIM = "#8a7d72"
THEME_SUCCESS = COLOR_MINT
THEME_ERROR = f"bold {COLOR_INK} on {COLOR_PRIMARY_ALT}"

MODE_COLORS = {
    "agent": COLOR_PRIMARY,
    "manual": COLOR_MINT,
    "engineer": COLOR_SKY,
    "collector": "#e8b86d",
}

BRAND_MARK = "*"
BRAND_WORDMARK = "rae"
APP_TAGLINE = "Turn websites into APIs."
