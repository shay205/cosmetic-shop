/* =====================================================
   GLOW BEAUTY - Main JavaScript
   ===================================================== */

document.addEventListener('DOMContentLoaded', function () {

    // ---------- 1. Mobile menu toggle ----------
    const navToggle = document.getElementById('navToggle');
    const primaryNav = document.getElementById('primaryNav');

    function closeMenu() {
        navToggle.classList.remove('open');
        primaryNav.classList.remove('open');
        navToggle.setAttribute('aria-expanded', 'false');
    }

    if (navToggle && primaryNav) {
        navToggle.addEventListener('click', function () {
            const isOpen = primaryNav.classList.toggle('open');
            navToggle.classList.toggle('open', isOpen);
            navToggle.setAttribute('aria-expanded', String(isOpen));
        });

        // Close the menu after tapping a link
        primaryNav.querySelectorAll('a').forEach(function (link) {
            link.addEventListener('click', closeMenu);
        });
    }

    // ---------- 2. Header shadow when scrolling ----------
    const header = document.getElementById('siteHeader');
    function handleScroll() {
        if (!header) return;
        header.classList.toggle('scrolled', window.scrollY > 10);
    }
    window.addEventListener('scroll', handleScroll, { passive: true });
    handleScroll();

    // ---------- 3. Scroll reveal animation ----------
    const revealItems = document.querySelectorAll('.reveal');

    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry, index) {
                if (entry.isIntersecting) {
                    // Small stagger so cards appear one after another
                    setTimeout(function () {
                        entry.target.classList.add('visible');
                    }, index * 80);
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.12 });

        revealItems.forEach(function (item) { observer.observe(item); });
    } else {
        // Very old browsers: just show everything
        revealItems.forEach(function (item) { item.classList.add('visible'); });
    }

    // ---------- 4. Newsletter form (front-end only for now) ----------
    const form = document.getElementById('newsletterForm');
    const emailInput = document.getElementById('newsletterEmail');
    const message = document.getElementById('newsletterMsg');

    if (form && emailInput && message) {
        form.addEventListener('submit', function (event) {
            event.preventDefault();
            const email = emailInput.value.trim();
            const looksValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

            if (!looksValid) {
                message.textContent = 'Please enter a valid email address.';
                return;
            }
            message.textContent = 'Thank you for joining the Glow Club! 💖';
            form.reset();
        });
    }

    // ---------- 5. Search bar (opens from the magnifier icon) ----------
    const searchToggle = document.getElementById('searchToggle');
    const searchPanel = document.getElementById('searchPanel');
    const searchInput = document.getElementById('searchInput');

    function setSearchOpen(isOpen) {
        searchPanel.classList.toggle('open', isOpen);
        searchToggle.setAttribute('aria-expanded', String(isOpen));
    }

    if (searchToggle && searchPanel && searchInput) {
        // Click the magnifier: open or close the bar instead of leaving the page
        searchToggle.addEventListener('click', function (event) {
            event.preventDefault();
            const willOpen = !searchPanel.classList.contains('open');
            setSearchOpen(willOpen);
            if (willOpen) {
                searchInput.focus();
            }
        });

        // Press Escape to close the bar
        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && searchPanel.classList.contains('open')) {
                setSearchOpen(false);
                searchToggle.focus();
            }
        });

        // On the results page, keep the bar open so the customer sees what they searched
        if (searchInput.value.trim() !== '') {
            setSearchOpen(true);
        }
    }

    // ---------- 6. Account menu (logged-in customers) ----------
    const userMenu = document.getElementById('userMenu');
    const userMenuToggle = document.getElementById('userMenuToggle');

    // This only exists when a customer is logged in, so skip it otherwise
    if (userMenu && userMenuToggle) {

        function setUserMenuOpen(isOpen) {
            userMenu.classList.toggle('open', isOpen);
            userMenuToggle.setAttribute('aria-expanded', String(isOpen));
        }

        // Click the avatar: open or close the dropdown
        userMenuToggle.addEventListener('click', function () {
            setUserMenuOpen(!userMenu.classList.contains('open'));
        });

        // Click anywhere outside the menu: close it
        document.addEventListener('click', function (event) {
            if (!userMenu.contains(event.target)) {
                setUserMenuOpen(false);
            }
        });

        // Press Escape: close it and return focus to the avatar button
        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && userMenu.classList.contains('open')) {
                setUserMenuOpen(false);
                userMenuToggle.focus();
            }
        });
    }

    // ---------- 7. M-Pesa payment status ----------
    const paymentStatus = document.getElementById('paymentStatus');
    if (paymentStatus && paymentStatus.dataset.statusUrl) {
        const statusMessages = {
            pending: 'M-Pesa prompt sent. Waiting for payment confirmation.',
            successful: 'Payment confirmed.',
            failed: 'M-Pesa payment failed. Please contact us for help.',
            cancelled: 'M-Pesa payment was cancelled.',
        };

        const checkPaymentStatus = function () {
            fetch(paymentStatus.dataset.statusUrl, {
                headers: { 'Accept': 'application/json' },
            })
                .then(function (response) {
                    if (!response.ok) throw new Error('Payment status request failed.');
                    return response.json();
                })
                .then(function (data) {
                    paymentStatus.textContent = statusMessages[data.status] || data.message;
                    if (data.status === 'successful' && data.receipt) {
                        paymentStatus.textContent += ' Receipt: ' + data.receipt + '.';
                    }
                    if (data.status !== 'pending') clearInterval(paymentStatusTimer);
                })
                .catch(function () {
                    paymentStatus.textContent = 'Payment status is temporarily unavailable. Please refresh this page.';
                });
        };

        const paymentStatusTimer = setInterval(checkPaymentStatus, 4000);
        checkPaymentStatus();
    }
});