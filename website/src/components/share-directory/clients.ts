// Directory of clients & CLIs built with rae.
//
// PLACEHOLDER DATA. When this page is wired up for real, this array becomes the
// committed data source populated via "Submit your client" pull requests (the
// submission/cloud logic is still TBD — that's why the page isn't shipped yet).

export type Category = 'AI' | 'Music' | 'Social' | 'Finance' | 'Shopping' | 'Dev';

export type RaeClient = {
  slug: string;
  service: string;
  monogram: string;
  title: string; // SEO-flavored: "Unofficial X API"
  blurb: string;
  author: string;
  stars: number;
  lang: 'Python' | 'TypeScript';
  category: Category;
  tags: string[];
  accent: string; // brand-ish accent, used as icon-tile bg + monogram fallback
  domain: string; // brand domain, for the logo service
  featured?: boolean;
};

export const CATEGORIES: Category[] = ['AI', 'Music', 'Social', 'Finance', 'Shopping', 'Dev'];

// Brand icon by domain. DuckDuckGo's icon service is no-token, domain-keyed,
// and reliable (Clearbit's free logo API is dead; Pipedream's logos are keyed
// by internal app_id, not domain; logo.dev needs a token). One-line swap.
export const logoUrl = (domain: string) => `https://icons.duckduckgo.com/ip3/${domain}.ico`;

export const CLIENTS: RaeClient[] = [
  {
    slug: 'spotify',
    service: 'Spotify',
    monogram: 'Sp',
    title: 'Unofficial Spotify API',
    blurb: 'Search tracks, read playlists and pull audio features straight from the web player — no developer app, no rate-limited tokens.',
    author: '@maelle',
    stars: 412,
    lang: 'Python',
    category: 'Music',
    tags: ['search', 'auth', 'playlists'],
    accent: '#1db954',
    domain: 'spotify.com',
    featured: true,
  },
  {
    slug: 'perplexity',
    service: 'Perplexity',
    monogram: 'Px',
    title: 'Unofficial Perplexity API',
    blurb: 'Drive Perplexity answers and follow-ups programmatically, including the sources panel and the model picker.',
    author: '@dvv',
    stars: 308,
    lang: 'Python',
    category: 'AI',
    tags: ['stream', 'auth', 'sources'],
    accent: '#20808d',
    domain: 'perplexity.ai',
    featured: true,
  },
  {
    slug: 'suno',
    service: 'Suno',
    monogram: 'Su',
    title: 'Unofficial Suno API',
    blurb: 'Queue song generations, poll job status and download finished tracks — the captcha-gated flow handled for you.',
    author: '@kalil',
    stars: 286,
    lang: 'Python',
    category: 'Music',
    tags: ['jobs', 'captcha', 'download'],
    accent: '#000000',
    domain: 'suno.com',
  },
  {
    slug: 'notion',
    service: 'Notion',
    monogram: 'No',
    title: 'Unofficial Notion API',
    blurb: 'Read and write blocks the web app can but the public API still cannot — synced blocks, page comments and database views.',
    author: '@hana',
    stars: 241,
    lang: 'TypeScript',
    category: 'Dev',
    tags: ['blocks', 'auth', 'sync'],
    accent: '#111111',
    domain: 'notion.so',
  },
  {
    slug: 'linear',
    service: 'Linear',
    monogram: 'Li',
    title: 'Unofficial Linear API',
    blurb: 'Bulk-update issues and triage views by replaying the exact GraphQL calls the app makes, typed end to end.',
    author: '@theo',
    stars: 197,
    lang: 'TypeScript',
    category: 'Dev',
    tags: ['graphql', 'issues', 'bulk'],
    accent: '#5e6ad2',
    domain: 'linear.app',
  },
  {
    slug: 'vinted',
    service: 'Vinted',
    monogram: 'Vi',
    title: 'Unofficial Vinted API',
    blurb: 'Search listings, watch price drops and read seller feedback across every Vinted locale from one typed client.',
    author: '@lou',
    stars: 173,
    lang: 'Python',
    category: 'Shopping',
    tags: ['search', 'locale', 'watch'],
    accent: '#09b1ba',
    domain: 'vinted.com',
  },
  {
    slug: 'midjourney',
    service: 'Midjourney',
    monogram: 'Mj',
    title: 'Unofficial Midjourney API',
    blurb: 'Submit prompts, upscale, and animate jobs through the same endpoints the web app uses — Cloudflare handled.',
    author: '@kalil',
    stars: 168,
    lang: 'Python',
    category: 'AI',
    tags: ['jobs', 'video', 'cloudflare'],
    accent: '#1c1c1c',
    domain: 'midjourney.com',
  },
  {
    slug: 'wise',
    service: 'Wise',
    monogram: 'Wi',
    title: 'Unofficial Wise API',
    blurb: 'Pull live mid-market rates and your transfer history without the partner-program gate.',
    author: '@sven',
    stars: 142,
    lang: 'Python',
    category: 'Finance',
    tags: ['rates', 'auth', 'history'],
    accent: '#163300',
    domain: 'wise.com',
  },
  {
    slug: 'letterboxd',
    service: 'Letterboxd',
    monogram: 'Lb',
    title: 'Unofficial Letterboxd API',
    blurb: 'Read diaries, watchlists and ratings as typed objects — perfect for the "year in review" project they never shipped an API for.',
    author: '@noor',
    stars: 131,
    lang: 'Python',
    category: 'Social',
    tags: ['profiles', 'lists', 'ratings'],
    accent: '#00e054',
    domain: 'letterboxd.com',
  },
  {
    slug: 'elevenlabs',
    service: 'ElevenLabs',
    monogram: 'El',
    title: 'Unofficial ElevenLabs API',
    blurb: 'Reach the voice-design and dubbing endpoints the public SDK leaves out, with usage tracking baked in.',
    author: '@ravi',
    stars: 118,
    lang: 'Python',
    category: 'AI',
    tags: ['tts', 'dubbing', 'usage'],
    accent: '#000000',
    domain: 'elevenlabs.io',
  },
  {
    slug: 'strava',
    service: 'Strava',
    monogram: 'St',
    title: 'Unofficial Strava API',
    blurb: 'Get full activity streams and segment efforts without the 100-call-per-15-min cap the official API imposes.',
    author: '@mira',
    stars: 104,
    lang: 'Python',
    category: 'Social',
    tags: ['activities', 'streams', 'segments'],
    accent: '#fc4c02',
    domain: 'strava.com',
  },
  {
    slug: 'robinhood',
    service: 'Robinhood',
    monogram: 'Rh',
    title: 'Unofficial Robinhood API',
    blurb: 'Quote options chains and read your positions through the mobile endpoints, MFA flow included.',
    author: '@dane',
    stars: 96,
    lang: 'Python',
    category: 'Finance',
    tags: ['quotes', 'mfa', 'positions'],
    accent: '#00c805',
    domain: 'robinhood.com',
  },
];
