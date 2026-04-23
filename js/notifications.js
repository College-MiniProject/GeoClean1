// js/notifications.js
document.addEventListener('DOMContentLoaded', async () => {
    // Check if notifications are supported
    if (!("Notification" in window)) {
        console.log("This browser does not support desktop notification");
        return;
    }

    let currentLat = null;
    let currentLng = null;

    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(pos => {
            currentLat = pos.coords.latitude;
            currentLng = pos.coords.longitude;
        }, err => console.log("GPS not available, will fallback to home location in backend"));
    }

    function injectVerifyModal() {
        if (document.getElementById('global-verify-modal')) return;
        const html = `
        <div id="global-verify-modal" class="modal-overlay" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); z-index:9999; justify-content:center; align-items:center;">
          <div style="background:#1a1a1a; padding:20px; border-radius:12px; border:1px solid #10b981; max-width:400px; text-align:center; color:white; position:relative;">
            <button onclick="document.getElementById('global-verify-modal').style.display='none'" style="position:absolute; top:10px; right:15px; background:none; border:none; color:white; font-size:1.5rem; cursor:pointer;">&times;</button>
            <h2 style="margin-top:0;">Verify Nearby Garbage</h2>
            <p style="color:#aaa; font-size:0.95rem; margin-bottom:20px;">
              You are near a newly reported garbage site at <br/><strong id="global-verify-location" style="color:#fff;"></strong>.<br/><br/>
              Can you confirm if the garbage is actually there?
            </p>
            <div style="display:flex; gap:15px; justify-content:center;">
              <button id="btn-global-verify-yes" style="background:#10b981; color:#000; border:none; padding:10px 20px; border-radius:8px; cursor:pointer; font-weight:bold;">👍 Yes, it's there</button>
              <button id="btn-global-verify-no" style="background:#ff0055; color:#fff; border:none; padding:10px 20px; border-radius:8px; cursor:pointer; font-weight:bold;">👎 No, fake report</button>
            </div>
          </div>
        </div>
        `;
        document.body.insertAdjacentHTML('beforeend', html);
    }

    window.submitGlobalVerification = async function(missionId, status) {
        const user = localStorage.getItem('user') || sessionStorage.getItem("user");
        try {
            await fetch(`${window.location.origin}/missions/${missionId}/verify`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ email: user, status: status })
            });
            alert('Thank you for verifying!');
        } catch(e) {}
        document.getElementById('global-verify-modal').style.display = 'none';
    };

    // Register Service Worker
    if ('serviceWorker' in navigator) {
        try {
            const registration = await navigator.serviceWorker.register('/sw.js');
            console.log('Service Worker registered with scope:', registration.scope);
            
            // Request Notification Permission
            if (Notification.permission === 'default' || Notification.permission === 'prompt') {
                const permission = await Notification.requestPermission();
                console.log('Notification permission:', permission);
            }

            const user = localStorage.getItem('user') || sessionStorage.getItem("user");
            if (user) {
                // Poll backend for proximity missions every 15 seconds
                setInterval(async () => {
                   try {
                       let latLngQuery = (currentLat !== null && currentLng !== null) ? `&lat=${currentLat}&lng=${currentLng}` : "";
                       const res = await fetch(`${window.location.origin}/notifications/poll?email=${user}${latLngQuery}`);
                       if(res.ok) {
                           const data = await res.json();
                           if (data.notifications && data.notifications.length > 0) {
                               let notified = JSON.parse(sessionStorage.getItem('notified_missions') || '[]');
                               data.notifications.forEach(m => {
                                   if (!notified.includes(m.id)) {
                                       if (Notification.permission === 'granted') {
                                           registration.showNotification("New Mission Nearby! 🌍", {
                                               body: `${m.type} reported near you. Open Dashboard to inspect.`,
                                               icon: "https://cdn-icons-png.flaticon.com/512/3233/3233483.png"
                                           });
                                       }
                                       notified.push(m.id);
                                   }
                               });
                               sessionStorage.setItem('notified_missions', JSON.stringify(notified));
                           }
                       }
                   } catch(e) {
                       console.error("Polling error", e);
                   }
                }, 15000);

                // Poll backend for proximity verifications every 20 seconds
                setInterval(async () => {
                   try {
                       let latLngQuery = (currentLat !== null && currentLng !== null) ? `&lat=${currentLat}&lng=${currentLng}` : "";
                       const vRes = await fetch(`${window.location.origin}/notifications/verify_poll?email=${user}${latLngQuery}`);
                       if(vRes.ok) {
                           const vData = await vRes.json();
                           if (vData.verifications && vData.verifications.length > 0) {
                               injectVerifyModal();
                               let asked = JSON.parse(sessionStorage.getItem('asked_verifications') || '[]');
                               for (let m of vData.verifications) {
                                   if (!asked.includes(m.id)) {
                                       // Show global modal
                                       document.getElementById('global-verify-location').innerText = m.location_text || m.full_address || "Nearby Location";
                                       document.getElementById('global-verify-modal').style.display = 'flex';
                                       
                                       document.getElementById('btn-global-verify-yes').onclick = () => submitGlobalVerification(m.id, 'garbage_present');
                                       document.getElementById('btn-global-verify-no').onclick = () => submitGlobalVerification(m.id, 'clean');

                                       // Show push notification
                                       if (Notification.permission === 'granted') {
                                           registration.showNotification("Verify nearby mission", {
                                               body: `Are you near ${m.location_text || m.full_address}? Is there garbage? Please verify!`,
                                               icon: "https://cdn-icons-png.flaticon.com/512/3233/3233483.png"
                                           });
                                       }
                                       asked.push(m.id);
                                       break; // only ask one at a time
                                   }
                               }
                               sessionStorage.setItem('asked_verifications', JSON.stringify(asked));
                           }
                       }
                   } catch(e) { }
                }, 20000);
            }
        } catch (error) {
            console.error('Service Worker registration failed:', error);
        }
    }
});
