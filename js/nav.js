document.addEventListener("DOMContentLoaded", () => {
    // Inject the Hamburger Menu logic
    const hamburger = document.querySelector('.hamburger-menu');
    const navLinks = document.querySelector('.nav-links');
    
    if(hamburger && navLinks) {
        hamburger.addEventListener('click', () => {
            navLinks.classList.toggle('active');
        });
    }

    // Auth Avatar vs Login Button logic
    const authContainer = document.getElementById('auth-container');
    const user = localStorage.getItem("user") || sessionStorage.getItem("user");
    
    if (authContainer) {
        if (!user) {
            // Unauthenticated: Show Login button
            authContainer.innerHTML = `<a href="auth.html" class="login-btn" style="text-decoration: none">Login</a>`;
        } else {
            // Authenticated: Show Profile Avatar linked to Dashboard
            authContainer.innerHTML = `
                <a href="Dashboard.html" class="avatar-link" title="Go to Dashboard">
                    <div class="nav-avatar">🧑‍💻</div>
                </a>
            `;
        }
    }

    // --- Global Image Zoom Overlay ---
    const zoomOverlay = document.createElement("div");
    zoomOverlay.id = "global-zoom-overlay";
    zoomOverlay.style.display = "none";
    zoomOverlay.style.position = "fixed";
    zoomOverlay.style.top = "0";
    zoomOverlay.style.left = "0";
    zoomOverlay.style.width = "100%";
    zoomOverlay.style.height = "100%";
    zoomOverlay.style.backgroundColor = "rgba(0, 0, 0, 0.9)";
    zoomOverlay.style.zIndex = "99999";
    zoomOverlay.style.justifyContent = "center";
    zoomOverlay.style.alignItems = "center";
    
    const zoomImg = document.createElement("img");
    zoomImg.style.maxWidth = "90%";
    zoomImg.style.maxHeight = "90%";
    zoomImg.style.borderRadius = "12px";
    zoomImg.style.boxShadow = "0 8px 30px rgba(0,0,0,0.5)";
    zoomImg.style.objectFit = "contain";

    const closeBtn = document.createElement("span");
    closeBtn.innerHTML = "&times;";
    closeBtn.style.position = "absolute";
    closeBtn.style.top = "20px";
    closeBtn.style.right = "30px";
    closeBtn.style.color = "#fff";
    closeBtn.style.fontSize = "40px";
    closeBtn.style.cursor = "pointer";

    zoomOverlay.appendChild(closeBtn);
    zoomOverlay.appendChild(zoomImg);
    document.body.appendChild(zoomOverlay);

    const closeZoom = () => zoomOverlay.style.display = "none";
    closeBtn.addEventListener("click", closeZoom);
    zoomOverlay.addEventListener("click", (e) => {
        if(e.target !== zoomImg) closeZoom();
    });

    window.openZoom = function(src) {
        if(!src) return;
        zoomImg.src = src;
        zoomOverlay.style.display = "flex";
    };

    // Attach to dynamic images that might want it automatically:
    document.body.addEventListener('click', function(e) {
        // Automatically hook if the image has a specific class or we manually fired it
        // We will just let inline click handlers call window.openZoom for safety, 
        // but let's automatically support Dashboard.html timeline images!
        if (e.target.tagName === 'IMG' && e.target.closest('#activity-timeline')) {
            window.openZoom(e.target.src);
        }
        if (e.target.tagName === 'IMG' && e.target.closest('#camera-box') && e.target.id === 'photo-result') {
            window.openZoom(e.target.src);
        }
    });

});
