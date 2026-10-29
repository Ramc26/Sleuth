/**
 * Sleuth landing — motion, carousel, nav
 */

(function () {
    'use strict';

    const toggle = document.getElementById('lpNavToggle');
    const navLinks = document.getElementById('lpNavLinks');
    if (toggle && navLinks) {
        toggle.addEventListener('click', () => navLinks.classList.toggle('open'));
        navLinks.querySelectorAll('a').forEach(a => {
            a.addEventListener('click', () => navLinks.classList.remove('open'));
        });
    }

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

        function next() { goTo(current + 1); }

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

    const revealEls = document.querySelectorAll('.lp-flow-card, .lp-step, .lp-check, .lp-diff-col');
    const observer = new IntersectionObserver(
        entries => {
            entries.forEach(entry => {
                if (entry.isIntersecting) entry.target.classList.add('visible');
            });
        },
        { threshold: 0.15, rootMargin: '0px 0px -40px 0px' }
    );
    revealEls.forEach(el => observer.observe(el));
})();
