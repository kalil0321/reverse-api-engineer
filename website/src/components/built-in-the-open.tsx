const CARDS = [
  {
    id: '001',
    title: 'MIT licensed',
    note: 'Use it at work, fork it, or ship it inside a closed-source product. No fees, no copyleft, no strings attached.',
  },
  {
    id: '002',
    title: 'Runs locally',
    note: 'Everything happens on your machine. The traffic you capture and the clients it generates never leave it — no account, no server, no analytics.',
  },
  {
    id: '003',
    title: 'You own the output',
    note: 'rae writes plain Python files straight into your project. No SDK to depend on, no service that can go away — just code you can read and edit.',
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
              Open source.{' '}
              <span className="text-[#885dc5] dark:text-[#b89dff]">Runs on your machine.</span>
            </h2>
          </div>
        </div>

        <div
          className="grid grid-cols-1 md:grid-cols-3 gap-px
            bg-[rgba(30,20,50,0.14)] dark:bg-[rgba(248,244,255,0.08)]
            rounded-md"
        >
          {CARDS.map((c, i) => (
            <div
              key={c.id}
              className={`oss-hov bg-[#f2effa] dark:bg-[#1e1729]
                px-6 py-7 md:px-7 md:py-8 flex flex-col ${
                  i === 0
                    ? 'rounded-t-md md:rounded-tr-none md:rounded-bl-md'
                    : i === CARDS.length - 1
                      ? 'rounded-b-md md:rounded-bl-none md:rounded-tr-md'
                      : ''
                }`}
            >
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
