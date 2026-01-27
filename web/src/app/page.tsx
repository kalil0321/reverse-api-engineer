export default function Home() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950">
      <main className="flex flex-col items-center gap-8 text-center px-8">
        <h1 className="text-5xl font-bold text-white tracking-tight">
          Reverse API Engineer
        </h1>
        <p className="text-xl text-zinc-400 max-w-xl">
          Cloud-based API client generation from browser traffic.
          Capture HAR files in a cloud browser and generate production-ready Python clients.
        </p>
        <div className="flex gap-4 mt-4">
          <button className="px-6 py-3 bg-white text-zinc-950 font-medium rounded-lg hover:bg-zinc-200 transition-colors">
            Get Started
          </button>
          <button className="px-6 py-3 border border-zinc-700 text-zinc-300 font-medium rounded-lg hover:bg-zinc-800 transition-colors">
            Documentation
          </button>
        </div>
        <p className="text-sm text-zinc-600 mt-8">
          Coming Soon
        </p>
      </main>
    </div>
  );
}
