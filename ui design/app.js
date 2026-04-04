/* ═══════════════════════════════════════════
   Landing Page — Interactive Logic
   Handles stagger reveals, scroll nav,
   theme toggle, and workflow step animations.
   ═══════════════════════════════════════════ */

(function () {
  'use strict';

  // ─── Theme toggle ───
  function initThemeToggle() {
    const btn = document.getElementById('themeToggle');
    if (!btn) return;

    const saved = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initial = saved || (prefersDark ? 'dark' : 'light');

    if (initial === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    }

    btn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('theme', next);
      showToast(next === 'dark' ? 'Dark mode enabled' : 'Light mode enabled');
    });
  }

  // ─── Toast ───
  function showToast(message) {
    const toast = document.getElementById('toast');
    const msg = document.getElementById('toastMessage');
    if (!toast || !msg) return;

    msg.textContent = message;
    if (toast._hideTimeout) clearTimeout(toast._hideTimeout);

    requestAnimationFrame(() => {
      toast.classList.add('show');
      toast._hideTimeout = setTimeout(() => {
        toast.classList.remove('show');
      }, 2500);
    });
  }

  // ─── Scroll-aware nav ───
  function initScrollNav() {
    const nav = document.getElementById('mainNav');
    if (!nav) return;

    let ticking = false;
    window.addEventListener('scroll', () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          nav.classList.toggle('scrolled', window.scrollY > 20);
          ticking = false;
        });
        ticking = true;
      }
    }, { passive: true });
  }

  // ─── Stagger reveal via IntersectionObserver ───
  function initStagger() {
    const items = document.querySelectorAll('.stagger-item');
    if (!items.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            // Get all siblings that are also stagger items in the same parent
            const parent = entry.target.parentElement;
            const siblings = parent
              ? Array.from(parent.querySelectorAll(':scope > .stagger-item'))
              : [entry.target];

            const index = siblings.indexOf(entry.target);
            const delay = Math.max(0, index) * 60; // 60ms stagger

            setTimeout(() => {
              entry.target.classList.add('visible');
            }, delay);

            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15, rootMargin: '0px 0px -40px 0px' }
    );

    items.forEach((item) => observer.observe(item));
  }

  // ─── Apply progress bar animation ───
  function initApplyAnimation() {
    const applyFill = document.getElementById('applyFill');
    const applyCheck = document.querySelector('.apply-check');
    if (!applyFill) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setTimeout(() => {
              applyFill.classList.add('animate');
              if (applyCheck) applyCheck.classList.add('show');
            }, 500);
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.3 }
    );

    observer.observe(applyFill);
  }

  // ─── 3D Tilt on mockup card ───
  function initMockupTilt() {
    const card = document.getElementById('mockupCard');
    if (!card) return;

    const matchesHover = window.matchMedia('(hover: hover) and (pointer: fine)');
    if (!matchesHover.matches) return;

    card.addEventListener('mousemove', (e) => {
      const rect = card.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width - 0.5;
      const y = (e.clientY - rect.top) / rect.height - 0.5;

      card.style.transform = `
        perspective(800px)
        rotateY(${x * 6}deg)
        rotateX(${-y * 4}deg)
        translateY(-4px)
      `;
    });

    card.addEventListener('mouseleave', () => {
      card.style.transform = '';
    });
  }

  // ─── Button ripple ───
  function initButtonFeedback() {
    document.querySelectorAll('.btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        if (btn.disabled) return;
        const rect = btn.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        const ripple = document.createElement('span');
        ripple.style.cssText = `
          position: absolute; width: 0; height: 0;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.25);
          transform: translate(-50%, -50%);
          left: ${x}px; top: ${y}px;
          pointer-events: none;
        `;

        btn.appendChild(ripple);

        ripple.animate(
          [
            { width: '0px', height: '0px', opacity: 1 },
            { width: '300px', height: '300px', opacity: 0 },
          ],
          { duration: 500, easing: 'cubic-bezier(0.23, 1, 0.32, 1)', fill: 'forwards' }
        ).onfinish = () => ripple.remove();
      });
    });
  }

  // ─── Init ───
  function init() {
    initThemeToggle();
    initScrollNav();
    initStagger();
    initApplyAnimation();
    initMockupTilt();
    initButtonFeedback();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
