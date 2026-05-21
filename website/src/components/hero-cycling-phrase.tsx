'use client';

import { useState, useEffect } from 'react';

const PHRASES = ['Get the client.', 'Own the API.', 'Skip the guesswork.', 'Ditch the scraper.'];

export function HeroCyclingPhrase() {
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(true);
  const [lineKey, setLineKey] = useState(0);

  useEffect(() => {
    let hold: ReturnType<typeof setTimeout>;
    let swap: ReturnType<typeof setTimeout>;

    hold = setTimeout(() => {
      setVisible(false);
      swap = setTimeout(() => {
        setIndex((i) => (i + 1) % PHRASES.length);
        setLineKey((k) => k + 1);
        setVisible(true);
      }, 280);
    }, 2600);

    return () => {
      clearTimeout(hold);
      clearTimeout(swap);
    };
  }, [index]);

  return (
    <em className={`hero-phrase ${visible ? 'hero-phrase--in' : 'hero-phrase--out'}`}>
      {PHRASES[index]}
      {visible && <span key={lineKey} className="hero-phrase-line" aria-hidden="true" />}
    </em>
  );
}
