const CARDS = [
  {
    id: '001',
    title: 'MIT license',
    note: 'Use it commercially. Fork it. Ship it inside a closed-source product. No royalties, no copyleft, no licensing call with legal.',
  },
  {
    id: '002',
    title: 'No telemetry',
    note: 'rae never phones home. Your HAR captures, your generated clients, your browsing — they stay on your machine. The repo is the whole product.',
  },
  {
    id: '003',
    title: 'Code stays yours',
    note: 'Generated clients are plain Python files. No SDK to pin, no service to depend on. Just code in your repo.',
  },
];

export function BuiltInTheOpen() {
  return (
    <section className="bg-[#e8e3f0] dark:bg-[#15101e] min-h-[100svh] flex items-center">
      <div className="w-full mx-auto max-w-7xl px-6 lg:px-10 py-24 md:py-36">
        <div className="mb-12 md:mb-14 flex justify-end">
          <div className="text-right max-w-2xl">
            <h2
              className="font-display italic tracking-[-0.03em] leading-tight
                text-[clamp(1.6rem,3vw,2.4rem)]
                text-[rgba(30,20,50,0.88)] dark:text-[rgba(248,244,255,0.92)]"
              style={{ fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1", fontWeight: 400 }}
            >
              Built in the open.{' '}
              <span className="text-[#885dc5] dark:text-[#b89dff]">Stays yours.</span>
            </h2>
          </div>
        </div>

        <div
          className="grid grid-cols-1 md:grid-cols-3 gap-px
            bg-[rgba(30,20,50,0.14)] dark:bg-[rgba(248,244,255,0.08)]
            rounded-md overflow-hidden"
        >
          {CARDS.map((c) => (
            <div
              key={c.id}
              className="bg-[#f2effa] dark:bg-[#1e1729]
                px-6 py-7 md:px-7 md:py-8 flex flex-col"
            >
              <p
                className="font-mono text-[9px] tracking-[0.15em]
                  text-[rgba(30,20,50,0.28)] dark:text-[rgba(248,244,255,0.32)]
                  mb-5"
              >
                N° {c.id}
              </p>
              <p
                className="font-display italic text-xl leading-[1.15] tracking-[-0.02em]
                  text-[rgba(30,20,50,0.88)] dark:text-[rgba(248,244,255,0.92)]
                  mb-4"
                style={{ fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1", fontWeight: 400 }}
              >
                {c.title}
              </p>
              <div
                className="border-t pt-3.5
                  border-[rgba(30,20,50,0.15)] dark:border-[rgba(248,244,255,0.12)]"
              >
                <p
                  className="font-mono text-[10px] leading-[1.7]
                    text-[rgba(30,20,50,0.55)] dark:text-[rgba(248,244,255,0.55)]"
                >
                  {c.note}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
