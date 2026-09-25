// FraudX background: black space starfield with occasional shooting stars.
// Drop this in as static/bg.js (replaces the previous network-graph background).
// Paints its own black background each frame, so it works regardless of the page's own background color.
(() => {
  const cv = document.getElementById('bg'), cx = cv.getContext('2d');
  let W, H, stars = [], shooters = [], dpr = Math.min(devicePixelRatio || 1, 2);
  const R = (a, b) => a + Math.random() * (b - a);

  function init() {
    W = innerWidth; H = innerHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    cx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.min(500, Math.round((W * H) / 2200));
    stars = [];
    for (let i = 0; i < n; i++) {
      stars.push({ x: R(0, W), y: R(0, H), r: R(0.4, 1.8), ph: R(0, 6.28), sp: R(0.0006, 0.0022), base: R(0.2, 0.9) });
    }
    shooters = [];
  }

  function spawnShooter() {
    shooters.push({ x: R(0, W * 0.7), y: R(0, H * 0.4), len: R(60, 140), ang: 0.5, life: 1 });
  }

  function frame(t) {
    // solid black backdrop (works even if the page body isn't black)
    cx.fillStyle = '#02040a';
    cx.fillRect(0, 0, W, H);

    // twinkling stars
    stars.forEach(s => {
      const a = s.base * (0.5 + 0.5 * Math.sin(t * s.sp + s.ph));
      cx.fillStyle = `rgba(255,255,255,${a})`;
      cx.beginPath(); cx.arc(s.x, s.y, s.r, 0, 6.28); cx.fill();
    });

    // occasional ambient shooting star
    if (Math.random() < 0.012 && !matchMedia('(prefers-reduced-motion: reduce)').matches) spawnShooter();

    shooters = shooters.filter(s => s.life > 0);
    shooters.forEach(s => {
      const dx = -s.len * Math.cos(s.ang), dy = -s.len * Math.sin(s.ang);
      const g = cx.createLinearGradient(s.x, s.y, s.x + dx, s.y + dy);
      g.addColorStop(0, `rgba(255,255,255,${s.life})`);
      g.addColorStop(1, 'rgba(255,255,255,0)');
      cx.strokeStyle = g; cx.lineWidth = 1.4;
      cx.beginPath(); cx.moveTo(s.x, s.y);
      s.x += s.len * 0.3 * Math.cos(s.ang);
      s.y += s.len * 0.3 * Math.sin(s.ang);
      cx.lineTo(s.x, s.y); cx.stroke();
      s.life -= 0.02;
    });

    if (!matchMedia('(prefers-reduced-motion: reduce)').matches) requestAnimationFrame(frame);
  }

  addEventListener('resize', init);
  init();

  // Kept for compatibility with app.js, which calls BG.investigate() when a case is opened
  // or evidence changes. There's no node graph in this background, so it just triggers a
  // small burst of shooting stars as a subtle "something happened" cue.
  window.BG = {
    investigate() {
      for (let i = 0; i < 3; i++) setTimeout(spawnShooter, i * 120);
    }
  };

  requestAnimationFrame(frame);
})();