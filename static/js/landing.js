/**
 * Sleuth landing page — hero loop, carousel, scroll reveals
 */

(function () {
    'use strict';

    /* ── Mobile nav ─────────────────────────────────────── */
    const toggle = document.getElementById('lpNavToggle');
    const navLinks = document.getElementById('lpNavLinks');
    if (toggle && navLinks) {
        toggle.addEventListener('click', () => navLinks.classList.toggle('open'));
        navLinks.querySelectorAll('a').forEach(a => {
            a.addEventListener('click', () => navLinks.classList.remove('open'));
        });
    }

    /* ── Hero dashboard animation loop ──────────────────── */
    const stage = document.getElementById('heroStage');
    const stages = [
        {
            html: '<span class="investigating"><i class="fa-solid fa-spinner fa-spin"></i> Investigation Running…</span>',
            cls: 'investigating'
        },
        {
            html: 'Root Cause Found<div class="lp-mockup-confidence">Approved Vendor Discount</div><div class="lp-mockup-confidence mono">Confidence: 94%</div>',
            cls: 'resolved'
        },
        {
            html: '<span style="color:var(--text-2)">Variance Detected — Ready to investigate</span>',
            cls: ''
        }
    ];
    let stageIdx = 0;

    function runHeroLoop() {
        if (!stage) return;
        const s = stages[stageIdx];
        stage.style.opacity = '0';
        setTimeout(() => {
            stage.className = 'lp-mockup-stage ' + (s.cls || '');
            stage.innerHTML = s.html;
            stage.style.opacity = '1';
            stageIdx = (stageIdx + 1) % stages.length;
        }, 300);
    }

    if (stage) {
        setInterval(runHeroLoop, 3200);
    }

    /* ── Product carousel (fade + autoplay) ───────────── */
    const carousel = document.getElementById('productCarousel');
    if (carousel) {
        const slides = carousel.querySelectorAll('.lp-carousel-slide');
        const prevBtn = carousel.querySelector('.lp-carousel-prev');
        const nextBtn = carousel.querySelector('.lp-carousel-next');
        const dotsContainer = document.getElementById('carouselDots');
        let current = 0;
        let autoplayTimer = null;
        const AUTOPLAY_MS = 6000;

        slides.forEach((_, i) => {
            const dot = document.createElement('button');
            dot.className = 'lp-carousel-dot' + (i === 0 ? ' active' : '');
            dot.setAttribute('aria-label', 'Go to slide ' + (i + 1));
            dot.addEventListener('click', () => {
                goTo(i);
                resetAutoplay();
            });
            dotsContainer.appendChild(dot);
        });

        const dots = dotsContainer.querySelectorAll('.lp-carousel-dot');

        function goTo(index) {
            current = (index + slides.length) % slides.length;
            slides.forEach((s, i) => s.classList.toggle('active', i === current));
            dots.forEach((d, i) => d.classList.toggle('active', i === current));
        }

        function next() {
            goTo(current + 1);
        }

        function resetAutoplay() {
            clearInterval(autoplayTimer);
            autoplayTimer = setInterval(next, AUTOPLAY_MS);
        }

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                goTo(current - 1);
                resetAutoplay();
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                next();
                resetAutoplay();
            });
        }

        carousel.addEventListener('mouseenter', () => clearInterval(autoplayTimer));
        carousel.addEventListener('mouseleave', resetAutoplay);

        let touchStartX = 0;
        carousel.addEventListener('touchstart', e => {
            touchStartX = e.changedTouches[0].screenX;
        }, { passive: true });
        carousel.addEventListener('touchend', e => {
            const diff = e.changedTouches[0].screenX - touchStartX;
            if (Math.abs(diff) > 50) {
                goTo(diff > 0 ? current - 1 : current + 1);
                resetAutoplay();
            }
        }, { passive: true });

        resetAutoplay();
    }

    /* ── Scroll reveal ──────────────────────────────────── */
    const revealEls = document.querySelectorAll(
        '.lp-step-card, .lp-flow-col, .lp-checklist-card, .lp-diff-col'
    );
    const observer = new IntersectionObserver(
        entries => {
            entries.forEach(entry => {
                if (entry.isIntersecting) entry.target.classList.add('visible');
            });
        },
        { threshold: 0.15, rootMargin: '0px 0px -40px 0px' }
    );
    revealEls.forEach(el => observer.observe(el));

    /* ── Loom fallback if placeholder ID ────────────────── */
    const loom = document.getElementById('loomEmbed');
    if (loom && loom.src.includes('YOUR_LOOM_ID')) {
        loom.remove();
        const wrap = document.querySelector('.lp-video-wrap');
        if (wrap) {
            wrap.style.display = 'flex';
            wrap.style.flexDirection = 'column';
            wrap.style.alignItems = 'center';
            wrap.style.justifyContent = 'center';
            wrap.style.gap = '16px';
            wrap.style.padding = '48px 24px';
            wrap.innerHTML =
                '<p style="color:var(--text-2);font-size:14px;text-align:center;">Replace YOUR_LOOM_ID in landing.html with your Loom embed ID.</p>' +
                '<a href="https://calendly.com/itsrambikkina/30min" class="lp-btn lp-btn-cta" target="_blank" rel="noopener noreferrer">Schedule Demo</a>';
        }
    }
})();
